# Bluetooth Beacon Search Script

## Setup
1. Ensure you have Python installed
2. Install dependencies: `pip install -r requirements.txt`
3. Set up your virtual environment using pyenv (recommended)

## Running the Script

```bash
export TARGET_SERVICE_UUID="{your uuid}"
export TARGET_NAME_SUBSTR="{your peripheral name}"
python app.py
```

the script essentially look for the match UUID and Beacon name for the device to pair. if it matched successfully you should see the following: 
[MATCH] {peripheral name}: RSSI=-42, UUIDs=[]

(Modify this down the road)
How the dog walk towards the beacon:
repeat
  scan beacon → get RSSI
  if beacon not seen recently → pause
  else:
     measure RSSI_forward
     turn left  → measure RSSI_left
     turn right → measure RSSI_right
     pick heading with highest RSSI
     turn toward it
     short walk forward
     stop & repeat
until stop requested

## Available Endpoints
GET /status:
Returns current beacon RSSI, config, and whether homing is active.

POST /walk
Sends a one-shot walk command to Bittle (WALK_CMD token or JSO {"cmd":"<token>"}).

POST /start
Begins autonomous homing toward the beacon.

POST /stop
Stops homing and relaxes the robot.

