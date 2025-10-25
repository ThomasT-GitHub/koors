# backend/app_macos.py
import os, re, time, threading, asyncio
from typing import Optional, Tuple, List
from flask import Flask, jsonify, request
from bleak import BleakScanner

RAW_UUID = (os.getenv("TARGET_SERVICE_UUID") or "").strip()
TARGET_NAME_SUBSTR = (os.getenv("TARGET_NAME_SUBSTR") or "").strip()

def expand_uuid(u: str) -> Optional[str]:
    if not u: return None
    s = u.lower().replace("-", "")
    if re.fullmatch(r"[0-9a-f]{4}", s):  return f"0000{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{8}", s):  return f"{s}-0000-1000-8000-00805f9b34fb"
    if re.fullmatch(r"[0-9a-f]{32}", s): return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:]}"
    return u

TARGET_SERVICE_UUID = (expand_uuid(RAW_UUID) or "").lower()
NAME_SUB = TARGET_NAME_SUBSTR.lower()

class BeaconState:
    def __init__(self):
        self.last_addr=None; self.last_name=None; self.last_rssi=None; self.last_seen=None
        self._lock=threading.Lock()
    def update(self, addr, name, rssi):
        with self._lock:
            self.last_addr=addr; self.last_name=name; self.last_rssi=rssi; self.last_seen=time.time()
    def as_dict(self):
        with self._lock:
            return {
                "address": self.last_addr, "name": self.last_name, "rssi": self.last_rssi,
                "last_seen_epoch": self.last_seen,
                "age_secs": (time.time()-self.last_seen) if self.last_seen else None,
            }

state = BeaconState()
app = Flask(__name__)

@app.get("/status")
def status():
    return jsonify({
        "ok": True,
        "config": {
            "target_service_uuid": TARGET_SERVICE_UUID or None,
            "target_name_substr": TARGET_NAME_SUBSTR or None,
        },
        "beacon": state.as_dict()
    })

def normalize(device, adv):
    addr = getattr(device, "address", None) or "(noaddr)"
    name = getattr(adv, "local_name", None) or getattr(device, "name", "") or ""
    rssi = getattr(adv, "rssi", None)
    uuids = [u.lower() for u in (getattr(adv, "service_uuids", None) or [])]
    return addr, name, rssi, uuids

def on_detect(device, adv):
    addr, name, rssi, suuids = normalize(device, adv)
    has_uuid = bool(TARGET_SERVICE_UUID) and (TARGET_SERVICE_UUID in suuids)
    has_name = (not NAME_SUB) or (name and NAME_SUB in name.lower())
    if TARGET_SERVICE_UUID:
        if has_uuid:
            state.update(addr, name or addr, int(rssi) if rssi is not None else None)
            print(f"[MATCH] {name or addr}: RSSI={rssi}, UUIDs={suuids}")
    else:
        if has_name:
            state.update(addr, name or addr, int(rssi) if rssi is not None else None)
            print(f"[MATCH] {name or addr}: RSSI={rssi}, UUIDs={suuids}")

def run_flask(): app.run(host="127.0.0.1", port=8080)

async def main():
    threading.Thread(target=run_flask, daemon=True).start()
    print(f"[SCAN] uuid={TARGET_SERVICE_UUID or '(none)'} name_sub='{TARGET_NAME_SUBSTR or '(none)'}'")
    scanner = BleakScanner(detection_callback=on_detect)
    await scanner.start()
    try:
        while True:
            await asyncio.sleep(0.5)
    finally:
        await scanner.stop()

if __name__ == "__main__":
    asyncio.run(main())