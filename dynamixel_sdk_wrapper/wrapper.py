"""
Dynamixel SDK wrapper with command-based dispatch.

Public API:
  - send_cmd(cmd) → int | Dict[int, int] | bool   (dispatched by command type)
  - add_servo(servos: List[ServoConfig])              (register & configure servos)
  - open_port() / close_port()

Commands are routed by their base class:
  SingleReadCommand  → _handle_single_read   → int
  SyncReadCommand    → _handle_sync_read     → Dict[int, int]
  SingleWriteCommand → _handle_single_write  → bool
  SyncWriteCommand   → _handle_sync_write    → bool
  CompoundCommand    → _handle_compound      → bool
"""

from dynamixel_sdk import (
    PacketHandler, PortHandler, GroupBulkWrite,
    GroupBulkRead, GroupSyncWrite, GroupSyncRead, COMM_SUCCESS, DXL_LOWORD,
    DXL_HIWORD, DXL_LOBYTE, DXL_HIBYTE
)

from dynamixel_sdk_wrapper.cmds import *
from dynamixel_sdk_wrapper.control_tables import CONTROL_TABLE

import logging
from typing import Dict, List, Union
from dataclasses import dataclass, field

# Registers whose raw values should be interpreted as signed
SIGNED_REGISTERS = frozenset({
    'PRESENT_POSITION', 'PRESENT_VELOCITY', 'PRESENT_CURRENT',
    'GOAL_POSITION', 'GOAL_VELOCITY', 'GOAL_CURRENT',
    'HOMING_OFFSET',
})


@dataclass
class ServoConfig:
    """User-facing configuration for registering a Dynamixel servo.

    Only ``id_`` and ``model`` are required. Every optional field left as
    ``None`` is simply not written to the servo during ``add_servo()``;
    fields marked EEPROM persist across power cycles.
    """
    id_: int
    model: str
    name: str = ''
    # Operating mode
    op_mode: str = 'extended_pos'
    reverse: bool = False
    # Limits (EEPROM)
    pos_limit: tuple = None           # (min, max) raw ticks
    current_limit: int = None         # mA
    velocity_limit: int = None        # raw units
    temperature_limit: int = None     # degrees C
    pwm_limit: int = None             # raw units
    voltage_limit: tuple = None       # (min, max) in 0.1 V units
    # Motion (EEPROM)
    homing_offset: int = None         # raw ticks
    moving_threshold: int = None      # raw units
    # Misc
    shutdown: int = None              # error bitmask
    profile_acceleration: int = None  # raw units (RAM, but useful at init)
    led: bool = None                  # initial LED state
    bus_watchdog: int = None          # 0 = disabled, 1-127 in 20 ms units


@dataclass
class Servo:
    """Internal runtime state for a registered Dynamixel servo."""
    id_: int
    model: str
    control_table: dict
    firmware_ver: int = 0
    position_limits: dict = field(default_factory=lambda: {'min': -1048575, 'max': 1048575})
    operating_mode: str = 'extended_pos'
    torque_status: bool = False
    # Limits (cached from EEPROM)
    current_limit: int = 0
    velocity_limit: int = 0
    temperature_limit: int = 0
    pwm_limit: int = 0
    voltage_limits: dict = field(default_factory=lambda: {'min': 0, 'max': 0})
    # Motion config
    homing_offset: int = 0
    moving_threshold: int = 0
    # Status
    hardware_error_status: int = 0
    led: bool = False

    def __repr__(self):
        return (f"Servo(ID={self.id_}, Model='{self.model}', FW={self.firmware_ver}, "
                f"OpMode='{self.operating_mode}', Torque={'On' if self.torque_status else 'Off'})")


