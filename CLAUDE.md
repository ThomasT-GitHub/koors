# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Koors is a robotic dog companion system that uses heart rate monitoring to detect distress and responds to voice commands. The system consists of three main components:

1. **Frontend** (React Native/Expo mobile app) - Monitors heart rate via HealthKit, accepts voice commands, and advertises as a BLE beacon
2. **Backend** (Python/Flask) - BLE scanner that tracks the phone beacon's RSSI and manages robot navigation/commands
3. **Robot** (Python) - Controls a Petoi Bittle robot dog via serial commands

## Architecture

### Communication Flow

```
Mobile App (BLE Beacon)
    ↓ RSSI signal
Backend (BLE Scanner + Flask API)
    ↓ HTTP/subprocess
Robot Controller (Serial → Bittle)
```

The backend scans for the phone's BLE beacon, tracks RSSI (signal strength), and either:
- Launches `robot/navigator.py` as a subprocess to autonomously navigate toward the beacon
- Directly calls `robot/controller.py` functions to perform specific tricks/gestures

### Key Architectural Patterns

**Navigator Process Management**: Backend uses `subprocess.Popen` to launch/halt the autonomous navigator. The navigator polls the backend's `/status` endpoint for live RSSI updates and implements a finite state machine (SEARCH → ALIGN → ADVANCE → AVOID → LOST) for beacon homing.

**Serial Connection Singleton**: `robot/controller.py` maintains a single global serial connection (`_connection`) to the Bittle. All movement/gesture functions operate on this shared connection.

**Heart Rate Triggering**: Frontend monitors HealthKit heart rate. When HR >= 180 BPM, state changes to 'searching' which should trigger the robot to start autonomous navigation (future integration).

**Camera Streaming**: Backend provides MJPEG streaming from a Raspberry Pi Camera. The camera module runs in a background thread, continuously capturing frames that can be streamed via HTTP or accessed for computer vision processing. Frames are stored both as JPEG (for streaming) and numpy arrays (for CV work).

## Development Commands

### Frontend (Expo/React Native)
```bash
cd frontend/koors

# Install dependencies
npm install

# Start development server
npx expo start

# Run on specific platforms
npx expo start --ios
npx expo start --android
npx expo start --web

# Lint
npm run lint
```

### Backend (Python/Flask)
```bash
cd backend

# Install dependencies
pip install -r requirement.txt

# Run the BLE scanner + Flask server
# Linux/BlueZ version (recommended):
export TARGET_SERVICE_UUID="180D"  # or your beacon UUID
export TARGET_NAME_SUBSTR="Koors Beacon"
export DOG_PORT="/dev/ttyUSB0"  # or your serial port
python app.py

# macOS version (if using macOS):
python app_macos.py
```

**Important**: On Linux, you may need Bluetooth capabilities:
```bash
sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)
```

### Robot Controller (Python)
```bash
cd robot

# Install dependencies
pip install -r requirements.txt

# Test basic controller functions
python flip_example.py

# Run autonomous navigator (requires backend running)
export APP_STATUS_URL="http://127.0.0.1:8080/status"
export DOG_PORT="/dev/ttyUSB0"
python navigator.py
```

### Common Serial Ports
- **macOS**: `/dev/tty.usbserial-*` or `/dev/tty.usbmodem-*`
- **Linux/Pi**: `/dev/ttyUSB0` or `/dev/ttyAMA0` (user must be in `dialout` group)
- **Windows**: `COM3`, `COM4`, etc.

## Backend API Endpoints

The Flask server (port 8080) provides:

### Navigation & Control
- `GET /status` - Returns beacon RSSI, config, and navigator status
- `POST /dispatch` - Starts autonomous navigation (spawns `navigator.py`)
- `POST /halt` - Stops autonomous navigation
- `POST /process_speech` - Executes a specific action (wave, flip, push_up, cheer) and overrides any ongoing navigation
  - Body: `{"action": "flip"}` or similar

### Camera Streaming
- `GET /camera/status` - Returns camera availability and current state
- `POST /camera/start` - Start camera capture (must call before streaming)
- `POST /camera/stop` - Stop camera capture
- `GET /camera/snapshot` - Get a single JPEG frame (camera must be running)
- `GET /camera/stream` - MJPEG video stream (camera must be running)
  - View directly in browser: `http://127.0.0.1:8080/camera/stream`
  - Works with HTML `<img>` tag or React Native Image component

