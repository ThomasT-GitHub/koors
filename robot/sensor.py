import RPi.GPIO as GPIO
import time

TRIG_PIN = 23
ECHO_PIN = 24
SPEED_OF_SOUND = 34300

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)


def get_distance():
	GPIO.output(TRIG_PIN, GPIO.HIGH)
	time.sleep(0.00001)
	GPIO.output(TRIG_PIN, GPIO.LOW)

	while GPIO.input(ECHO_PIN) == 0:
		pulse_start = time.time()

	while GPIO.input(ECHO_PIN) == 1:
		pulse_end = time.time()

	pulse_duration = pulse_end - pulse_start
	distance = pulse_duration * SPEED_OF_SOUND / 2

	return distance

def gpio_cleanup():
	GPIO.cleanup()

if __name__ == "__main__":
    print("This is the module file.")
