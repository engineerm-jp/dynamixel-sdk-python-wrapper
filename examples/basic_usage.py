"""
Basic example for dynamixel-sdk-python-wrapper.

Demonstrates:
  - Opening a port
  - Registering servos
  - Enabling torque
  - Reading position, current, temperature
  - Moving a servo to a goal position
  - Sync reading multiple servos
  - Disabling torque and closing

Adjust `PORT`, servo IDs, and model names to match your hardware.
"""

from dynamixel_sdk_wrapper import DynamixelSDKWrapper, ServoConfig
from dynamixel_sdk_wrapper.cmds import (
    TorqueCommand,
    ReadPositionCommand,
    ReadCurrentCommand,
    ReadTemperatureCommand,
    GoalPositionCommand,
    SyncReadPositionCommand,
    LedCommand,
    OperatingModeCommand,
)
from time import sleep

# ── Configuration ────────────────────────────────────────────
PORT = "COM3"          # Windows — change to "/dev/ttyUSB0" on Linux
BAUDRATE = 4000000
SERVO_IDS = [1, 2]     # IDs of the servos on the bus
MODEL = "XC330"        # Must match a key in control_tables.py

# ── Setup ────────────────────────────────────────────────────
dxl = DynamixelSDKWrapper(port=PORT, baudrate=BAUDRATE)

if not dxl.open_port():
    raise RuntimeError(f"Could not open port {PORT}")

# Register two servos in extended-position mode
dxl.add_servo([
    ServoConfig(id_=SERVO_IDS[0], model=MODEL, name="joint_1", op_mode="extended_pos"),
    ServoConfig(id_=SERVO_IDS[1], model=MODEL, name="joint_2", op_mode="extended_pos"),
])

# ── Read sensor values ───────────────────────────────────────
for sid in SERVO_IDS:
    pos  = dxl.send_cmd(ReadPositionCommand(id=sid))
    cur  = dxl.send_cmd(ReadCurrentCommand(id=sid))
    temp = dxl.send_cmd(ReadTemperatureCommand(id=sid))
    print(f"[Servo {sid}]  Position: {pos}  |  Current: {cur} mA  |  Temp: {temp} °C")

sleep(1)  # Just to separate output sections

# ── Sync read positions from all servos at once ──────────────
positions = dxl.send_cmd(SyncReadPositionCommand(ids=SERVO_IDS))
print(f"Sync positions: {positions}")

# ── Enable torque and move ───────────────────────────────────
dxl.send_cmd(TorqueCommand(ids=SERVO_IDS, enable=[True, True]))

# Turn LEDs on so you can see the servos are active
for sid in SERVO_IDS:
    dxl.send_cmd(LedCommand(id=sid, value=1))
sleep(1.0)

# Move servo 1 to position 2048 over 1.5 seconds with a 500 mA current cap
dxl.send_cmd(GoalPositionCommand(
    id=SERVO_IDS[0],
    position=2048,
    duration_ms=1500,
))
sleep(2)  # Wait for motion to finish

# Set to current-based control mode and apply a current to servo 1 for 1 second
result = dxl.send_cmd(OperatingModeCommand(ids=SERVO_IDS, mode="current_pos"))
print(f"Operating mode change result: {result}")

# Move servo 2 to position 1024 over 1 second (with current control)
dxl.send_cmd(GoalPositionCommand(
    id=SERVO_IDS[1],
    position=0,
    duration_ms=1000,
    current_limit_mA=500,
))

sleep(2)  # Wait for motions to finish

# ── Read final positions ─────────────────────────────────────
final = dxl.send_cmd(SyncReadPositionCommand(ids=SERVO_IDS))
print(f"Final positions: {final}")

# ── Cleanup ──────────────────────────────────────────────────
for sid in SERVO_IDS:
    dxl.send_cmd(LedCommand(id=sid, value=0))

dxl.send_cmd(TorqueCommand(ids=SERVO_IDS, enable=[False, False]))
dxl.close_port()
print("Done.")
