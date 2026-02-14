"""
Dynamixel SDK Wrapper — a command-driven Python wrapper for the Dynamixel SDK.

Quick start::

    from dynamixel_sdk_wrapper import DynamixelSDKWrapper, ServoConfig
    from dynamixel_sdk_wrapper.cmds import *

    dxl = DynamixelSDKWrapper(port='COM3')
    dxl.open_port()

    dxl.add_servo([ServoConfig(id_=1, model='XC330', name='joint1')])
    dxl.send_cmd(TorqueCommand(ids=[1], enable=[True]))

    pos = dxl.send_cmd(ReadPositionCommand(id=1))
    print(f"Position: {pos}")

    dxl.close_port()
"""

from dynamixel_sdk_wrapper.wrapper import DynamixelSDKWrapper, ServoConfig, Servo
from dynamixel_sdk_wrapper.cmds import *
from dynamixel_sdk_wrapper.control_tables import CONTROL_TABLE

__all__ = [
    "DynamixelSDKWrapper",
    "ServoConfig",
    "Servo",
    "CONTROL_TABLE",
]

__version__ = "0.1.0"