class DynamixelSDKWrapper:
    """Command-driven wrapper for the Dynamixel SDK.

    All bus operations go through :meth:`send_cmd`, which dispatches on the
    command's base class (see ``cmds.py``). Typical lifecycle::

        dxl = DynamixelSDKWrapper(port="/dev/ttyUSB0", baudrate=4_000_000)
        dxl.open_port()
        dxl.add_servo([ServoConfig(id_=1, model="XC330")])
        dxl.send_cmd(TorqueCommand(ids=[1], enable=[True]))
        ...
        dxl.close_port()

    Communication failures never raise; they return sentinels
    (``INVALID_INT_VAL`` / ``{}`` / ``False``). Enable SDK error logging
    with :meth:`suppress_error_msg`.

    Attributes:
        servos: Registered servos keyed by bus ID.
        INVALID_INT_VAL: Sentinel returned by failed single reads (-1).
        DEDUP_REGISTERS: RAM registers whose unchanged periodic sync-write
            payloads are skipped off the wire (see :meth:`invalidate_write_cache`).
    """

    CONTROL_TABLES = CONTROL_TABLE
    SUPPRESS_ERROR_MSG = True
    INVALID_INT_VAL = -1

    #: RAM registers whose sync writes are skipped when the payload is
    #: identical to the last successful write. On a periodic control loop
    #: these are constants (profile durations, current limits) resent every
    #: cycle — each skip saves a full wire packet. The cache is invalidated
    #: by any compound command, reboot, or add_servo (events after which the
    #: register content can no longer be assumed).
    DEDUP_REGISTERS = frozenset({'PROFILE_VELOCITY', 'GOAL_CURRENT'})

    def __init__(self, port: str, protocol: float = 2.0, baudrate: int = 115200):
        """Create a wrapper bound to one serial port.

        Args:
            port: Serial device, e.g. ``"COM3"`` or ``"/dev/ttyUSB0"``.
            protocol: Dynamixel protocol version (2.0 for all X-series).
            baudrate: Bus baud rate; applied when :meth:`open_port` is called.
        """
        self.port: str = port
        self.port_handler: PortHandler = PortHandler(port)
        self.packet_handler: PacketHandler = PacketHandler(protocol)
        self.servos: Dict[int, Servo] = {}
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s", datefmt="[%X]")
        self.logger = logging.getLogger(__name__)
        self.baudrate = baudrate
        # Reused group handlers, keyed by (addr, len): the SDK pattern is
        # create-once / transact-per-cycle. Rebuilding a Group object and
        # re-adding every param on each 100+ Hz call was pure overhead.
        self._sync_write_groups: Dict[tuple, tuple] = {}   # (addr,len) -> (group, {ids})
        self._sync_read_groups: Dict[tuple, tuple] = {}    # (addr,len) -> (group, tuple(ids))
        self._last_sync_payload: Dict[str, Dict[int, List[int]]] = {}

    def invalidate_write_cache(self) -> None:
        """Forget deduplicated register payloads (forces the next sync write
        of every DEDUP register to go out on the wire)."""
        self._last_sync_payload.clear()

    def __del__(self):
        self.close_port()

    # ========================= Public API =========================

    def send_cmd(self, cmd) -> Union[int, Dict[int, int], Dict[int, Dict[str, int]], bool]:
        """
        Single entry-point for all Dynamixel operations.

        Routes the command to the appropriate handler based on its base class:
          SingleReadCommand  → int
          SyncReadCommand    → Dict[int, int]  (signed-corrected)
          BulkReadCommand    → Dict[int, Dict[str, int]] (signed-corrected)
          SingleWriteCommand → bool
          SyncWriteCommand   → bool
          BulkWriteCommand   → bool
          CompoundCommand    → bool

        Args:
            cmd: Any command dataclass from ``dynamixel_sdk_wrapper.cmds``.

        Returns:
            The value per the table above; on communication failure a
            sentinel: ``INVALID_INT_VAL`` (-1), ``{}``, or ``False``.
            Never raises on bus errors.
        """
        if isinstance(cmd, CompoundCommand):
            # Compound commands (torque, op-mode, reboot, drive mode, …) can
            # change or reset RAM registers — drop the dedup cache so the
            # next periodic sync write re-sends ground truth.
            self._last_sync_payload.clear()
            return self._handle_compound(cmd)
        if isinstance(cmd, SingleReadCommand):
            return self._handle_single_read(cmd)
        if isinstance(cmd, SyncReadCommand):
            return self._handle_sync_read(cmd)
        if isinstance(cmd, BulkReadCommand):
            return self._handle_bulk_read(cmd)
        if isinstance(cmd, SingleWriteCommand):
            return self._handle_single_write(cmd)
        if isinstance(cmd, SyncWriteCommand):
            return self._handle_sync_write(cmd)
        if isinstance(cmd, BulkWriteCommand):
            return self._handle_bulk_write(cmd)

        self.logger.error(f"Unknown command type: {type(cmd).__name__}")
        return False

    def add_servo(self, servos_cfg: List[ServoConfig]) -> None:
        """Register and configure servos from a list of :class:`ServoConfig`.

        For each servo: ping / read firmware, disable torque, set the
        operating mode, apply startup + drive-mode configuration
        (time-based profile), and write every optional limit/EEPROM field
        provided. Each servo gets up to 5 attempts; a per-servo summary is
        logged at the end. Already-registered IDs and unsupported models
        are skipped with a log entry rather than raising.

        Args:
            servos_cfg: One :class:`ServoConfig` per servo to register.
        """
        # The id population changes: reset the reused group handlers and the
        # dedup cache so they are rebuilt against the new servo set.
        self._sync_write_groups.clear()
        self._sync_read_groups.clear()
        self._last_sync_payload.clear()
        self.suppress_error_msg(suppress=False)
        total = len(servos_cfg)
        results = {}  # label -> ('OK' | 'FAIL', reason)

        self.logger.info(f"{'=' * 50}")
        self.logger.info(f" Servo Configuration  ({total} servo{'s' if total != 1 else ''})")
        self.logger.info(f"{'=' * 50}")

        for cfg in servos_cfg:
            id_, model = cfg.id_, cfg.model
            label = cfg.name or f'ID{id_}'

            self.logger.info(f"")
            self.logger.info(f"  [{label}]  ID {id_}  |  Model: {model.upper()}")
            self.logger.info(f"  {'-' * 40}")

            # --- Pre-checks ---
            if self._is_servo_registered(id_):
                results[label] = ('SKIP', 'already registered')
                self.logger.warning(f"  Already registered — skipping")
                continue

            if model.upper() not in self.CONTROL_TABLES:
                results[label] = ('FAIL', f"unsupported model '{model}'")
                self.logger.error(f"  Unsupported model — skipping")
                continue

            # --- Configuration with retries ---
            configured = False
            op_mode = cfg.op_mode
            reverse = cfg.reverse
            lim = cfg.pos_limit

            for attempt in range(5):
                self.servos[id_] = Servo(id_, model.upper(), self.CONTROL_TABLES[model.upper()])

                steps = [
                    ('Ping / FW version', lambda: self._config_read_fw(id_),           lambda: str(self.servos[id_].firmware_ver)),
                    ('Disable torque',     lambda: self.send_cmd(TorqueCommand(ids=[id_], enable=[False])), None),
                    ('Operating mode',     lambda: self.send_cmd(OperatingModeCommand(ids=[id_], mode=op_mode)), lambda: op_mode),
                    ('Startup config',     lambda: self.send_cmd(StartupConfigCommand(id=id_, restore_ram=True, torque_enable=False)), None),
                    ('Reverse mode',       lambda: self.send_cmd(DriveModeCommand(id=id_, mode='reverse_mode', enable=reverse)), lambda: str(reverse)),
                    ('Time-based profile', lambda: self.send_cmd(DriveModeCommand(id=id_, mode='profile', enable=True)), None),
                ]
                if lim:
                    steps.insert(5, ('Position limits', lambda: self.send_cmd(
                        PositionLimitCommand(id=id_, min_pos=lim[0], max_pos=lim[1])
                    ), lambda: f"{lim[0]} .. {lim[1]}"))

                # --- Optional EEPROM config from ServoConfig ---
                if cfg.current_limit is not None:
                    steps.append(('Current limit', lambda: self.send_cmd(
                        CurrentLimitCommand(id=id_, value=cfg.current_limit)
                    ), lambda: f"{cfg.current_limit} mA"))
                if cfg.velocity_limit is not None:
                    steps.append(('Velocity limit', lambda: self.send_cmd(
                        VelocityLimitCommand(id=id_, value=cfg.velocity_limit)
                    ), lambda: str(cfg.velocity_limit)))
                if cfg.temperature_limit is not None:
                    steps.append(('Temperature limit', lambda: self.send_cmd(
                        TemperatureLimitCommand(id=id_, value=cfg.temperature_limit)
                    ), lambda: f"{cfg.temperature_limit} C"))
                if cfg.pwm_limit is not None:
                    steps.append(('PWM limit', lambda: self.send_cmd(
                        PwmLimitCommand(id=id_, value=cfg.pwm_limit)
                    ), lambda: str(cfg.pwm_limit)))
                if cfg.voltage_limit is not None:
                    steps.append(('Voltage limits', lambda: self.send_cmd(
                        VoltageLimitCommand(id=id_, min_voltage=cfg.voltage_limit[0], max_voltage=cfg.voltage_limit[1])
                    ), lambda: f"{cfg.voltage_limit[0]} .. {cfg.voltage_limit[1]}"))
                if cfg.homing_offset is not None:
                    steps.append(('Homing offset', lambda: self.send_cmd(
                        HomingOffsetCommand(id=id_, value=cfg.homing_offset)
                    ), lambda: str(cfg.homing_offset)))
                if cfg.moving_threshold is not None:
                    steps.append(('Moving threshold', lambda: self.send_cmd(
                        MovingThresholdCommand(id=id_, value=cfg.moving_threshold)
                    ), lambda: str(cfg.moving_threshold)))
                if cfg.shutdown is not None:
                    steps.append(('Shutdown config', lambda: self.send_cmd(
                        ShutdownConfigCommand(id=id_, value=cfg.shutdown)
                    ), lambda: f"0x{cfg.shutdown:02X}"))
                # --- Optional RAM config ---
                if cfg.profile_acceleration is not None:
                    steps.append(('Profile acceleration', lambda: self.send_cmd(
                        WriteRegisterCommand(id=id_, register='PROFILE_ACCELERATION', value=cfg.profile_acceleration)
                    ), lambda: str(cfg.profile_acceleration)))
                if cfg.led is not None:
                    steps.append(('LED', lambda: self.send_cmd(
                        LedCommand(id=id_, value=1 if cfg.led else 0)
                    ), lambda: 'On' if cfg.led else 'Off'))
                if cfg.bus_watchdog is not None:
                    steps.append(('Bus watchdog', lambda: self.send_cmd(
                        BusWatchdogCommand(id=id_, value=cfg.bus_watchdog)
                    ), lambda: f"{cfg.bus_watchdog * 20} ms" if cfg.bus_watchdog > 0 else 'Disabled'))

                max_name_len = max(len(s[0]) for s in steps)
                failed_step = None
                for step_name, step_fn, detail_fn in steps:
                    ok = step_fn()
                    tag = 'OK' if ok else 'FAIL'
                    detail = ''
                    if ok and detail_fn is not None:
                        detail = f" : {detail_fn()}"
                    level = self.logger.info if ok else self.logger.error
                    level(f"    {tag:<4}  {step_name:<{max_name_len}}{detail}")
                    if not ok:
                        failed_step = step_name
                        break

                if failed_step is None:
                    configured = True
                    break
                else:
                    if id_ in self.servos:
                        del self.servos[id_]
                    if attempt < 4:
                        self.logger.warning(f"  Retry {attempt + 1}/4 — failed at '{failed_step}'")

            if configured:
                self.logger.info(f"  {'-' * 40}")
                self.logger.info(f"  Result : OK")
                results[label] = ('OK', id_)
            else:
                results[label] = ('FAIL', f"failed at '{failed_step}' after 5 attempts")
                self.logger.error(f"  {'-' * 40}")
                self.logger.error(f"  Result : FAILED after 5 attempts")

        # --- Summary ---
        ok_count = sum(1 for s, _ in results.values() if s == 'OK')
        fail_count = sum(1 for s, _ in results.values() if s != 'OK')
        max_label_len = max((len(k) for k in results), default=0)
        self.logger.info(f"")
        self.logger.info(f"{'=' * 50}")
        self.logger.info(f" Summary:  {ok_count} OK  /  {fail_count} failed  /  {total} total")
        for lbl, (status, detail) in results.items():
            if status == 'OK':
                line = f"   ID {detail:>3}  ({lbl:<{max_label_len}}):  {status}"
            else:
                line = f"   ({lbl:<{max_label_len}}):  {status}  — {detail}"
            self.logger.info(line)
        self.logger.info(f"{'=' * 50}")

    def _config_read_fw(self, id_: int) -> bool:
        """Ping servo and store firmware version. Returns False on no response."""
        fw = self.send_cmd(ReadFirmwareCommand(id=id_))
        if fw == self.INVALID_INT_VAL:
            return False
        self.servos[id_].firmware_ver = fw
        return True

    def open_port(self) -> bool:
        """Open the serial port and apply the configured baud rate.

        Returns:
            True on success, False if the port could not be opened or the
            baud rate could not be set.
        """
        if self.port_handler.openPort():
            self.logger.info(f"Port {self.port} opened.")
            if self.port_handler.setBaudRate(self.baudrate):
                self.logger.info(f"Baudrate set to {self.baudrate}.")
                return True
        self.logger.error(f"Failed to open port {self.port} or set baudrate.")
        return False

    def close_port(self) -> None:
        """Close the serial port if it is open (idempotent)."""
        if self.port_handler.is_open:
            self.port_handler.closePort()
            self.logger.info(f"Port {self.port} closed.")

    def suppress_error_msg(self, suppress: bool) -> None:
        """Toggle logging of SDK packet/communication errors.

        Suppressed by default; pass ``False`` while debugging to see the
        underlying TxRx result and packet error for every failure.
        """
        self.SUPPRESS_ERROR_MSG = suppress

    # =================== Command Handlers ===================

    def _handle_single_read(self, cmd: SingleReadCommand) -> int:
        """Read one register from one servo. Returns signed value or INVALID_INT_VAL."""
        if not self._is_servo_registered(cmd.id):
            return self.INVALID_INT_VAL
        servo = self._get_servo(cmd.id)
        reg = servo.control_table[cmd.register]
        val, res, err = self._readTxRx(cmd.id, reg)
        if not self._check_communication(cmd.id, cmd.register, res, err):
            return self.INVALID_INT_VAL
        if cmd.register in SIGNED_REGISTERS:
            val = self._correct_to_signed(val, reg['LEN'])
        return val

    def _handle_sync_read(self, cmd: SyncReadCommand) -> Dict[int, int]:
        """Read one register from multiple servos. Returns {id: signed_value}."""
        if not cmd.ids:
            return {}
        first_id = cmd.ids[0]
        if not self._is_servo_registered(first_id):
            self.logger.error(f"[SyncRead] Servo ID {first_id} is not registered.")
            return {}
        reg = self._get_servo(first_id).control_table[cmd.register]
        raw = self._sync_read(cmd.ids, cmd.register)
        if cmd.register in SIGNED_REGISTERS:
            return {id_: self._correct_to_signed(v, reg['LEN']) for id_, v in raw.items()}
        return raw

    def _handle_bulk_read(self, cmd: BulkReadCommand) -> Dict[int, Dict[str, int]]:
        """Read multiple registers from multiple servos. Returns {id: {reg_name: signed_value}}."""
        if not hasattr(cmd, 'targets') or not cmd.targets:
            return {}

        # Resolve register names to dictionaries
        read_requests = {}
        for id_, reg_names in cmd.targets.items():
            if not self._is_servo_registered(id_):
                self.logger.error(f"[BulkRead] Servo ID {id_} is not registered.")
                continue
            servo = self._get_servo(id_)
            read_requests[id_] = [servo.control_table[name] for name in reg_names]

        raw_results = self._bulk_read(read_requests)

        # Apply signed correction
        corrected_results = {}
        for id_, regs_data in raw_results.items():
            corrected_results[id_] = {}
            for reg_name, val in regs_data.items():
                if val == self.INVALID_INT_VAL:
                    corrected_results[id_][reg_name] = val
                    continue
                if reg_name in SIGNED_REGISTERS:
                    reg_len = self._get_servo(id_).control_table[reg_name]['LEN']
                    val = self._correct_to_signed(val, reg_len)
                corrected_results[id_][reg_name] = val
        return corrected_results

    def _handle_bulk_write(self, cmd: BulkWriteCommand) -> bool:
        """Write multiple registers to multiple servos. Returns bool."""
        if not hasattr(cmd, 'targets') or not cmd.targets:
            return False

        write_requests = {}
        for id_, reg_val_pairs in cmd.targets.items():
            if not self._is_servo_registered(id_):
                self.logger.error(f"[BulkWrite] Servo ID {id_} is not registered.")
                continue
            servo = self._get_servo(id_)
            write_requests[id_] = [(servo.control_table[name], val) for name, val in reg_val_pairs]

        res = self._bulk_write(write_requests)
        return self._check_communication(254, 'BULK_WRITE', res)

    def _handle_single_write(self, cmd: SingleWriteCommand) -> bool:
        """Write one value to one register on one servo."""
        if not self._is_servo_registered(cmd.id):
            return False
        servo = self._get_servo(cmd.id)
        reg = servo.control_table[cmd.register]

        # Extract the value to write from command-specific fields
        if isinstance(cmd, GoalCurrentCommand):
            if servo.operating_mode not in ('current', 'current_pos'):
                self.logger.error(f"Cannot set goal current for ID {cmd.id}: not in a current-based mode.")
                return False
            value = cmd.goal_mA
        elif isinstance(cmd, ProfileTimeCommand):
            value = cmd.duration_ms
        elif hasattr(cmd, 'value'):
            value = cmd.value
        else:
            self.logger.error(f"Unhandled SingleWriteCommand subclass: {type(cmd).__name__}")
            return False

        res, err = self._writeTxRx(cmd.id, reg, value)
        return self._check_communication(cmd.id, cmd.register, res, err)

    def _handle_sync_write(self, cmd: SyncWriteCommand) -> bool:
        """Write values to one register on multiple servos."""
        if isinstance(cmd, TorqueCommand):
            return self._exec_torque(cmd)
        if isinstance(cmd, SyncGoalCurrentCommand):
            return self._exec_sync_goal_current(cmd)
        if isinstance(cmd, SyncGoalPositionCommand):
            return self._exec_sync_goal_position(cmd)
        # Generic fallback for any SyncWrite with ids + values + register
        if hasattr(cmd, 'values') and hasattr(cmd, 'ids') and hasattr(cmd, 'register'):
            return self._exec_generic_sync_write(cmd)
        self.logger.error(f"Unhandled SyncWriteCommand subclass: {type(cmd).__name__}")
        return False

    def _handle_compound(self, cmd: CompoundCommand) -> bool:
        """Dispatch compound (multi-step) commands."""
        if isinstance(cmd, GoalPositionCommand):
            return self._exec_goal_position(cmd)
        if isinstance(cmd, OperatingModeCommand):
            return self._exec_operating_mode(cmd)
        if isinstance(cmd, DriveModeCommand):
            return self._exec_drive_mode(cmd)
        if isinstance(cmd, StartupConfigCommand):
            return self._exec_startup_config(cmd)
        if isinstance(cmd, PositionLimitCommand):
            return self._exec_position_limit(cmd)
        if isinstance(cmd, RebootCommand):
            return self._exec_reboot(cmd)
        # EEPROM write commands
        if isinstance(cmd, VoltageLimitCommand):
            return self._exec_voltage_limit(cmd)
        if isinstance(cmd, EepromWriteCommand):
            return self._exec_eeprom_write(cmd)
        self.logger.error(f"Unhandled CompoundCommand subclass: {type(cmd).__name__}")
        return False

    # ============== Compound Command Executors ==============

    def _exec_goal_position(self, cmd: GoalPositionCommand) -> bool:
        """Sets current limit + profile duration + goal position for one servo."""
        if not self._is_servo_registered(cmd.id):
            return False

        servo = self._get_servo(cmd.id)
        if servo.operating_mode in ('current', 'current_pos'):
            self.send_cmd(GoalCurrentCommand(id=cmd.id, goal_mA=cmd.current_limit_mA))
        self.send_cmd(ProfileTimeCommand(id=cmd.id, duration_ms=cmd.duration_ms))

        servo = self._get_servo(cmd.id)
        if not (servo.position_limits['min'] <= cmd.position <= servo.position_limits['max']):
            self.logger.warning(f"Goal position {cmd.position} for ID {cmd.id} is out of limits.")
            return False
        res, err = self._writeTxRx(cmd.id, servo.control_table['GOAL_POSITION'], cmd.position)
        return self._check_communication(cmd.id, 'GOAL_POSITION', res, err)

    def _exec_operating_mode(self, cmd: OperatingModeCommand) -> bool:
        mode_map = {'current': 0, 'velocity': 1, 'position': 3, 'extended_pos': 4, 'current_pos': 5, 'pwm': 16}
        mode_val = mode_map.get(cmd.mode)
        if mode_val is None:
            return False
        success = True
        for id_ in cmd.ids:
            if not self._is_servo_registered(id_):
                continue
            self.send_cmd(TorqueCommand(ids=[id_], enable=[False]))
            servo = self._get_servo(id_)
            res, err = self._writeTxRx(id_, servo.control_table['OPERATING_MODE'], mode_val)
            if self._check_communication(id_, 'OPERATING_MODE', res, err):
                servo.operating_mode = cmd.mode
            else:
                success = False
        return success

    def _exec_drive_mode(self, cmd: DriveModeCommand) -> bool:
        if not self._is_servo_registered(cmd.id):
            return False
        servo = self._get_servo(cmd.id)
        mode_map = {'reverse_mode': 0, 'profile': 2, 'torque': 3}
        bit_pos = mode_map.get(cmd.mode)
        if bit_pos is None:
            return False
        current_mode, _, _ = self._readTxRx(cmd.id, servo.control_table['DRIVE_MODE'])
        new_mode = (current_mode | (1 << bit_pos)) if cmd.enable else (current_mode & ~(1 << bit_pos))
        res, err = self._writeTxRx(cmd.id, servo.control_table['DRIVE_MODE'], new_mode)
        return self._check_communication(cmd.id, 'DRIVE_MODE', res, err)

    def _exec_startup_config(self, cmd: StartupConfigCommand) -> bool:
        if not self._is_servo_registered(cmd.id):
            return False
        servo = self._get_servo(cmd.id)
        current_config, _, _ = self._readTxRx(cmd.id, servo.control_table['STARTUP_CONFIGURATION'])
        TORQUE_BIT, RAM_BIT = 0, 1
        current_config = (current_config | (1 << TORQUE_BIT)) if cmd.torque_enable else (current_config & ~(1 << TORQUE_BIT))
        current_config = (current_config | (1 << RAM_BIT)) if cmd.restore_ram else (current_config & ~(1 << RAM_BIT))
        res, err = self._writeTxRx(cmd.id, servo.control_table['STARTUP_CONFIGURATION'], current_config)
        return self._check_communication(cmd.id, 'STARTUP_CONFIG', res, err)

    def _exec_position_limit(self, cmd: PositionLimitCommand) -> bool:
        if not self._is_servo_registered(cmd.id):
            return False
        servo = self._get_servo(cmd.id)
        res1, err1 = self._writeTxRx(cmd.id, servo.control_table['MAX_POSITION_LIMIT'], cmd.max_pos)
        res2, err2 = self._writeTxRx(cmd.id, servo.control_table['MIN_POSITION_LIMIT'], cmd.min_pos)
        if self._check_communication(cmd.id, 'MAX_POS_LIMIT', res1, err1) and self._check_communication(cmd.id, 'MIN_POS_LIMIT', res2, err2):
            servo.position_limits = {'min': cmd.min_pos, 'max': cmd.max_pos}
            return True
        return False

    def _exec_reboot(self, cmd: RebootCommand) -> bool:
        if not self._is_servo_registered(cmd.id):
            return False
        res, err = self.packet_handler.reboot(self.port_handler, cmd.id)
        return self._check_communication(cmd.id, 'REBOOT', res, err)

    # ============== EEPROM Write Executors ==============

    def _exec_eeprom_write(self, cmd: EepromWriteCommand) -> bool:
        """Disable torque if needed, write EEPROM register, optionally update Servo state."""
        if not self._is_servo_registered(cmd.id):
            return False
        servo = self._get_servo(cmd.id)
        was_on = servo.torque_status
        if was_on:
            self.send_cmd(TorqueCommand(ids=[cmd.id], enable=[False]))
        res, err = self._writeTxRx(cmd.id, servo.control_table[cmd.register], cmd.value)
        ok = self._check_communication(cmd.id, cmd.register, res, err)
        if ok and cmd.servo_attr:
            setattr(servo, cmd.servo_attr, cmd.value)
        if was_on:
            self.send_cmd(TorqueCommand(ids=[cmd.id], enable=[True]))
        return ok

    def _exec_voltage_limit(self, cmd) -> bool:
        if not self._is_servo_registered(cmd.id):
            return False
        servo = self._get_servo(cmd.id)
        was_on = servo.torque_status
        if was_on:
            self.send_cmd(TorqueCommand(ids=[cmd.id], enable=[False]))
        r1, e1 = self._writeTxRx(cmd.id, servo.control_table['MAX_VOLTAGE_LIMIT'], cmd.max_voltage)
        r2, e2 = self._writeTxRx(cmd.id, servo.control_table['MIN_VOLTAGE_LIMIT'], cmd.min_voltage)
        ok = (self._check_communication(cmd.id, 'MAX_VOLTAGE_LIMIT', r1, e1)
              and self._check_communication(cmd.id, 'MIN_VOLTAGE_LIMIT', r2, e2))
        if ok:
            servo.voltage_limits = {'min': cmd.min_voltage, 'max': cmd.max_voltage}
        if was_on:
            self.send_cmd(TorqueCommand(ids=[cmd.id], enable=[True]))
        return ok

    # ============== Sync Write Executors ==============

    def _exec_torque(self, cmd: TorqueCommand) -> bool:
        if not cmd.ids:
            return False
        # Torque transitions are the natural boundary after which cached
        # register payloads should not be assumed — force a full re-send.
        self._last_sync_payload.clear()
        data = {id_: [1 if cmd.enable[i] else 0]
                for i, id_ in enumerate(cmd.ids) if self._is_servo_registered(id_)}
        res = self._sync_write('TORQUE_ENABLE', data)
        if self._check_communication(254, 'SYNC_TORQUE', res):
            for i, id_ in enumerate(cmd.ids):
                self._get_servo(id_).torque_status = cmd.enable[i]
            return True
        return False

    def _exec_sync_goal_current(self, cmd: SyncGoalCurrentCommand) -> bool:
        if not cmd.is_valid():
            self.logger.error("Sync set goal current failed: command is invalid.")
            return False
        reg = self._get_servo(cmd.ids[0]).control_table['GOAL_CURRENT']
        data = {id_: self._convert_to_bytes(cmd.currents[i], reg['LEN'])
                for i, id_ in enumerate(cmd.ids) if self._is_servo_registered(id_)}
        res = self._sync_write('GOAL_CURRENT', data)
        return self._check_communication(254, 'SYNC_GOAL_CURRENT', res)

    def _exec_sync_goal_position(self, cmd: SyncGoalPositionCommand) -> bool:
        if not (len(cmd.ids) == len(cmd.positions) == len(cmd.durations)):
            self.logger.error("Sync position command failed: list lengths do not match.")
            return False
        if cmd.current_limits:
            if len(cmd.current_limits) != len(cmd.ids):
                self.logger.error("Sync position command failed: current limits list length does not match IDs.")
                return False
            self.send_cmd(SyncGoalCurrentCommand(ids=cmd.ids, currents=cmd.current_limits))

        pos_to_send, duration_to_send = {}, {}
        for i, id_ in enumerate(cmd.ids):
            servo = self._get_servo(id_)
            pos_len = servo.control_table['GOAL_POSITION']['LEN']
            dur_len = servo.control_table['PROFILE_VELOCITY']['LEN']
            pos_to_send[id_] = self._convert_to_bytes(cmd.positions[i], pos_len)
            duration_to_send[id_] = self._convert_to_bytes(cmd.durations[i], dur_len)

        res1 = self._sync_write('PROFILE_VELOCITY', duration_to_send)
        res2 = self._sync_write('GOAL_POSITION', pos_to_send)
        return (self._check_communication(254, 'SYNC_VELOCITY', res1)
                and self._check_communication(254, 'SYNC_POSITION', res2))

    def _exec_generic_sync_write(self, cmd) -> bool:
        """Generic sync write for commands with ids + values + register."""
        if len(cmd.ids) != len(cmd.values):
            self.logger.error(f"Sync write '{cmd.register}' failed: list lengths do not match.")
            return False
        data = {}
        for i, id_ in enumerate(cmd.ids):
            servo = self._get_servo(id_)
            reg = servo.control_table[cmd.register]
            data[id_] = self._convert_to_bytes(cmd.values[i], reg['LEN'])
        res = self._sync_write(cmd.register, data)
        return self._check_communication(254, f'SYNC_{cmd.register}', res)

    # =================== Low-level Helpers ===================

    def _get_servo(self, id_: int) -> Servo:
        return self.servos[id_]

    def _is_servo_registered(self, id_: int) -> bool:
        return id_ in self.servos

    def _readTxRx(self, id_: int, reg: dict):
        length, addr = reg['LEN'], reg['ADDR']
        if length == 1: return self.packet_handler.read1ByteTxRx(self.port_handler, id_, addr)
        if length == 2: return self.packet_handler.read2ByteTxRx(self.port_handler, id_, addr)
        return self.packet_handler.read4ByteTxRx(self.port_handler, id_, addr)

    def _writeTxRx(self, id_: int, reg: dict, data: int):
        length, addr = reg['LEN'], reg['ADDR']
        if length == 1: return self.packet_handler.write1ByteTxRx(self.port_handler, id_, addr, data)
        if length == 2: return self.packet_handler.write2ByteTxRx(self.port_handler, id_, addr, data)
        return self.packet_handler.write4ByteTxRx(self.port_handler, id_, addr, data)

    def _sync_write(self, reg_name: str, data: Dict[int, List[int]]):
        if not data:
            return COMM_SUCCESS

        # Skip the wire entirely when a dedup-eligible payload is unchanged
        # (profile durations / current limits are constants on a periodic
        # control loop — resending them every cycle doubled the TX packets).
        dedup = reg_name in self.DEDUP_REGISTERS
        if dedup and self._last_sync_payload.get(reg_name) == data:
            return COMM_SUCCESS

        first_id = next(iter(data))
        reg = self._get_servo(first_id).control_table[reg_name]
        key = (reg['ADDR'], reg['LEN'])
        cached = self._sync_write_groups.get(key)
        if cached is None:
            group, known_ids = GroupSyncWrite(
                self.port_handler, self.packet_handler, reg['ADDR'], reg['LEN']), set()
            self._sync_write_groups[key] = (group, known_ids)
        else:
            group, known_ids = cached

        # Reuse the group across cycles: addParam only for new ids,
        # changeParam for the rest (the SDK's intended periodic pattern).
        stale = known_ids - data.keys()
        if stale:
            for id_ in stale:
                group.removeParam(id_)
            known_ids -= stale
        for id_, param_data in data.items():
            if id_ in known_ids:
                group.changeParam(id_, param_data)
            else:
                group.addParam(id_, param_data)
                known_ids.add(id_)

        result = group.txPacket()
        if dedup and result == COMM_SUCCESS:
            self._last_sync_payload[reg_name] = dict(data)
        return result

    def _sync_read(self, ids: Union[int, List[int]], reg_name: str) -> Dict[int, int]:
        """Synchronous read of one register from multiple servos (raw unsigned values)."""
        if isinstance(ids, int):
            ids = [ids]
        first_id = ids[0]
        reg = self._get_servo(first_id).control_table[reg_name]

        # Reuse the group handler when the id set is unchanged (the 100+ Hz
        # state loop reads the same ids every cycle; params persist across
        # txRxPacket calls, so re-adding them per call was pure overhead).
        key = (reg['ADDR'], reg['LEN'])
        ids_key = tuple(ids)
        cached = self._sync_read_groups.get(key)
        if cached is not None and cached[1] == ids_key:
            group = cached[0]
        else:
            group = GroupSyncRead(self.port_handler, self.packet_handler, reg['ADDR'], reg['LEN'])
            for id_ in ids:
                if not group.addParam(id_):
                    self.logger.error(f"[SyncRead] Failed to add param for ID {id_}.")
                    return {}
            self._sync_read_groups[key] = (group, ids_key)

        comm_result = group.txRxPacket()
        if comm_result != COMM_SUCCESS:
            self._check_communication(254, 'SYNC_READ_TXRX', comm_result)
            return {}

        results = {}
        for id_ in ids:
            if group.isAvailable(id_, reg['ADDR'], reg['LEN']):
                results[id_] = group.getData(id_, reg['ADDR'], reg['LEN'])
            else:
                self.logger.warning(f"[SyncRead] No data available for ID {id_}.")
                results[id_] = self.INVALID_INT_VAL
        return results

    def _bulk_write(self, write_requests: Dict[int, List[tuple]]) -> int:
        """
        Bulk write: {servo_id: [(reg_dict, value), ...], ...}
        Returns communication result code.
        """
        group = GroupBulkWrite(self.port_handler, self.packet_handler)
        for id_, commands in write_requests.items():
            for reg, value in commands:
                byte_value = self._convert_to_bytes(value, reg['LEN'])
                if not group.addParam(id_, reg['ADDR'], reg['LEN'], byte_value):
                    self.logger.error(f"[BulkWrite] Failed to add param for ID {id_} at address {reg['ADDR']}.")
                    return -1
        result = group.txPacket()
        group.clearParam()
        return result

    def _bulk_read(self, read_requests: Dict[int, List[Dict]]) -> Dict[int, Dict[str, int]]:
        """
        Bulk read: {servo_id: [reg_dict, ...], ...}
        Returns {servo_id: {register_name: value, ...}, ...}
        """
        group = GroupBulkRead(self.port_handler, self.packet_handler)
        for id_, regs in read_requests.items():
            for reg in regs:
                if not group.addParam(id_, reg['ADDR'], reg['LEN']):
                    self.logger.error(f"[BulkRead] Failed to add param for ID {id_} at address {reg['ADDR']}.")
                    return {}

        comm_result = group.txRxPacket()
        if comm_result != COMM_SUCCESS:
            self._check_communication(254, 'BULK_READ_TXRX', comm_result)
            return {}

        results = {}
        for id_, regs in read_requests.items():
            results[id_] = {}
            for reg in regs:
                name = next((n for n, d in self._get_servo(id_).control_table.items() if d['ADDR'] == reg['ADDR']), None)
                if group.isAvailable(id_, reg['ADDR'], reg['LEN']):
                    results[id_][name] = group.getData(id_, reg['ADDR'], reg['LEN'])
                else:
                    self.logger.warning(f"[BulkRead] No data available for ID {id_} at address {reg['ADDR']}.")
                    results[id_][name] = self.INVALID_INT_VAL

        group.clearParam()
        return results

    def _convert_to_bytes(self, data: int, length: int) -> List[int]:
        if length == 4: return [DXL_LOBYTE(DXL_LOWORD(data)), DXL_HIBYTE(DXL_LOWORD(data)), DXL_LOBYTE(DXL_HIWORD(data)), DXL_HIBYTE(DXL_HIWORD(data))]
        if length == 2: return [DXL_LOBYTE(data), DXL_HIBYTE(data)]
        if length == 1: return [data]
        return []

    def _check_communication(self, id_: int, cmd_name: str, result: int, error: int = 0) -> bool:
        if result == COMM_SUCCESS and error == 0:
            return True
        if not self.SUPPRESS_ERROR_MSG:
            err_msg = f"ID {id_} CMD '{cmd_name}': {self.packet_handler.getTxRxResult(result)}"
            if error != 0:
                err_msg += f" - {self.packet_handler.getRxPacketError(error)}"
            self.logger.error(err_msg)
        return False

    def _correct_to_signed(self, value: int, data_length_bytes: int) -> int:
        """Converts an unsigned int of N bytes to its signed equivalent."""
        if data_length_bytes == 1:
            return value - 256 if value > 127 else value
        if data_length_bytes == 2:
            return value - 65536 if value > 32767 else value
        if data_length_bytes == 4:
            return value - 4294967296 if value > 2147483647 else value
        return value