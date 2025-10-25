import serial
import time
from typing import Optional

# Global connection - one dog, one connection
_connection: Optional[serial.Serial] = None


def connect_dog(port: str = "/dev/ttyUSB0", baudrate: int = 115200) -> bool:
    """Connect to the dog. Call this once at startup."""
    global _connection
    try:
        _connection = serial.Serial(port=port, baudrate=baudrate, timeout=1)
        time.sleep(2)
        print(f"Connected to dog on {port}")
        return True
    except Exception as e:
        print(f"Failed to connect: {e}")
        return False


def disconnect():
    """Disconnect from dog."""
    global _connection
    if _connection:
        _connection.close()
        _connection = None
        print("Disconnected from dog")


def send_command(command: str) -> bool:
    """Send command to dog."""
    if not _connection:
        print("Dog not connected")
        return False

    try:
        _connection.write(f"{command}\n".encode())
        time.sleep(0.1)
        return True
    except Exception as e:
        print(f"Command failed: {e}")
        return False


def is_connected() -> bool:
    """Check if connected to dog."""
    return _connection is not None and _connection.is_open


# Basic Movement Functions
def walk_forward(duration: float = 1.0) -> bool:
    """Walk forward for specified duration."""
    if send_command("kwkF"):
        time.sleep(duration)
        stop()
        return True
    return False


def walk_backward(duration: float = 1.0) -> bool:
    """Walk backward for specified duration."""
    if send_command("kbk"):
        time.sleep(duration)
        stop()
        return True
    return False


def turn_left(duration: float = 0.5) -> bool:
    """Turn left for specified duration."""
    if send_command("kL"):
        time.sleep(duration)
        stop()
        return True
    return False


def turn_right(duration: float = 0.5) -> bool:
    """Turn right for specified duration."""
    if send_command("kR"):
        time.sleep(duration)
        stop()
        return True
    return False


def sit() -> bool:
    """Make the dog sit."""
    return send_command("ksit")


def stand() -> bool:
    """Make the dog stand."""
    return send_command("kup")


def stop() -> bool:
    """Stop all movement."""
    return send_command("kbalance")


# Gesture Functions
def wave() -> bool:
    """Make the dog wave hello."""
    return send_command("khi")


def bark() -> bool:
    """Make the dog bark."""
    return send_command("kb")


def play_dead() -> bool:
    """Make the dog play dead."""
    return send_command("krest")


def shake_hands() -> bool:
    """Make the dog shake hands."""
    return send_command("kck")


def stretch() -> bool:
    """Make the dog stretch."""
    return send_command("kstr")


def push_up() -> bool:
    """Make the dog do push ups."""
    return send_command("kpu")


def roll() -> bool:
    """Make the dog roll over."""
    return send_command("krl")


def flip() -> bool:
    """Make the dog do a backflip."""
    return send_command("kbf")


# Utility Functions
def send_raw_command(command: str) -> bool:
    """Send a custom raw command to the dog."""
    return send_command(command)


def calibrate() -> bool:
    """Calibrate the dog's servo positions."""
    return send_command("c")


def beep() -> bool:
    """Make the dog beep."""
    return send_command("b")


def get_status() -> dict:
    """Get basic status information."""
    return {
        "connected": is_connected(),
        "port": _connection.port if _connection else None,
        "baudrate": _connection.baudrate if _connection else None,
    }


def reset_position() -> bool:
    """Reset dog to neutral standing position."""
    return send_command("kbalance")
