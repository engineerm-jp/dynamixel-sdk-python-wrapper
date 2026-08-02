# dynamixel-sdk-wrapper

A command-driven Python wrapper for the [Dynamixel SDK](https://github.com/ROBOTIS-GIT/DynamixelSDK).
Instead of managing raw register addresses and byte conversions, you create **command
objects** and pass them to a single `send_cmd()` entry point.

- **Python:** 3.8+ &nbsp;•&nbsp; **Protocol:** Dynamixel Protocol 2.0 &nbsp;•&nbsp; **License:** MIT &nbsp;•&nbsp; **Version:** 0.2.0

```python
from dynamixel_sdk_wrapper import DynamixelSDKWrapper, ServoConfig
from dynamixel_sdk_wrapper.cmds import GoalPositionCommand

dxl = DynamixelSDKWrapper(port="/dev/ttyUSB0", baudrate=4_000_000)
dxl.open_port()
dxl.add_servo([ServoConfig(id_=1, model="XC330", name="joint_1")])
dxl.send_cmd(GoalPositionCommand(id=1, position=2048, duration_ms=1000))
```

## Contents

- [Features](#features)
- [Supported models](#supported-models)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Usage guide](#usage-guide)
- [Command reference](#command-reference)
- [Return values and error handling](#return-values-and-error-handling)
- [Performance notes](#performance-notes)
- [Hardware notes](#hardware-notes)
- [Adding a new servo model](#adding-a-new-servo-model)
- [Project structure](#project-structure)
- [Versioning and compatibility](#versioning-and-compatibility)
- [License](#license)

## Features

- **Command-based API** — read, write, sync-read, sync-write, bulk-read/write, and
  compound operations through typed dataclass commands, all dispatched by one
  `send_cmd()` method.
- **Model-aware** — register addresses and lengths are resolved from per-model
  control tables at runtime; commands name registers (`'PRESENT_POSITION'`), never
  addresses.
- **Automatic signed conversion** — position, velocity, current, and homing-offset
  values are sign-extended correctly in both directions.
- **Servo lifecycle management** — `add_servo()` handles ping, operating mode,
  drive mode, limits, and EEPROM configuration with per-servo retries and a
  readable configuration log.
- **Control-loop friendly** — `GroupSyncRead`/`GroupSyncWrite` handlers are created
  once and reused across cycles, and unchanged periodic payloads are deduplicated
  off the wire (see [Performance notes](#performance-notes)).
- **Extensible** — add new servo models by adding one dict to
  `control_tables.py`; generic register commands cover anything without a
  dedicated command class.
- **Dependency-light** — `dynamixel-sdk` (which brings `pyserial`) and the
  standard library only. No numpy.

## Supported models

| Model      | Status       | Control table |
|------------|--------------|---------------|
| XC330      | ✅ Supported | [e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xc330-t288/#control-table) |
| XM430-W350 | ✅ Supported | [e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xm430-w350/#control-table) |

Other Protocol 2.0 servos in the X-series generally work after
[adding their control table](#adding-a-new-servo-model).

## Installation

### Prerequisites

- Python 3.8+
- A Dynamixel-compatible USB adapter (e.g. U2D2)

### Install from source (recommended)

```bash
git clone https://github.com/engineerm-jp/dynamixel-sdk-python-wrapper.git
cd dynamixel-sdk-python-wrapper
pip install .
```

Or install a pinned ref directly (reproducible — use a tag/commit, not a branch):

```bash
pip install "git+https://github.com/engineerm-jp/dynamixel-sdk-python-wrapper.git@v0.2.0"
```

### Install in development/editable mode

```bash
git clone https://github.com/engineerm-jp/dynamixel-sdk-python-wrapper.git
cd dynamixel-sdk-python-wrapper
pip install -e ".[dev]"
```

This installs the package as a link to your local copy — changes take effect
immediately without reinstalling. The `[dev]` extra adds pytest, ruff, and mypy.

### Ubuntu / ROS 2 note (numpy conflicts)

This package depends on `dynamixel-sdk` (which brings `pyserial`) and the
standard library **only — it does not use numpy**. If `pip install` inside a
ROS environment starts downloading or upgrading numpy, that pressure comes
from *other* packages in the same command, not from this wrapper.

On ROS 2 Humble (Ubuntu 22.04) keep the system numpy: ROS's compiled Python
modules are built against apt's numpy 1.21, and letting pip upgrade to
numpy ≥ 2 breaks them. If that has already happened, recover with
`pip install "numpy<2"` and check the environment with `pip check`.

## Quick start

```python
from dynamixel_sdk_wrapper import DynamixelSDKWrapper, ServoConfig
from dynamixel_sdk_wrapper.cmds import (
    TorqueCommand,
    ReadPositionCommand,
    GoalPositionCommand,
)

# 1. Create wrapper and open port
dxl = DynamixelSDKWrapper(port="COM3", baudrate=115200)  # Linux: "/dev/ttyUSB0"
dxl.open_port()

# 2. Register servos
dxl.add_servo([
    ServoConfig(id_=1, model="XC330", name="base_joint", op_mode="extended_pos"),
    ServoConfig(id_=2, model="XC330", name="elbow", op_mode="extended_pos"),
])

# 3. Enable torque
dxl.send_cmd(TorqueCommand(ids=[1, 2], enable=[True, True]))

# 4. Read position
pos = dxl.send_cmd(ReadPositionCommand(id=1))
print(f"Servo 1 position: {pos}")

# 5. Move servo
dxl.send_cmd(GoalPositionCommand(id=1, position=2048, duration_ms=1000, current_limit_mA=500))

# 6. Clean up
dxl.send_cmd(TorqueCommand(ids=[1, 2], enable=[False, False]))
dxl.close_port()
```

A complete runnable script is in [`examples/basic_usage.py`](examples/basic_usage.py).

## Usage guide

### ServoConfig

`add_servo()` takes a list of `ServoConfig` objects. Every field except `id_` and
`model` is optional; fields left as `None` are not written to the servo.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `id_` | `int` | required | Servo ID on the bus |
| `model` | `str` | required | Model name; must match a key in `CONTROL_TABLE` |
| `name` | `str` | `''` | Human-readable label used in logs |
| `op_mode` | `str` | `'extended_pos'` | Operating mode (see table below) |
| `reverse` | `bool` | `False` | Firmware reverse rotation (Drive Mode bit 0) — see [Hardware notes](#hardware-notes) |
| `pos_limit` | `(int, int)` | `None` | (min, max) position limits, raw ticks (EEPROM) |
| `current_limit` | `int` | `None` | Current limit (EEPROM) |
| `velocity_limit` | `int` | `None` | Velocity limit, raw units (EEPROM) |
| `temperature_limit` | `int` | `None` | Max temperature, °C (EEPROM) |
| `pwm_limit` | `int` | `None` | PWM limit, raw units (EEPROM) |
| `voltage_limit` | `(int, int)` | `None` | (min, max) voltage limits, 0.1 V units (EEPROM) |
| `homing_offset` | `int` | `None` | Homing offset, raw ticks (EEPROM) |
| `moving_threshold` | `int` | `None` | Moving threshold, raw units (EEPROM) |
| `shutdown` | `int` | `None` | Shutdown error bitmask (EEPROM) |
| `profile_acceleration` | `int` | `None` | Profile acceleration, raw units (RAM) |
| `led` | `bool` | `None` | Initial LED state |
| `bus_watchdog` | `int` | `None` | Bus Watchdog: 0 = disabled, 1–127 in 20 ms units — see [Hardware notes](#hardware-notes) |

During registration each servo is pinged, torque-disabled, switched to `op_mode`,
put in **time-based profile** drive mode, and configured with every limit you
provided. Each servo gets up to 5 attempts; a per-servo summary is logged at the
end.

#### Operating modes

| Mode          | String value     | Description                       |
|---------------|------------------|-----------------------------------|
| Current       | `"current"`      | Current (torque) control          |
| Velocity      | `"velocity"`     | Velocity control                  |
| Position      | `"position"`     | Position control (0–4095)         |
| Extended Pos. | `"extended_pos"` | Multi-turn position control       |
| Current+Pos.  | `"current_pos"`  | Position control with current cap |
| PWM           | `"pwm"`          | Direct PWM control                |

### Reading values

```python
from dynamixel_sdk_wrapper.cmds import (
    ReadPositionCommand,
    ReadCurrentCommand,
    ReadTemperatureCommand,
    SyncReadPositionCommand,
    GenericBulkReadCommand,
)

# Single servo read
position = dxl.send_cmd(ReadPositionCommand(id=1))
current  = dxl.send_cmd(ReadCurrentCommand(id=1))
temp     = dxl.send_cmd(ReadTemperatureCommand(id=1))

# Sync read: one register from multiple servos in one transaction
positions = dxl.send_cmd(SyncReadPositionCommand(ids=[1, 2, 3]))
# → {1: 2048, 2: 1024, 3: 3072}

# Bulk read: different registers per servo in one transaction
state = dxl.send_cmd(GenericBulkReadCommand(targets={
    1: ["PRESENT_POSITION", "PRESENT_CURRENT"],
    2: ["PRESENT_TEMPERATURE"],
}))
# → {1: {"PRESENT_POSITION": 2048, "PRESENT_CURRENT": -12}, 2: {"PRESENT_TEMPERATURE": 34}}
```

### Writing values

```python
from dynamixel_sdk_wrapper.cmds import (
    GoalPositionCommand,
    GoalCurrentCommand,
    ProfileTimeCommand,
    TorqueCommand,
)

# Move with current limit and duration (compound: current + profile + position)
dxl.send_cmd(GoalPositionCommand(id=1, position=2048, duration_ms=1500, current_limit_mA=600))

# Set goal current directly (requires 'current' or 'current_pos' mode)
dxl.send_cmd(GoalCurrentCommand(id=1, goal_mA=300))

# Set profile duration
dxl.send_cmd(ProfileTimeCommand(id=1, duration_ms=2000))

# Torque on/off (per servo)
dxl.send_cmd(TorqueCommand(ids=[1, 2], enable=[True, False]))
```

### Sync write (multiple servos)

```python
from dynamixel_sdk_wrapper.cmds import (
    SyncGoalPositionCommand,
    SyncGoalCurrentCommand,
    SyncWriteRegisterCommand,
)

# Move multiple servos simultaneously (writes PROFILE_VELOCITY, then GOAL_POSITION)
dxl.send_cmd(SyncGoalPositionCommand(
    ids=[1, 2, 3],
    positions=[2048, 1024, 3072],
    durations=[1000, 1500, 800],
    current_limits=[500, 500, 500],   # optional; only for current-based modes
))

# Set goal currents for multiple servos
dxl.send_cmd(SyncGoalCurrentCommand(ids=[1, 2], currents=[300, 400]))

# Generic sync write to any RAM register
dxl.send_cmd(SyncWriteRegisterCommand(ids=[1, 2], values=[5, 5], register="BUS_WATCHDOG"))
```

### EEPROM configuration at runtime

EEPROM commands automatically disable torque before writing and re-enable it
afterward:

```python
from dynamixel_sdk_wrapper.cmds import (
    PositionLimitCommand,
    CurrentLimitCommand,
    HomingOffsetCommand,
    OperatingModeCommand,
)

dxl.send_cmd(PositionLimitCommand(id=1, min_pos=0, max_pos=4095))
dxl.send_cmd(CurrentLimitCommand(id=1, value=800))
dxl.send_cmd(HomingOffsetCommand(id=1, value=100))
dxl.send_cmd(OperatingModeCommand(ids=[1, 2], mode="position"))
```

> EEPROM has a limited write-endurance — configure once at startup rather than
> inside a control loop.

### Rebooting a servo

A reboot clears a latched hardware error, drops torque, and resets all RAM
registers (operating mode, watchdog, goals) to their power-on values; EEPROM
(homing offsets, limits) survives. Reconfigure RAM state after rebooting:

```python
from dynamixel_sdk_wrapper.cmds import RebootCommand

dxl.send_cmd(RebootCommand(id=1))
```

## Command reference

All commands are dataclasses imported from `dynamixel_sdk_wrapper.cmds`.
`send_cmd()` dispatches on the command's base class.

### Single read → `int`

| Command | Register | Notes |
|---------|----------|-------|
| `ReadPositionCommand` | `PRESENT_POSITION` | Signed |
| `ReadVelocityCommand` | `PRESENT_VELOCITY` | Signed |
| `ReadCurrentCommand` | `PRESENT_CURRENT` | Signed |
| `ReadPwmCommand` | `PRESENT_PWM` | |
| `ReadTemperatureCommand` | `PRESENT_TEMPERATURE` | °C |
| `ReadVoltageCommand` | `PRESENT_INPUT_VOLTAGE` | 0.1 V units |
| `ReadFirmwareCommand` | `FIRMWARE_VERSION` | |
| `ReadModelNumberCommand` | `MODEL_NUMBER` | |
| `ReadMovingCommand` | `MOVING` | 0/1 |
| `ReadMovingStatusCommand` | `MOVING_STATUS` | Bitfield |
| `ReadHardwareErrorCommand` | `HARDWARE_ERROR_STATUS` | Error bitmask |
| `ReadHomingOffsetCommand` | `HOMING_OFFSET` | Signed |
| `ReadRealtimeTickCommand` | `REALTIME_TICK` | |
| `ReadVelocityTrajectoryCommand` | `VELOCITY_TRAJECTORY` | |
| `ReadPositionTrajectoryCommand` | `POSITION_TRAJECTORY` | |
| `ReadBackupReadyCommand` | `BACKUP_READY` | |
| `ReadRegisterCommand` | any | Generic: pass `register=` by name |

### Sync read → `Dict[int, int]`

| Command | Register |
|---------|----------|
| `SyncReadPositionCommand` | `PRESENT_POSITION` |
| `SyncReadVelocityCommand` | `PRESENT_VELOCITY` |
| `SyncReadCurrentCommand` | `PRESENT_CURRENT` |
| `SyncReadPwmCommand` | `PRESENT_PWM` |
| `SyncReadTemperatureCommand` | `PRESENT_TEMPERATURE` |
| `SyncReadVoltageCommand` | `PRESENT_INPUT_VOLTAGE` |
| `SyncReadMovingCommand` | `MOVING` |
| `SyncReadHardwareErrorCommand` | `HARDWARE_ERROR_STATUS` |
| `SyncReadRegisterCommand` | any (generic) |

### Bulk read → `Dict[int, Dict[str, int]]`

| Command | Description |
|---------|-------------|
| `GenericBulkReadCommand` | `targets={id: [register_name, ...]}` — different registers per servo, one transaction |

### Single write (RAM) → `bool`

| Command | Register | Notes |
|---------|----------|-------|
| `GoalCurrentCommand` | `GOAL_CURRENT` | Requires a current-based mode |
| `GoalVelocityCommand` | `GOAL_VELOCITY` | |
| `GoalPwmCommand` | `GOAL_PWM` | |
| `ProfileTimeCommand` | `PROFILE_VELOCITY` | Duration in ms (time-based profile) |
| `ProfileAccelerationCommand` | `PROFILE_ACCELERATION` | |
| `LedCommand` | `LED` | 0/1 |
| `BusWatchdogCommand` | `BUS_WATCHDOG` | 0 = off, 1–127 × 20 ms |
| `StatusReturnLevelCommand` | `STATUS_RETURN_LEVEL` | 0 = none, 1 = reads only, 2 = all |
| `WriteRegisterCommand` | any | Generic: pass `register=` by name |

### Sync write → `bool`

| Command | Register | Notes |
|---------|----------|-------|
| `TorqueCommand` | `TORQUE_ENABLE` | Per-servo enable list |
| `SyncGoalPositionCommand` | `GOAL_POSITION` | Also writes `PROFILE_VELOCITY` (+ optional current limits) |
| `SyncGoalCurrentCommand` | `GOAL_CURRENT` | Values validated against ±1193 LSB (largest supported register range) |
| `SyncGoalVelocityCommand` | `GOAL_VELOCITY` | |
| `SyncGoalPwmCommand` | `GOAL_PWM` | |
| `SyncLedCommand` | `LED` | |
| `SyncWriteRegisterCommand` | any | Generic: per-servo values for one register |

### Bulk write → `bool`

| Command | Description |
|---------|-------------|
| `GenericBulkWriteCommand` | `targets={id: [(register_name, value), ...]}` — different registers per servo, one transaction |

### Compound (multi-step) → `bool`

| Command | Description |
|---------|-------------|
| `GoalPositionCommand` | Current limit + profile duration + goal position for one servo |
| `OperatingModeCommand` | Torque off, then set operating mode |
| `DriveModeCommand` | Read-modify-write one Drive Mode bit (`'reverse_mode'`, `'profile'`, `'torque'`) |
| `StartupConfigCommand` | Read-modify-write Startup Configuration (torque-on / RAM-restore bits) |
| `PositionLimitCommand` | Set min + max position limits |
| `RebootCommand` | Reboot a servo (clears error latch, resets RAM) |
| `VoltageLimitCommand` | Set min + max voltage limits (EEPROM, torque-managed) |

### EEPROM writes (torque managed automatically) → `bool`

| Command | Register |
|---------|----------|
| `HomingOffsetCommand` | `HOMING_OFFSET` |
| `CurrentLimitCommand` | `CURRENT_LIMIT` |
| `VelocityLimitCommand` | `VELOCITY_LIMIT` |
| `TemperatureLimitCommand` | `TEMPERATURE_LIMIT` |
| `PwmLimitCommand` | `PWM_LIMIT` |
| `MovingThresholdCommand` | `MOVING_THRESHOLD` |
| `ShutdownConfigCommand` | `SHUTDOWN` |
| `BaudRateConfigCommand` | `BAUD_RATE` (0=9600 … 7=4.5M) |
| `PwmSlopeCommand` | `PWM_SLOPE` |
| `SecondaryIdCommand` | `SECONDARY_ID` (253 = disabled) |

> Units for goal/limit values are the servo's raw register LSBs unless a command
> field says otherwise; consult the model's e-Manual control table for LSB scale
> (e.g. `GOAL_CURRENT` is ≈1 mA/LSB on XC330 but 2.69 mA/LSB on XM430-W350).

## Return values and error handling

`send_cmd()` never raises on communication failure — it returns a sentinel:

| Command family | Success | Failure |
|----------------|---------|---------|
| Single read | `int` (signed-corrected) | `-1` (`DynamixelSDKWrapper.INVALID_INT_VAL`) |
| Sync / bulk read | dict | `{}` (whole transaction failed) or `-1` per missing servo |
| All writes / compound | `True` | `False` |

Values from `PRESENT_POSITION`, `PRESENT_VELOCITY`, `PRESENT_CURRENT`,
`GOAL_*`, and `HOMING_OFFSET` are automatically converted from the wire's
unsigned representation to signed Python ints.

SDK-level error messages are suppressed by default; enable them while
debugging:

```python
dxl.suppress_error_msg(False)   # log packet errors via logging
```

Note that `-1` is also a legal signed reading for some registers — when a read
of a signed register genuinely matters, treat `-1` with suspicion only alongside
other failures, or check `ReadHardwareErrorCommand`.

## Performance notes

The wrapper is designed to sit inside a 100+ Hz control loop:

- **Group handler reuse.** `GroupSyncWrite`/`GroupSyncRead` objects are created
  once per `(address, length)` and reused across cycles with
  `addParam`/`changeParam`/`removeParam`, the SDK's intended periodic pattern.
  Handlers are rebuilt automatically when the servo set changes (`add_servo`).
- **Write deduplication.** Sync writes to registers listed in
  `DynamixelSDKWrapper.DEDUP_REGISTERS` (`PROFILE_VELOCITY`, `GOAL_CURRENT`) are
  skipped entirely when the payload is byte-identical to the last successful
  write — on a periodic loop these are usually constants, and each skip saves a
  full wire packet. The cache is invalidated automatically by any compound
  command (torque, op-mode, reboot, …) and by `add_servo`.
- **Manual cache invalidation.** If something outside the wrapper may have
  changed those registers (power cycle, another master on the bus, firmware
  watchdog trip), force the next write onto the wire:

  ```python
  dxl.invalidate_write_cache()
  ```

- **Prefer sync/bulk commands** over per-servo loops: one transaction for N
  servos instead of N round-trips.

## Hardware notes

- **USB latency timer (FTDI adapters, Linux).** The kernel default of 16 ms
  caps any request-response bus at ~60 Hz. Set it to 1 ms:

  ```bash
  echo 1 | sudo tee /sys/bus/usb-serial/devices/ttyUSB0/latency_timer
  ```

- **Bus Watchdog.** When `ServoConfig.bus_watchdog` (or `BusWatchdogCommand`)
  is set to 1–127, the *servo firmware* halts motion if no instruction packet
  arrives within `value × 20 ms` — a crashed host or unplugged cable stops the
  motor with no software in the loop. Disable it (value 0) before intentionally
  pausing traffic (e.g. calibration holds), and re-arm afterwards.

- **Reverse mode vs. Homing Offset.** Per the ROBOTIS e-Manual, Homing
  Offset(20) is **not** sign-flipped by Drive Mode(10) reverse. If you calibrate
  homing offsets from raw ticks, keep every servo in Normal drive mode
  (`reverse=False`) and handle direction flips in software instead.

- **Hardware error latch.** When a `SHUTDOWN`-listed error trips (overload,
  overheat, voltage, …), the firmware torques the servo off and ignores goal
  writes *silently* — poll `SyncReadHardwareErrorCommand` if you need to detect
  it. The latch is cleared only by `RebootCommand` or a power cycle.

## Adding a new servo model

Open `dynamixel_sdk_wrapper/control_tables.py` and add an entry with the
register map from the model's [ROBOTIS e-Manual](https://emanual.robotis.com/docs/en/dxl/):

```python
CONTROL_TABLE['XL430'] = {
    'MODEL_NUMBER':      {'ADDR': 0,   'LEN': 2},
    'FIRMWARE_VERSION':  {'ADDR': 6,   'LEN': 1},
    'ID':                {'ADDR': 7,   'LEN': 1},
    # ... all registers used by the commands you need
    'TORQUE_ENABLE':     {'ADDR': 64,  'LEN': 1},
    'GOAL_POSITION':     {'ADDR': 116, 'LEN': 4},
    'PRESENT_POSITION':  {'ADDR': 132, 'LEN': 4},
}
```

Then use the model name in `ServoConfig`:

```python
ServoConfig(id_=1, model="XL430")
```

## Project structure

```
dynamixel-sdk-python-wrapper/
├── dynamixel_sdk_wrapper/
│   ├── __init__.py          # Public API exports (__version__ lives here)
│   ├── wrapper.py           # DynamixelSDKWrapper, ServoConfig, Servo
│   ├── cmds.py              # All command dataclasses
│   └── control_tables.py    # Per-model register tables
├── examples/
│   └── basic_usage.py       # Runnable end-to-end example
├── pyproject.toml           # Package metadata & dependencies
├── LICENSE
└── README.md
```

## Versioning and compatibility

Releases are tagged `vX.Y.Z`; install a pinned tag or commit (never a moving
branch) when reproducibility matters:

```bash
pip install "git+https://github.com/engineerm-jp/dynamixel-sdk-python-wrapper.git@v0.2.0"
```

The public API is everything importable from `dynamixel_sdk_wrapper` and every
command class in `dynamixel_sdk_wrapper.cmds`. Sentinel return values
(`-1` / `{}` / `False`) and the `send_cmd()` dispatch contract are stable within
a minor series.

## License

[MIT](LICENSE)
