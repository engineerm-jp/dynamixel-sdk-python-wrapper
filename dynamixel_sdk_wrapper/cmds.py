
"""
Dynamixel command dataclasses.

Commands are organized by communication pattern:
  - SingleReadCommand:  read one register from one servo         → returns int
  - SyncReadCommand:    read one register from multiple servos   → returns Dict[int, int]
  - SingleWriteCommand: write one value to one servo             → returns bool
  - SyncWriteCommand:   write values to multiple servos          → returns bool
  - CompoundCommand:    multi-step operations                    → returns bool

Commands specify a `register` name (e.g. 'PRESENT_POSITION') instead of
hard-coded addresses, so the wrapper can resolve the actual addr/len from
each servo's model-specific control table at runtime.
"""

from dataclasses import dataclass, field
from typing import List


# ===================== Base Command Types =====================

class SingleReadCommand:
    """Read one register from one servo. Returns int."""
    pass

class SyncReadCommand:
    """Read one register from multiple servos. Returns Dict[int, int]."""
    pass

class BulkReadCommand:
    """Read multiple registers from multiple servos. Returns Dict[int, Dict[str, int]]."""
    pass

class SingleWriteCommand:
    """Write one value to one register on one servo. Returns bool."""
    pass

class SyncWriteCommand:
    """Write values to one register on multiple servos. Returns bool."""
    pass

class BulkWriteCommand:
    """Write multiple registers to multiple servos. Returns bool."""
    pass

class CompoundCommand:
    """Multi-step operation with dedicated handler logic. Returns bool."""
    pass


# ===================== Generic Commands =====================

@dataclass
class ReadRegisterCommand(SingleReadCommand):
    """Generic single read: specify any register name."""
    id: int = 0
    register: str = ''

@dataclass
class WriteRegisterCommand(SingleWriteCommand):
    """Generic RAM write: specify register name and value."""
    id: int = 0
    value: int = 0
    register: str = ''

@dataclass
class SyncWriteRegisterCommand(SyncWriteCommand):
    """Generic sync RAM write: specify register name and values per servo."""
    ids: List[int] = field(default_factory=list)
    values: List[int] = field(default_factory=list)
    register: str = ''

@dataclass
class GenericBulkWriteCommand(BulkWriteCommand):
    """
    Bulk write multiple registers to multiple servos.
    targets: {servo_id: [(register_name1, value1), (register_name2, value2), ...]}
    """
    targets: dict = field(default_factory=dict)


# ===================== Single Read Commands =====================

@dataclass
class ReadPositionCommand(SingleReadCommand):
    id: int = 0
    register: str = 'PRESENT_POSITION'

@dataclass
class ReadCurrentCommand(SingleReadCommand):
    id: int = 0
    register: str = 'PRESENT_CURRENT'

@dataclass
class ReadFirmwareCommand(SingleReadCommand):
    id: int = 0
    register: str = 'FIRMWARE_VERSION'

@dataclass
class ReadTemperatureCommand(SingleReadCommand):
    id: int = 0
    register: str = 'PRESENT_TEMPERATURE'

@dataclass
class ReadVelocityCommand(SingleReadCommand):
    id: int = 0
    register: str = 'PRESENT_VELOCITY'

@dataclass
class ReadPwmCommand(SingleReadCommand):
    id: int = 0
    register: str = 'PRESENT_PWM'

@dataclass
class ReadVoltageCommand(SingleReadCommand):
    id: int = 0
    register: str = 'PRESENT_INPUT_VOLTAGE'

@dataclass
class ReadModelNumberCommand(SingleReadCommand):
    id: int = 0
    register: str = 'MODEL_NUMBER'

@dataclass
class ReadMovingCommand(SingleReadCommand):
    id: int = 0
    register: str = 'MOVING'

@dataclass
class ReadMovingStatusCommand(SingleReadCommand):
    id: int = 0
    register: str = 'MOVING_STATUS'

@dataclass
class ReadHardwareErrorCommand(SingleReadCommand):
    id: int = 0
    register: str = 'HARDWARE_ERROR_STATUS'

@dataclass
class ReadHomingOffsetCommand(SingleReadCommand):
    id: int = 0
    register: str = 'HOMING_OFFSET'

@dataclass
class ReadRealtimeTickCommand(SingleReadCommand):
    id: int = 0
    register: str = 'REALTIME_TICK'

@dataclass
class ReadVelocityTrajectoryCommand(SingleReadCommand):
    id: int = 0
    register: str = 'VELOCITY_TRAJECTORY'

@dataclass
class ReadPositionTrajectoryCommand(SingleReadCommand):
    id: int = 0
    register: str = 'POSITION_TRAJECTORY'

@dataclass
class ReadBackupReadyCommand(SingleReadCommand):
    id: int = 0
    register: str = 'BACKUP_READY'


# ===================== Sync Read Commands =====================

@dataclass
class SyncReadPositionCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'PRESENT_POSITION'

