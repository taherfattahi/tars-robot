import os
import getpass
import sys
import re

import bluetooth

# --- Audio Imports ---
import ggwave
import pyaudio

# --- LangChain and Robot Imports ---
from langchain.agents import AgentType, initialize_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool

# Append custom module path if needed
sys.path.append('/home/pi/TurboPi/')

# --- Set OpenAI API Key ---
if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter your OpenAI API key: ")


# Replace with your server device's Bluetooth MAC address
server_address = "D8:3A:DD:7D:67:75"
port = 1  # This is the channel to which the server is bound

# Create an RFCOMM Bluetooth socket
sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
sock.connect((server_address, port))

@tool
def robot_movement(command_string):
    """
    Move the robot based on a command string.
    Commands supported:
    - 'forward X cm' where X is a number
    - 'forward X cm and turn Y' where X is a number and Y is 'left' or 'right'
    - 'backward X cm' where X is a number
    - 'turn Y' where Y is 'left' or 'right'
    Examples: 'forward 40 cm', 'forward 40 cm and turn right', 'backward 30 cm', 'turn left'
    """
    # Extract parameters from the command
    distance, direction, movement_type = extract_robot_command_params(command_string)
    
    if movement_type == "turn_only":
        # Turn-only command
        if direction is None or direction.lower() not in ["left", "right"]:
            return "Error: Direction must be 'left' or 'right'."
        
        try:
            sock.send("turn@" + direction)
        except Exception as e:
            return f"Error executing command: {str(e)}"
        
        return f"Robot turned {direction}."
        
    elif movement_type == "backward":
        # Backward movement command
        if distance is None:
            return "Error: Could not determine distance from command."
        
        try:
            sock.send("-" + str(distance) + "@none")
        except Exception as e:
            return f"Error executing command: {str(e)}"
        
        return f"Robot moved backward {distance} cm."
        
    elif movement_type == "forward_only":
        # Forward-only movement command
        if distance is None:
            return "Error: Could not determine distance from command."
        
        try:
            sock.send(str(distance) + "@none")
        except Exception as e:
            return f"Error executing command: {str(e)}"
        
        return f"Robot moved forward {distance} cm."
        
    else:
        # Forward and turn command
        if distance is None:
            return "Error: Could not determine distance from command."
        
        if direction is None or direction.lower() not in ["left", "right"]:
            return "Error: Direction must be 'left' or 'right'."
        
        try:
            sock.send(str(distance) + "@" + direction)
        except Exception as e:
            return f"Error executing command: {str(e)}"
        
        return f"Robot moved forward {distance} cm and turned {direction}."

# Function to extract parameters from natural language
def extract_robot_command_params(user_input):
    distance_pattern = r'(\d+(?:\.\d+)?)\s*(?:cm|centimeters?|meters?|m)'
    direction_pattern = r'(left|right)'
    
    # Identify command type
    if re.search(r'\bturn\b', user_input.lower()) and not re.search(r'\b(forward|backward|go|move)\b', user_input.lower()):
        # Turn-only command
        movement_type = "turn_only"
    elif re.search(r'\bbackward\b', user_input.lower()):
        # Backward movement command
        movement_type = "backward"
    elif re.search(r'\b(forward|go|move)\b', user_input.lower()) and not re.search(r'\bturn\b', user_input.lower()):
        # Forward-only command
        movement_type = "forward_only"
    else:
        # Default: forward and turn
        movement_type = "forward_turn"
    
    # Extract distance
    distance_match = re.search(distance_pattern, user_input.lower())
    distance = float(distance_match.group(1)) if distance_match else None
    
    # Extract direction
    direction_match = re.search(direction_pattern, user_input.lower())
    direction = direction_match.group(1) if direction_match else None
    
    return distance, direction, movement_type

# --- Initialize the ChatOpenAI LLM ---
llm = ChatOpenAI(
    openai_api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4-turbo",
    temperature=0
)

# Initialize the agent with the tool
agent = initialize_agent(
    tools=[robot_movement], 
    llm=llm, 
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# Function to process user commands
def process_robot_command(user_input):
    # Pass the entire command to the tool or the agent
    return robot_movement(user_input)

# --- Set up audio receiver using ggwave and pyaudio ---
p_audio = pyaudio.PyAudio()
stream = p_audio.open(format=pyaudio.paFloat32, channels=1, rate=48000, input=True, frames_per_buffer=1024)
print("Listening for audio commands... Press Ctrl+C to stop.")
instance = ggwave.init()

# --- Main Loop ---
if __name__ == "__main__":
    try:
        while True:
            data = stream.read(1024, exception_on_overflow=False)
            res = ggwave.decode(instance, data)
            if res is not None:
                try:
                    command = res.decode("utf-8")
                    print("Received text command: " + command)
                    # Process command using the agent
                    result = process_robot_command(command)
                    print("Agent Response: ", result)
                except Exception as e:
                    print("Error processing command:", e)
    except KeyboardInterrupt:
        pass
    finally:
        ggwave.free(instance)
        stream.stop_stream()
        stream.close()
        p_audio.terminate()
        print("Command processor terminated.")
