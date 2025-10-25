"""
Bittle Robot Command Constants

This module contains all the standard commands for the Petoi Bittle robot.
Use these constants with the send_raw_command() method for custom control.
"""

# Movement Commands
WALK_FORWARD = "kwkF"
WALK_BACKWARD = "kbk"
TURN_LEFT = "kL"
TURN_RIGHT = "kR"
BALANCE = "kbalance"  # Stop/balance position

# Posture Commands
SIT = "ksit"
STAND_UP = "kup"
REST = "krest"  # Lie down/play dead

# Gesture Commands
WAVE_HI = "khi"
SHAKE_HANDS = "kck"
STRETCH = "kstr"

# Sound Commands
BARK = "kb"
BEEP = "b"

# Utility Commands
CALIBRATE = "c"

# Advanced Movement Commands (for reference)
CRAWL_FORWARD = "kcrF"
CRAWL_LEFT = "kcrL"
CRAWL_RIGHT = "kcrR"
TROT = "ktr"
BOUND = "kbd"
PACE = "kpc"

# Trick Commands
PUSH_UP = "kpu"
ROLL = "krl"
RECOVER = "krc"

# All available commands for reference
ALL_COMMANDS = {
    # Basic movements
    "walk_forward": WALK_FORWARD,
    "walk_backward": WALK_BACKWARD,
    "turn_left": TURN_LEFT,
    "turn_right": TURN_RIGHT,
    "balance": BALANCE,

    # Postures
    "sit": SIT,
    "stand": STAND_UP,
    "rest": REST,

    # Gestures
    "wave": WAVE_HI,
    "shake_hands": SHAKE_HANDS,
    "stretch": STRETCH,

    # Sounds
    "bark": BARK,
    "beep": BEEP,

    # Advanced moves
    "crawl_forward": CRAWL_FORWARD,
    "crawl_left": CRAWL_LEFT,
    "crawl_right": CRAWL_RIGHT,
    "trot": TROT,
    "bound": BOUND,
    "pace": PACE,
    "push_up": PUSH_UP,
    "roll": ROLL,
    "recover": RECOVER,

    # Utility
    "calibrate": CALIBRATE,
}

def get_command(name: str) -> str:
    """Get a command by name."""
    return ALL_COMMANDS.get(name.lower(), "")

def list_commands() -> list:
    """Get list of all available command names."""
    return list(ALL_COMMANDS.keys())