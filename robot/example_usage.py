#!/usr/bin/env python3
"""
Example usage of the Bittle Robot Controller

This script demonstrates how to use the BittleController class
to control your Petoi Bittle robot dog.

Make sure to:
1. Install dependencies: pip install -r requirements.txt
2. Connect your Bittle robot via USB
3. Update the port if needed (check device manager/ls /dev/tty*)
"""

import time
from controller import BittleController
from commands import ALL_COMMANDS, get_command

def basic_demo():
    """Basic demonstration of robot functions."""
    print("🐕 Starting Bittle Robot Demo")

    # Create controller instance (update port as needed)
    # Common ports:
    # - Linux/Mac: /dev/ttyUSB0, /dev/ttyACM0, /dev/cu.usbserial-*
    # - Windows: COM3, COM4, etc.
    dog = BittleController(port="/dev/ttyUSB0")

    # Connect to robot
    if not dog.connect():
        print("❌ Failed to connect to robot. Check port and connection.")
        return

    try:
        print("✅ Connected! Starting demo sequence...")

        # Say hello
        print("👋 Waving hello...")
        dog.wave()
        time.sleep(2)

        # Basic movements
        print("🚶 Walking forward...")
        dog.walk_forward(duration=2)
        time.sleep(1)

        print("↩️ Turning around...")
        dog.turn_right(duration=1)
        dog.turn_right(duration=1)
        time.sleep(1)

        print("🚶 Walking back...")
        dog.walk_backward(duration=2)
        time.sleep(1)

        # Tricks
        print("🎪 Doing some tricks...")
        dog.sit()
        time.sleep(2)

        dog.bark()
        time.sleep(1)

        dog.shake_hands()
        time.sleep(2)

        print("😴 Playing dead...")
        dog.play_dead()
        time.sleep(3)

        print("🔄 Getting back up...")
        dog.stand()
        time.sleep(2)

        print("🎉 Demo complete!")

    except KeyboardInterrupt:
        print("\n⏹️ Demo interrupted by user")

    finally:
        # Always disconnect when done
        dog.disconnect()

def context_manager_demo():
    """Demonstration using context manager (auto connect/disconnect)."""
    print("\n🔄 Context Manager Demo")

    try:
        # Using 'with' statement for automatic connection management
        with BittleController(port="/dev/ttyUSB0") as dog:
            print("✅ Auto-connected via context manager")

            # Quick sequence
            dog.wave()
            time.sleep(1)
            dog.beep()
            time.sleep(1)
            dog.sit()

            print("✅ Context manager demo complete")

    except Exception as e:
        print(f"❌ Context manager demo failed: {e}")

def custom_commands_demo():
    """Demonstration of using custom commands."""
    print("\n🛠️ Custom Commands Demo")

    try:
        with BittleController(port="/dev/ttyUSB0") as dog:
            # Using raw commands
            print("🎯 Sending raw command for stretch...")
            dog.send_raw_command("kstr")
            time.sleep(2)

            # Using command constants
            print("📖 Using command from constants...")
            stretch_cmd = get_command("stretch")
            dog.send_raw_command(stretch_cmd)
            time.sleep(2)

            print("✅ Custom commands demo complete")

    except Exception as e:
        print(f"❌ Custom commands demo failed: {e}")

def status_demo():
    """Demonstration of status checking."""
    print("\n📊 Status Demo")

    dog = BittleController(port="/dev/ttyUSB0")

    # Check status before connection
    status = dog.get_status()
    print(f"Status before connection: {status}")

    if dog.connect():
        # Check status after connection
        status = dog.get_status()
        print(f"Status after connection: {status}")

        dog.disconnect()

    print("✅ Status demo complete")

if __name__ == "__main__":
    print("🤖 Bittle Robot Controller Examples\n")

    # List available commands
    print("📋 Available commands:")
    for name in sorted(ALL_COMMANDS.keys()):
        print(f"  - {name}: {ALL_COMMANDS[name]}")
    print()

    try:
        # Run demos
        basic_demo()
        context_manager_demo()
        custom_commands_demo()
        status_demo()

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        print("💡 Tips:")
        print("  - Check that robot is connected via USB")
        print("  - Verify the correct port (update in code)")
        print("  - Install dependencies: pip install -r requirements.txt")
        print("  - Make sure robot is powered on")