## Code Organization

### Frontend Structure
- `app/index.tsx` - Main home screen with heart rate monitoring and voice recognition
- `components/KoorsButton.tsx` - Custom button component
- `hooks/` - Custom React hooks for theming and color schemes

### Backend Structure
- `app.py` - Main Linux/BlueZ BLE scanner with Flask API (production)
- `app_macos.py` - macOS-compatible version
- `camera.py` - Pi Camera manager for MJPEG streaming and CV frame access
- `petoi_serial.py` - Legacy serial helper (mostly replaced by `robot/controller.py`)

### Robot Structure
- `controller.py` - Function-based API for controlling Bittle (no classes, easy to import)
- `commands.py` - Command token constants for Bittle serial protocol
- `navigator.py` - Autonomous beacon-homing FSM with obstacle avoidance
- `sensor.py` - Placeholder for future sensor integration

## Robot Controller Functions

The `robot/controller.py` module provides simple function calls:

**Movement**: `walk_forward(duration)`, `walk_backward(duration)`, `turn_left(duration)`, `turn_right(duration)`, `sit()`, `stand()`, `stop()`

**Gestures**: `wave()`, `bark()`, `shake_hands()`, `play_dead()`, `stretch()`, `push_up()`, `roll()`, `flip()`

**Utilities**: `send_raw_command(cmd)`, `calibrate()`, `beep()`, `reset_position()`, `get_status()`

**Connection**: `connect_dog(port)`, `disconnect()`, `is_connected()`

## Environment Variables

### Backend
- `TARGET_SERVICE_UUID` - BLE service UUID to filter (16/32-bit auto-expanded to full UUID)
- `TARGET_NAME_SUBSTR` - Substring to match in beacon name (e.g., "Koors Beacon")
- `ADAPTER` - Bluetooth adapter (default: `hci0`)
- `SCANNING_MODE` - `active` or `passive` (default: `active`)
- `DOG_PORT` - Serial port for robot (default: `/dev/ttyUSB0`)
- `WALK_CMD` - Command token for walk (default: `kwkF`)
- `STOP_CMD` - Command token for stop (default: `d`)

### Camera (Optional)
- `CAMERA_WIDTH` - Camera resolution width (default: `640`)
- `CAMERA_HEIGHT` - Camera resolution height (default: `480`)
- `CAMERA_FPS` - Frame rate (default: `30`)
- `CAMERA_ROTATION` - Rotation in degrees: 0, 90, 180, or 270 (default: `0`)

### Navigator
- `APP_STATUS_URL` - Backend status endpoint (default: `http://127.0.0.1:8080/status`)
- `DOG_PORT` - Serial port for robot (default: `/dev/ttyUSB0`)

## Testing Strategy

When testing changes:

1. **Frontend**: Use Expo Go or development builds on physical iOS/Android device (HealthKit requires real device)
2. **Backend**: Test BLE scanning with phone's BLE peripheral app (e.g., LightBlue) advertising with matching UUID/name
3. **Robot**: Test controller functions incrementally - always call `connect_dog()` first, `disconnect()` when done
4. **Navigator**: Test with backend running and phone beacon active; monitor state transitions in console output
5. **Camera**:
   - Start camera: `curl -X POST http://127.0.0.1:8080/camera/start`
   - View stream in browser: `http://127.0.0.1:8080/camera/stream`
   - Get snapshot: `curl http://127.0.0.1:8080/camera/snapshot -o test.jpg`
   - Check status: `curl http://127.0.0.1:8080/camera/status`

## Important Notes

- The robot requires a physical serial connection to the Bittle hardware
- HealthKit (heart rate monitoring) only works on physical iOS devices, not simulators
- Voice recognition requires microphone permissions
- BLE beacon advertising from the phone must be in foreground (some apps like LightBlue required)
- The navigator implements a 10-minute global run limit (`GLOBAL_RUN_LIMIT_S`) for safety
- Always ensure the robot has sufficient battery before running autonomous navigation
- **Camera**: Raspberry Pi Camera Module required for camera streaming. The backend gracefully handles missing camera hardware (server still runs, camera endpoints return 503). Camera must be explicitly started via `/camera/start` before streaming