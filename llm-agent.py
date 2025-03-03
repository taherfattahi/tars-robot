import os
import getpass
import sys
import time
import signal
import re

# --- Audio Imports ---
import ggwave
import pyaudio

# --- LangChain and Robot Imports ---
from langchain_openai import ChatOpenAI
from langchain.agents import initialize_agent
from langchain.tools import Tool
import HiwonderSDK.mecanum as mecanum

# Append custom module path if needed
sys.path.append('/home/pi/TurboPi/')

# --- Set OpenAI API Key ---
if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = getpass.getpass("Enter your OpenAI API key: ")

# --- Initialize the ChatOpenAI LLM ---
llm = ChatOpenAI(
    openai_api_key=os.environ["OPENAI_API_KEY"],
    model="gpt-4-turbo",
    temperature=0
)

# --- Initialize the chassis ---
chassis = mecanum.MecanumChassis()
start = True

# --- Constants ---
SPEED = 50              # Speed (0-100)
FORWARD_DIRECTION = 90  # Forward direction in degrees (90 is forward)
MAX_SPEED_CMPS = 50     # Maximum speed in cm/s at 100% power

# --- Signal Handler for Graceful Exit ---
def stop_handler(signum, frame):
    global start
    start = False
    print("Stopping robot...")
    chassis.set_velocity(0, 0, 0)

signal.signal(signal.SIGINT, stop_handler)

# --- Movement Helper Functions ---
def get_move_duration(distance: int, speed: int = SPEED) -> float:
    """Calculate movement duration based on distance and speed."""
    actual_speed = (speed / 100) * MAX_SPEED_CMPS  # in cm/s
    return distance / actual_speed

def execute_robot_command(distance: int, turn_direction: str = None) -> str:
    """
    Execute a robot movement command.
    
    Args:
        distance: Distance to move forward (in cm).
        turn_direction: "left", "right", or None.
    
    Returns:
        A description of the executed action.
    """
    try:
        if not isinstance(distance, int) or distance <= 0:
            return "Invalid distance value. Please provide a positive number."
        if turn_direction and turn_direction.lower() not in ["left", "right"]:
            return "Invalid turn direction. Use 'left' or 'right'."
        
        duration = get_move_duration(distance)
        print(f"Moving forward {distance} cm for {duration:.2f} seconds.")
        chassis.set_velocity(SPEED, FORWARD_DIRECTION, 0)
        time.sleep(duration)
        
        # Stop briefly before turning
        chassis.set_velocity(0, 0, 0)
        time.sleep(0.5)
        
        result = f"Moved forward {distance} cm"
        if turn_direction:
            turn_direction = turn_direction.lower()
            angular_rate = 0.5 if turn_direction == "left" else -0.5
            print(f"Turning {turn_direction} for 1.5 seconds.")
            chassis.set_velocity(0, 0, angular_rate)
            time.sleep(1.5)
            chassis.set_velocity(0, 0, 0)
            time.sleep(0.5)
            result += f" and turned {turn_direction}"
        
        return result + "."
    except Exception as e:
        chassis.set_velocity(0, 0, 0)
        return f"Error executing command: {str(e)}"

def parse_movement_command(command_str: str) -> dict:
    """
    Parse a command string to extract movement parameters.
    
    Args:
        command_str: Structured command text.
        
    Returns:
        Dictionary with keys 'distance' and 'turn_direction'.
    """
    distance_match = re.search(r'(\d+)\s*(?:cm|centimeters?)', command_str, re.IGNORECASE)
    turn_match = re.search(r'turn\s+(left|right)', command_str, re.IGNORECASE)
    distance = int(distance_match.group(1)) if distance_match else None
    turn_direction = turn_match.group(1).lower() if turn_match else None
    return {"distance": distance, "turn_direction": turn_direction}

# --- Extraction Function Using ChatOpenAI Directly ---
def extract_movement_command(user_input: str) -> str:
    """
    Extract a structured movement command from natural language input 
    using ChatOpenAI directly.
    
    Args:
        user_input: Raw natural language command.
        
    Returns:
        A structured command like "move 30 cm and turn left", or an empty string if none is found.
    """
    prompt = (
        f"Extract the movement command from the following input: \"{user_input}\"\n\n"
        "If the input contains a command to move the robot, respond with a structured command in the format:\n"
        "\"move [distance] cm\" or \"move [distance] cm and turn [left/right]\".\n\n"
        "If no valid movement command is found, respond with \"No valid movement command found.\""
    )
    response = llm.invoke([("system", prompt)])
    extracted = response.content.strip()
    if "No valid movement command found" in extracted:
        return ""
    return extracted

# --- Define the Tool Function ---
def robot_movement_tool_function(user_input: str) -> str:
    """
    Process the input: extract a structured movement command and execute it.
    
    Args:
        user_input: Natural language command.
    
    Returns:
        Result of executing the movement command.
    """
    extracted_command = extract_movement_command(user_input)
    if not extracted_command:
        return "No valid movement command detected."
    params = parse_movement_command(extracted_command)
    if params["distance"] is None:
        return "Extracted command is missing a valid distance."
    return execute_robot_command(distance=params["distance"], turn_direction=params["turn_direction"])

# --- Create a Tool for robot movement ---
robot_movement_tool = Tool(
    name="RobotMovement",
    func=robot_movement_tool_function,
    description=(
        "Executes robot movement commands. Input should be a natural language "
        "instruction that includes a distance (in cm) and an optional turn direction (left or right)."
    )
)

# --- Initialize the Agent using initialize_agent ---
agent = initialize_agent(
    tools=[robot_movement_tool],
    llm=llm,
    agent="zero-shot-react-description",
    verbose=True
)

# --- Set up audio receiver using ggwave and pyaudio ---
p_audio = pyaudio.PyAudio()
stream = p_audio.open(format=pyaudio.paFloat32, channels=1, rate=48000, input=True, frames_per_buffer=1024)
print("Listening for audio commands... Press Ctrl+C to stop.")
instance = ggwave.init()

# --- Main Loop ---
if __name__ == "__main__":
    try:
        while start:
            data = stream.read(1024, exception_on_overflow=False)
            res = ggwave.decode(instance, data)
            if res is not None:
                try:
                    command = res.decode("utf-8")
                    print("Received text command: " + command)
                    # Process command using the agent
                    response = agent.run(command)
                    print("Agent Response:", response)
                except Exception as e:
                    print("Error processing command:", e)
    except KeyboardInterrupt:
        pass
    finally:
        ggwave.free(instance)
        stream.stop_stream()
        stream.close()
        p_audio.terminate()
        chassis.set_velocity(0, 0, 0)
        print("Command processor terminated.")
