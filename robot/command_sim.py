# robot/command_sim.py
import time

def connect_dog(port="/dev/null", baudrate=0):
    print(f"[SIM] connect {port} @ {baudrate}")
    return True

def disconnect():
    print("[SIM] disconnect")

def is_connected():
    return True

def _act(label, dur=None):
    if dur:
        print(f"[SIM] {label} for {dur:.2f}s")
        time.sleep(dur)
    else:
        print(f"[SIM] {label}")
    return True

def walk_forward(duration=0.6): return _act("walk_forward", duration)
def walk_backward(duration=0.6): return _act("walk_backward", duration)
def turn_left(duration=0.3):    return _act("turn_left", duration)
def turn_right(duration=0.3):   return _act("turn_right", duration)
def stop():                     return _act("stop")
def sit():                      return _act("sit")
def stand():                    return _act("stand")
def send_command(cmd: str):     return _act(f"send_command({cmd})")