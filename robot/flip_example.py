#!/usr/bin/env python3
"""
🤸 Bittle Flip Tricks Demo

This script shows off the Bittle's acrobatic abilities!
Features backflips, rolls, and other cool tricks.

Make sure your robot has enough space to perform these moves safely.
"""

import time
import controller

def cool_flip_sequence():
    """Demonstrate the dog's acrobatic abilities."""
    print("🤸 Starting Bittle Flip & Tricks Demo!")

    if not controller.connect_dog("/dev/ttyUSB0"):
        print("❌ Failed to connect to dog")
        return

    try:
        print("✅ Connected! Get ready for some tricks...")
        time.sleep(1)

        # Start with a greeting
        print("👋 Say hello...")
        controller.wave()
        time.sleep(2)

        # Warm up with basic movements
        print("🏃 Warming up...")
        controller.walk_forward(1)
        controller.turn_left(0.5)
        controller.walk_backward(1)
        time.sleep(1)

        # The main event - backflip!
        print("🎪 GET READY FOR THE BACKFLIP!")
        time.sleep(2)
        print("3...")
        time.sleep(1)
        print("2...")
        time.sleep(1)
        print("1...")
        time.sleep(1)
        print("🤸 BACKFLIP!")

        controller.flip()
        time.sleep(3)  # Give it time to complete

        print("🎉 Amazing! Did you see that?")
        time.sleep(2)

        # Follow up with roll
        print("🌀 Now for a roll...")
        controller.roll()
        time.sleep(3)

        # Some push ups for strength
        print("💪 Time for some push ups...")
        controller.push_up()
        time.sleep(3)

        # Recovery pose
        print("😌 Taking a breather...")
        controller.sit()
        time.sleep(2)

        # Final trick - play dead
        print("😵 Playing dead...")
        controller.play_dead()
        time.sleep(3)

        # Wake up and celebrate
        print("🎊 Back to life!")
        controller.stand()
        time.sleep(1)

        controller.bark()
        controller.bark()
        controller.wave()

        print("✨ Trick sequence complete! What a show!")

    except KeyboardInterrupt:
        print("\n⏹️ Demo interrupted")
    except Exception as e:
        print(f"❌ Demo failed: {e}")
    finally:
        controller.disconnect()

def quick_flip_demo():
    """Just the flip for testing."""
    print("🤸 Quick Flip Test")

    if not controller.connect_dog("/dev/ttyUSB0"):
        print("❌ Failed to connect")
        return

    try:
        print("🤸 Doing a backflip...")
        controller.flip()
        time.sleep(3)
        print("✅ Flip complete!")
    except Exception as e:
        print(f"❌ Flip failed: {e}")
    finally:
        controller.disconnect()

def strength_demo():
    """Show off strength moves."""
    print("💪 Strength Training Demo")

    if not controller.connect_dog("/dev/ttyUSB0"):
        print("❌ Failed to connect")
        return

    try:
        print("💪 Push up routine...")
        for i in range(3):
            print(f"Push up {i+1}/3")
            controller.push_up()
            time.sleep(2)

        print("🌀 Rolling around...")
        controller.roll()
        time.sleep(3)

        print("💪 Strength demo complete!")
    except Exception as e:
        print(f"❌ Demo failed: {e}")
    finally:
        controller.disconnect()

if __name__ == "__main__":
    print("🤖 Bittle Flip & Tricks Demo")
    print("Choose your demo:")
    print("1. Full acrobatic sequence")
    print("2. Quick flip test")
    print("3. Strength training")
    print()

    try:
        choice = input("Enter choice (1-3) or press Enter for full demo: ").strip()

        if choice == "2":
            quick_flip_demo()
        elif choice == "3":
            strength_demo()
        else:  # Default to full demo
            cool_flip_sequence()

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure robot is connected and powered on!")