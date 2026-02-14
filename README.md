# Dynamixel SDK Python Wrapper

A command-driven Python wrapper for the [Dynamixel SDK](https://github.com/ROBOTIS-GIT/DynamixelSDK). Instead of managing raw register addresses and byte conversions, you create **command objects** and pass them to a single `send_cmd()` entry point.

## Features

- **Command-based API** — read, write, sync-read, sync-write, and compound operations through typed dataclass commands
- **Model-aware** — register addresses and lengths are resolved from per-model control tables
- **Automatic signed conversion** — position, velocity, and current values are correctly sign-extended
- **Servo lifecycle management** — `add_servo()` handles ping, mode setting, limits, and EEPROM configuration with retries
- **Extensible** — add new servo models by adding entries to the control table dict

## Supported Models

| Model       | Status |
|-------------|--------|
| XC330       | ✅ Supported |
| XM430-W350  | ✅ Supported |

> To add a new model, add its control table to `dynamixel_sdk_wrapper/control_tables.py`.

---

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

### Install in development/editable mode

If you plan to modify the wrapper code:

```bash
git clone https://github.com/engineerm-jp/dynamixel-sdk-python-wrapper.git
cd dynamixel-sdk-python-wrapper
pip install -e .
```

This installs the package as a link to your local copy — changes take effect immediately without reinstalling.

---

## Quick Start

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

---

## Usage Guide

### ServoConfig Options

When registering servos with `add_servo()`, you can configure:

```python
ServoConfig(
    id_=1,                      # Servo ID on the bus
    model="XC330",              # Model name (must match a control table)
    name="my_servo",            # Human-readable label (for logs)
    op_mode="extended_pos",     # Operating mode (see table below)
    reverse=False,              # Reverse rotation direction
    pos_limit=(0, 4095),        # (min, max) position limits
    current_limit=500,          # Current limit in mA
    velocity_limit=100,         # Velocity limit
    temperature_limit=60,       # Max temperature in °C
    homing_offset=0,            # Homing offset in raw ticks
    profile_acceleration=50,    # Profile acceleration
    led=True,                   # Turn LED on at startup
)
```

#### Operating Modes

| Mode            | String value      | Description                       |
|-----------------|-------------------|-----------------------------------|
| Current         | `"current"`       | Current (torque) control          |
| Velocity        | `"velocity"`      | Velocity control                  |
| Position        | `"position"`      | Position control (0–4095)         |
| Extended Pos.   | `"extended_pos"`  | Multi-turn position control       |
| Current+Pos.    | `"current_pos"`   | Position control with current cap |
| PWM             | `"pwm"`           | Direct PWM control                |

### Reading Values

```python
from dynamixel_sdk_wrapper.cmds import (
    ReadPositionCommand,
    ReadCurrentCommand,
    ReadTemperatureCommand,
    ReadVelocityCommand,
    SyncReadPositionCommand,
)

# Single servo read
position = dxl.send_cmd(ReadPositionCommand(id=1))
current  = dxl.send_cmd(ReadCurrentCommand(id=1))
temp     = dxl.send_cmd(ReadTemperatureCommand(id=1))
velocity = dxl.send_cmd(ReadVelocityCommand(id=1))

# Sync read (multiple servos at once)
positions = dxl.send_cmd(SyncReadPositionCommand(ids=[1, 2, 3]))
# Returns: {1: 2048, 2: 1024, 3: 3072}
```

### Writing Values

```python
from dynamixel_sdk_wrapper.cmds import (
    GoalPositionCommand,
    GoalCurrentCommand,
    ProfileTimeCommand,
    LedCommand,
    TorqueCommand,
)

# Move with current limit and duration
dxl.send_cmd(GoalPositionCommand(id=1, position=2048, duration_ms=1500, current_limit_mA=600))

# Set goal current directly (requires current or current_pos mode)
dxl.send_cmd(GoalCurrentCommand(id=1, goal_mA=300))

# Set profile duration
dxl.send_cmd(ProfileTimeCommand(id=1, duration_ms=2000))

# Toggle LED
dxl.send_cmd(LedCommand(id=1, value=1))

# Torque on/off
dxl.send_cmd(TorqueCommand(ids=[1, 2], enable=[True, False]))
```

### Sync Write (Multiple Servos)

```python
from dynamixel_sdk_wrapper.cmds import (
    SyncGoalPositionCommand,
    SyncGoalCurrentCommand,
)

# Move multiple servos simultaneously
dxl.send_cmd(SyncGoalPositionCommand(
    ids=[1, 2, 3],
    positions=[2048, 1024, 3072],
    durations=[1000, 1500, 800],
    current_limits=[500, 500, 500],
))

# Set currents for multiple servos
dxl.send_cmd(SyncGoalCurrentCommand(ids=[1, 2], currents=[300, 400]))
```

### EEPROM Configuration at Runtime

EEPROM commands automatically disable torque before writing and re-enable it afterward:

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

### Reboot a Servo

```python
from dynamixel_sdk_wrapper.cmds import RebootCommand

dxl.send_cmd(RebootCommand(id=1))
```

---

## Command Reference

All commands are dataclasses imported from `dynamixel_sdk_wrapper.cmds`.

| Category         | Command                      | Returns          | Description                            |
|------------------|------------------------------|------------------|----------------------------------------|
| **Single Read**  | `ReadPositionCommand`        | `int`            | Present position                       |
|                  | `ReadCurrentCommand`         | `int`            | Present current (mA)                   |
|                  | `ReadVelocityCommand`        | `int`            | Present velocity                       |
|                  | `ReadTemperatureCommand`     | `int`            | Present temperature (°C)               |
|                  | `ReadVoltageCommand`         | `int`            | Present input voltage (0.1V)           |
|                  | `ReadFirmwareCommand`        | `int`            | Firmware version                       |
|                  | `ReadMovingCommand`          | `int`            | Moving flag (0/1)                      |
|                  | `ReadHardwareErrorCommand`   | `int`            | Hardware error bitmask                 |
|                  | `ReadRegisterCommand`        | `int`            | Generic: any register by name          |
| **Sync Read**    | `SyncReadPositionCommand`    | `Dict[int, int]` | Positions for multiple servos          |
|                  | `SyncReadCurrentCommand`     | `Dict[int, int]` | Currents for multiple servos           |
|                  | `SyncReadVelocityCommand`    | `Dict[int, int]` | Velocities for multiple servos         |
|                  | `SyncReadTemperatureCommand` | `Dict[int, int]` | Temperatures for multiple servos       |
|                  | `SyncReadRegisterCommand`    | `Dict[int, int]` | Generic: any register for multiple IDs |
| **Single Write** | `GoalCurrentCommand`         | `bool`           | Set goal current                       |
|                  | `ProfileTimeCommand`         | `bool`           | Set profile velocity (time-based)      |
|                  | `LedCommand`                 | `bool`           | Set LED on/off                         |
|                  | `WriteRegisterCommand`       | `bool`           | Generic: write any RAM register        |
| **Sync Write**   | `TorqueCommand`              | `bool`           | Enable/disable torque (multi-servo)    |
|                  | `SyncGoalPositionCommand`    | `bool`           | Positions + durations (multi-servo)    |
|                  | `SyncGoalCurrentCommand`     | `bool`           | Currents (multi-servo)                 |
| **Compound**     | `GoalPositionCommand`        | `bool`           | Current + profile + position (1 servo) |
|                  | `OperatingModeCommand`       | `bool`           | Set operating mode (auto torque off)   |
|                  | `PositionLimitCommand`       | `bool`           | Set min/max position limits            |
|                  | `RebootCommand`              | `bool`           | Reboot a servo                         |
| **EEPROM**       | `CurrentLimitCommand`        | `bool`           | Set current limit (EEPROM)             |
|                  | `VelocityLimitCommand`       | `bool`           | Set velocity limit (EEPROM)            |
|                  | `TemperatureLimitCommand`    | `bool`           | Set temperature limit (EEPROM)         |
|                  | `HomingOffsetCommand`        | `bool`           | Set homing offset (EEPROM)             |
|                  | `VoltageLimitCommand`        | `bool`           | Set voltage limits (EEPROM)            |

---

## Adding a New Servo Model

Open `dynamixel_sdk_wrapper/control_tables.py` and add a new entry:

```python
CONTROL_TABLE['XM430'] = {
    'MODEL_NUMBER':      {'ADDR': 0,   'LEN': 2},
    'FIRMWARE_VERSION':  {'ADDR': 6,   'LEN': 1},
    'ID':                {'ADDR': 7,   'LEN': 1},
    # ... add all registers for the model
    'TORQUE_ENABLE':     {'ADDR': 64,  'LEN': 1},
    'GOAL_POSITION':     {'ADDR': 116, 'LEN': 4},
    'PRESENT_POSITION':  {'ADDR': 132, 'LEN': 4},
}
```

Then use the model name when creating a `ServoConfig`:

```python
ServoConfig(id_=1, model="XM430")
```

---

## Project Structure

```
dynamixel-sdk-python-wrapper/
├── dynamixel_sdk_wrapper/
│   ├── __init__.py          # Public API exports
│   ├── wrapper.py           # DynamixelSDKWrapper class
│   ├── cmds.py              # All command dataclasses
│   └── control_tables.py    # Per-model register tables
├── pyproject.toml           # Package metadata & dependencies
└── README.md
```

## License

MIT