@dataclass
class SyncReadVelocityCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'PRESENT_VELOCITY'

@dataclass
class SyncReadCurrentCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'PRESENT_CURRENT'

@dataclass
class SyncReadRegisterCommand(SyncReadCommand):
    """Generic sync read: specify any register name."""
    ids: List[int] = field(default_factory=list)
    register: str = ''

@dataclass
class GenericBulkReadCommand(BulkReadCommand):
    """
    Bulk read multiple registers from multiple servos.
    targets: {servo_id: [register_name1, register_name2, ...]}
    """
    targets: dict = field(default_factory=dict)

@dataclass
class SyncReadPwmCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'PRESENT_PWM'

@dataclass
class SyncReadVoltageCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'PRESENT_INPUT_VOLTAGE'

@dataclass
class SyncReadTemperatureCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'PRESENT_TEMPERATURE'

@dataclass
class SyncReadMovingCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'MOVING'

@dataclass
class SyncReadHardwareErrorCommand(SyncReadCommand):
    ids: List[int] = field(default_factory=list)
    register: str = 'HARDWARE_ERROR_STATUS'


# ===================== Single Write Commands (RAM) =====================

@dataclass
class GoalCurrentCommand(SingleWriteCommand):
    id: int = 0
    goal_mA: int = 700
    register: str = 'GOAL_CURRENT'

@dataclass
class ProfileTimeCommand(SingleWriteCommand):
    id: int = 0
    duration_ms: int = 1000
    register: str = 'PROFILE_VELOCITY'

@dataclass
class GoalVelocityCommand(SingleWriteCommand):
    id: int = 0
    value: int = 0
    register: str = 'GOAL_VELOCITY'

@dataclass
class GoalPwmCommand(SingleWriteCommand):
    id: int = 0
    value: int = 0
    register: str = 'GOAL_PWM'

@dataclass
class ProfileAccelerationCommand(SingleWriteCommand):
    id: int = 0
    value: int = 0
    register: str = 'PROFILE_ACCELERATION'

@dataclass
class LedCommand(SingleWriteCommand):
    id: int = 0
    value: int = 0
    register: str = 'LED'

@dataclass
class BusWatchdogCommand(SingleWriteCommand):
    id: int = 0
    value: int = 0  # 0 = disabled, 1-127 in 20 ms units
    register: str = 'BUS_WATCHDOG'

@dataclass
class StatusReturnLevelCommand(SingleWriteCommand):
    id: int = 0
    value: int = 2  # 0 = none, 1 = read-only, 2 = all
    register: str = 'STATUS_RETURN_LEVEL'


# ===================== Sync Write Commands =====================

@dataclass
class TorqueCommand(SyncWriteCommand):
    ids: List[int] = field(default_factory=list)
    enable: List[bool] = field(default_factory=list)
    register: str = 'TORQUE_ENABLE'

@dataclass
class SyncGoalCurrentCommand(SyncWriteCommand):
    ids: List[int] = field(default_factory=list)
    currents: List[int] = field(default_factory=list)
    register: str = 'GOAL_CURRENT'

    # Largest GOAL_CURRENT register range across the supported control tables
    # (XC330: 910, XM430-W350: 1193). Values beyond this would wrap in the
    # register; per-model clamping is the caller's responsibility (the
    # firmware CURRENT_LIMIT register is the hardware backstop).
    MAX_ABS_GOAL_CURRENT_LSB = 1193

    def is_valid(self) -> bool:
        return (len(self.ids) == len(self.currents)
                and all(-self.MAX_ABS_GOAL_CURRENT_LSB <= c <= self.MAX_ABS_GOAL_CURRENT_LSB
                        for c in self.currents))

@dataclass
class SyncGoalPositionCommand(SyncWriteCommand):
    """Also sets the profile and optionally current limits.

    Under a TIME-BASED profile (Drive Mode bit 2), ``durations`` is the
    total move time in ms and ``accels`` the acceleration ramp time in ms
    (firmware clamps it to half the duration). Give every servo in one
    command the SAME pair and their normalized trajectories are identical
    regardless of travel distance — which is what keeps mechanically
    coupled actuators (tendons on a shared joint) moving in lockstep.
    """
    ids: List[int] = field(default_factory=list)
    positions: List[int] = field(default_factory=list)
    durations: List[int] = field(default_factory=list)
    accels: List[int] = field(default_factory=list)
    current_limits: List[int] = field(default_factory=list)
    register: str = 'GOAL_POSITION'

@dataclass
class SyncGoalVelocityCommand(SyncWriteCommand):
    ids: List[int] = field(default_factory=list)
    values: List[int] = field(default_factory=list)
    register: str = 'GOAL_VELOCITY'

@dataclass
class SyncGoalPwmCommand(SyncWriteCommand):
    ids: List[int] = field(default_factory=list)
    values: List[int] = field(default_factory=list)
    register: str = 'GOAL_PWM'

