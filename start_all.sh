#!/bin/bash

# --- Configuration Variables ---
VENV_DIR="/home/anguy131/kivy_venv"
SERVER_SCRIPT="Server.py"
RFID_SCRIPT="RFID.py" # Verified filename
CLIENT_SCRIPT="Client.py"

# --- Setup and Execution ---

echo "--- Starting CyberKart Applications (Launching Terminals) ---"

# 1. Change to the target directory
echo "1. Changing directory to: $VENV_DIR"
cd "$VENV_DIR" || { echo "Error: Failed to change directory. Exiting."; exit 1; }

# Helper command: This executes inside the new terminal. 
# It activates the venv, runs the Python script, and uses 'exec bash' to keep the window open after the script finishes.
LAUNCH_CMD='bash -c "source '$VENV_DIR'/bin/activate; python %s; exec bash"'

# 2. Start the Server (mqttserver_code(1).py) - MUST start first
echo "2. Starting MQTT Server..."
# The 'lxterminal' command launches the new terminal window.
lxterminal --title="MQTT Server" -e "$(printf "$LAUNCH_CMD" "$SERVER_SCRIPT")" &
SERVER_PID=$!
echo "   Server PID: $SERVER_PID. Waiting 5 seconds for initialization..."

sleep 5

# 3. Start the RFID Reader (rfid_final.py)
echo "3. Starting RFID Reader..."
lxterminal --title="RFID Reader" -e "$(printf "$LAUNCH_CMD" "$RFID_SCRIPT")" &
RFID_PID=$!
echo "   RFID Reader PID: $RFID_PID"

# 4. Start the Kivy Client (combinedmqttclient.py)
echo "4. Starting Kivy Client (GUI)..."
lxterminal --title="Kivy Client" -e "$(printf "$LAUNCH_CMD" "$CLIENT_SCRIPT")" &
CLIENT_PID=$!
echo "   Kivy Client PID: $CLIENT_PID"

echo ""
echo "=================================================="
echo "Startup Complete. Three terminal windows are open."
echo "=================================================="

exit 0