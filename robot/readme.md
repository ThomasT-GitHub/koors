# 🐕 Bittle Robot Controller

Simple Python functions to control the Petoi Bittle robot dog. Perfect for APIs and hackathons.

## 🚀 Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Connect your Bittle via USB**

3. **Basic usage:**
   ```python
   import controller

   # Connect once at startup
   controller.connect_dog("/dev/ttyUSB0")  # Update port as needed

   # Then just call functions
   controller.wave()           # Say hello
   controller.walk_forward(2)  # Walk for 2 seconds
   controller.bark()           # Make noise
   controller.sit()            # Sit down

   # Disconnect when done
   controller.disconnect()
   ```

## 🌐 Perfect for APIs

```python
# Flask example
from flask import Flask
import controller

app = Flask(__name__)

# Connect once when app starts
controller.connect_dog("/dev/ttyUSB0")

@app.route("/wave")
def wave():
    controller.wave()
    return {"status": "waved"}

@app.route("/walk/<direction>")
def walk(direction):
    if direction == "forward":
        controller.walk_forward(1)
    elif direction == "back":
        controller.walk_backward(1)
    return {"status": f"walked {direction}"}
```

## 📋 Available Functions

### Movement
- `walk_forward(duration=1.0)` - Walk forward
- `walk_backward(duration=1.0)` - Walk backward
- `turn_left(duration=0.5)` - Turn left
- `turn_right(duration=0.5)` - Turn right
- `sit()` - Sit down
- `stand()` - Stand up
- `stop()` - Stop all movement

### Gestures & Tricks
- `wave()` - Wave hello
- `bark()` - Make barking sound
- `shake_hands()` - Shake hands gesture
- `play_dead()` - Lie down
- `stretch()` - Stretch pose
- `push_up()` - Do push ups
- `roll()` - Roll over
- `flip()` - Do a backflip! 🤸

### Utilities
- `send_raw_command(cmd)` - Send custom commands
- `get_status()` - Get connection status
- `beep()` - Make beep sound
- `calibrate()` - Calibrate servos
- `is_connected()` - Check connection
- `reset_position()` - Reset to standing

## 🔧 Port Configuration

**Common USB ports:**
- **Linux/Mac:** `/dev/ttyUSB0`, `/dev/ttyACM0`, `/dev/cu.usbserial-*`
- **Windows:** `COM3`, `COM4`, etc.

Check your system:
```bash
# Linux/Mac
ls /dev/tty*

# Windows Device Manager
# Look for "USB Serial Port" or "Arduino"
```

## 📁 Files

- `controller.py` - Main functions (no classes!)
- `commands.py` - All Bittle command constants
- `example_usage.py` - Basic usage examples
- `flip_example.py` - Cool flip tricks demo
- `requirements.txt` - Dependencies (just pyserial)

## 🎯 Example Demos

**Basic demo:**
```bash
python example_usage.py
```

**Flip tricks demo:**
```bash
python flip_example.py
```

## 🛠️ Custom Commands

Use raw Bittle commands from `commands.py`:
```python
from commands import WALK_FORWARD, get_command

controller.send_raw_command(WALK_FORWARD)
controller.send_raw_command(get_command("stretch"))
```

## 🚨 Troubleshooting

**Connection issues:**
- Check USB cable connection
- Verify correct port in code
- Ensure robot is powered on
- Try different USB ports

**Permission issues (Linux/Mac):**
```bash
sudo chmod 666 /dev/ttyUSB0
# or add user to dialout group
sudo usermod -a -G dialout $USER
```

**Robot not responding:**
- Try `controller.calibrate()` first
- Check if robot needs charging
- Verify commands in `commands.py`

## 🔗 Perfect for Integration

This simple function-based approach is ideal for:
- **Flask/FastAPI backends** - just import and call
- **IoT projects** - single connection, easy functions
- **Voice assistants** - map voice to functions
- **Mobile app backends** - simple REST endpoints
- **Game controllers** - direct function mapping

No classes, no complexity - just import and go! 🚀