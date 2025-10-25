# petoi_serial.py
# Minimal Petoi/OpenCat serial driver for Bittle on a Raspberry Pi.

import serial
import time

DEFAULT_PORT = "/dev/ttyUSB0"  # adjust if using UART pins: /dev/ttyAMA0
BAUD = 115200

class PetoiSerial:
    def __init__(self, port: str = DEFAULT_PORT, baud: int = BAUD):
        self.port = port
        self.baud = baud
        self.ser = None

    def open(self):
        if self.ser and self.ser.is_open:
            return
        self.ser = serial.Serial(self.port, self.baud, timeout=0.25)
        time.sleep(2.0)  # NyBoard resets on open

    def close(self):
        if self.ser:
            self.ser.close()

    def send(self, token: str):
        """Send a single OpenCat token, e.g. 'kbalance', 'kzero', 'kturnL', 'kwkF', 'd'."""
        if not self.ser or not self.ser.is_open:
            self.open()
        line = (token.strip() + "\n").encode("ascii")
        self.ser.write(line)

    # Convenience wrappers (REPLACE tokens with the ones your firmware uses)
    def stand(self):       self.send("kbalance")
    def zero(self):        self.send("kzero")
    def turn_left(self):   self.send("kturnL")  # <- confirm the exact skill name
    def turn_right(self):  self.send("kturnR")  # <- confirm the exact skill name
    def walk_forward(self):self.send("kwkF")    # <- confirm the exact skill name
    def stop(self):        self.send("d")       # often relax/stop