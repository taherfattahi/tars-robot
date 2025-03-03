#!/usr/bin/python3
# coding=utf8
import sys
sys.path.append('/home/pi/TurboPi/')
import time
import signal
import HiwonderSDK.mecanum as mecanum
from bluetooth import  *

print('''
Demo: Process a list of movement commands.
Commands:
    1. Move forward 50 centimeter and then turn left.
    2. Move forward 30 centimeter and then turn right.
Press Ctrl+C to stop.
''')

server_sock=BluetoothSocket( RFCOMM )
server_sock.bind(("",PORT_ANY))
server_sock.listen(1)

port = server_sock.getsockname()[1]

uuid = "94f39d29-7d6d-437d-973b-fba39e49d4ee"

advertise_service( server_sock, "SampleServer",
                   service_id = uuid,
                   service_classes = [ uuid, SERIAL_PORT_CLASS ],
                   profiles = [ SERIAL_PORT_PROFILE ], 
#                   protocols = [ OBEX_UUID ] 
                    )
                   
print("Waiting for connection on RFCOMM channel %d" % port)

client_sock, client_info = server_sock.accept()
print("Accepted connection from ", client_info)

# Initialize the chassis
chassis = mecanum.MecanumChassis()
start = True

# Signal handler for graceful exit
def stop_handler(signum, frame):
    global start
    start = False
    print("Stopping robot...")
    chassis.set_velocity(0, 0, 0)

signal.signal(signal.SIGINT, stop_handler)

# List of movement commands
# Unit is centimeter
# Each dictionary contains:
#  - distance: the distance to move
#  - move: the movement direction (only "forward" in this example)
#  - turn: the turn direction ("left" or "right")
# commands = [
#     {"distance": 50, "move": "forward", "turn": "left"},
#     {"distance": 50, "move": "forward", "turn": "right"}
# ]
commands = []

# Constants
SPEED = 50  # Speed (0-100)
FORWARD_DIRECTION = 90  # Forward direction in degrees (90 is forward)
WHEEL_DIAMETER_MM = 65  # Wheel diameter in mm (from your code)

def get_move_duration(distance, speed=50):
    MAX_SPEED_CMPS = 50  # Maximum speed in centimeters per second at 100% power
    actual_speed = (SPEED / 100) * MAX_SPEED_CMPS  # Speed in centimeters per second
    time_for_distance = distance / actual_speed  # Time in seconds
    return time_for_distance

def execute_command(cmd):
    # Check if this is a turn-only command
    if "distance" not in cmd:
        turn_direction = cmd.get("turn")
        if turn_direction:
            # Use a positive angular rate for left, negative for right.
            angular_rate = -0.5 if turn_direction.lower() == "left" else 0.5
            print(f"Turning {turn_direction} for 2 seconds.")
            chassis.set_velocity(0, 0, angular_rate)
            time.sleep(0.5)
            chassis.set_velocity(0, 0, 0)
            time.sleep(0.5)
        return
    
    # Check movement direction (forward or backward)
    move_direction = cmd.get("move", "forward")
    
    duration = get_move_duration(cmd["distance"], speed=50)
    
    if move_direction == "backward":
        print(f"Moving backward {cmd['distance']} for {duration:.2f} seconds.")
        chassis.set_velocity(50, 270, 0)  # 270 degrees is backward (opposite of forward)
    else:
        print(f"Moving forward {cmd['distance']} for {duration:.2f} seconds.")
        chassis.set_velocity(50, FORWARD_DIRECTION, 0)
    
    time.sleep(duration)
    
    # Stop before turning
    chassis.set_velocity(0, 0, 0)
    time.sleep(0.5)
    
    # Turn command (if present)
    turn_direction = cmd.get("turn")
    if turn_direction:
        # Use a positive angular rate for left, negative for right.
        angular_rate = -0.5 if turn_direction.lower() == "left" else 0.5
        print(f"Turning {turn_direction} for 2 seconds.")
        chassis.set_velocity(0, 0, angular_rate)
        time.sleep(0.5)
        chassis.set_velocity(0, 0, 0)
        time.sleep(0.5)

if __name__ == '__main__':
    
    while True:
        data = client_sock.recv(1024)
        if data and len(data) > 0:
            print(f"Received: {data}")
            if data == b"end":
                break
            try:
                data = data.decode('utf-8').split("@")
                
                # Check if this is a turn-only command
                if data[0] == "turn":
                    commands = [{"turn": data[1]}]
                # Check if this is a backward command (negative distance)
                elif data[0].startswith("-"):
                    distance = float(data[0])
                    commands = [{"distance": abs(distance), "move": "backward"}]
                else:
                    # Forward command (with or without turn)
                    distance = float(data[0])
                    if data[1] == "none":
                        # Forward-only command
                        commands = [{"distance": distance, "move": "forward"}]
                    else:
                        # Forward and turn command
                        commands = [{"distance": distance, "move": "forward", "turn": data[1]}]
            except Exception as e:
                print(f"An error occurred: {e}")
                break            
            for command in commands:
                if not start:
                    break
                execute_command(command)
    
    chassis.set_velocity(0, 0, 0)
    print("Command sequence completed.")