@dataclass
class SyncLedCommand(SyncWriteCommand):
    ids: List[int] = field(default_factory=list)
    values: List[int] = field(default_factory=list)
    register: str = 'LED'


# ===================== Compound Commands =====================

@dataclass
class GoalPositionCommand(CompoundCommand):
    """Sets current limit + profile duration + goal position for one servo."""
    id: int = 0
    position: int = 0
    duration_ms: int = 1000
    current_limit_mA: int = 800

@dataclass
class OperatingModeCommand(CompoundCommand):
    """Disables torque, then sets operating mode."""
    ids: List[int] = field(default_factory=list)
    mode: str = 'position' # 'position', 'velocity', 'current', 'extended_pos', 'pwm', 'current_pos'

@dataclass
class DriveModeCommand(CompoundCommand):
    """Read-modify-write a specific bit in the drive mode register."""
    id: int = 0
    mode: str = ''     # 'reverse_mode', 'profile', 'torque'
    enable: bool = False

@dataclass
class StartupConfigCommand(CompoundCommand):
    """Read-modify-write startup configuration register."""
    id: int = 0
    restore_ram: bool = True
    torque_enable: bool = False

@dataclass
class PositionLimitCommand(CompoundCommand):
    """Sets min and max position limits."""
    id: int = 0
    min_pos: int = 0
    max_pos: int = 0

@dataclass
class RebootCommand(CompoundCommand):
    """Reboots a servo."""
    id: int = 0


# --- EEPROM compound commands (torque is managed automatically) ---

@dataclass
class EepromWriteCommand(CompoundCommand):
    """Base for single-register EEPROM writes.

    Subclasses set `register` and optionally `servo_attr` (the Servo
    attribute to cache the written value on).  The wrapper's
    `_exec_eeprom_write` handles torque-disable/write/re-enable.
    """
    id: int = 0
    value: int = 0
    register: str = ''
    servo_attr: str = None

@dataclass
class HomingOffsetCommand(EepromWriteCommand):
    """Sets homing offset (EEPROM)."""
    register: str = 'HOMING_OFFSET'
    servo_attr: str = 'homing_offset'

@dataclass
class ReturnDelayCommand(EepromWriteCommand):
    """Sets Return Delay Time (EEPROM), in 2 us units.

    The factory default is 250 == 500 us of dead bus time BEFORE each
    status packet. On a sync read every servo pays it in series, so a
    13-servo chain wastes 6.5 ms per read regardless of baud rate — far
    more than the packets themselves cost. 0 is correct for a modern
    host; the value exists for microcontrollers too slow to turn the
    line around.
    """
    value: int = 0
    register: str = 'RETURN_DELAY_TIME'


@dataclass
class CurrentLimitCommand(EepromWriteCommand):
    """Sets current limit in mA (EEPROM)."""
    value: int = 910
    register: str = 'CURRENT_LIMIT'
    servo_attr: str = 'current_limit'

@dataclass
class VelocityLimitCommand(EepromWriteCommand):
    """Sets velocity limit (EEPROM)."""
    register: str = 'VELOCITY_LIMIT'
    servo_attr: str = 'velocity_limit'

@dataclass
class TemperatureLimitCommand(EepromWriteCommand):
    """Sets temperature limit in degrees C (EEPROM)."""
    value: int = 72
    register: str = 'TEMPERATURE_LIMIT'
    servo_attr: str = 'temperature_limit'

@dataclass
class VoltageLimitCommand(CompoundCommand):
    """Sets min and max voltage limits in 0.1 V units (EEPROM)."""
    id: int = 0
    min_voltage: int = 31
    max_voltage: int = 70

@dataclass
class PwmLimitCommand(EepromWriteCommand):
    """Sets PWM limit (EEPROM)."""
    value: int = 885
    register: str = 'PWM_LIMIT'
    servo_attr: str = 'pwm_limit'

@dataclass
class MovingThresholdCommand(EepromWriteCommand):
    """Sets moving threshold (EEPROM)."""
    value: int = 10
    register: str = 'MOVING_THRESHOLD'
    servo_attr: str = 'moving_threshold'

@dataclass
class ShutdownConfigCommand(EepromWriteCommand):
    """Sets shutdown error bitmask (EEPROM)."""
    value: int = 52
    register: str = 'SHUTDOWN'

@dataclass
class BaudRateConfigCommand(EepromWriteCommand):
    """Sets baud rate index (EEPROM). 0=9600, 1=57600, 2=115200, 3=1M, 4=2M, 5=3M, 6=4M, 7=4.5M."""
    value: int = 1
    register: str = 'BAUD_RATE'

@dataclass
class PwmSlopeCommand(EepromWriteCommand):
    """Sets PWM slope in mV/ms (EEPROM)."""
    value: int = 140
    register: str = 'PWM_SLOPE'

@dataclass
class SecondaryIdCommand(EepromWriteCommand):
    """Sets secondary (shadow) ID (EEPROM). 253 = disabled."""
    value: int = 253
    register: str = 'SECONDARY_ID'

