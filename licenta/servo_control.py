from gpiozero import Servo
from time import sleep

# Setăm pinul GPIO care controlează servo-ul
servo = Servo(18)

try:
    while True:
        with open('/tmp/servo_status.txt', 'r') as file:
            status = file.read().strip()
        if status == 'open':
            servo.max()  # Deschide servo-ul
        elif status == 'close':
            servo.min()  # Închide servo-ul
        sleep(1)
except KeyboardInterrupt:
    pass
