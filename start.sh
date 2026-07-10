#!/bin/bash
clear

# Keep the Mac awake for as long as this script is running.
# caffeinate -w $$ watches this script's own PID and exits automatically
# once this script exits, so sleep-prevention never outlives the agent.
caffeinate -dis -w $$ &
CAFFEINATE_PID=$!

# Make sure caffeinate is cleaned up no matter how this script ends
# (normal exit, error, or Ctrl+C).
trap 'kill "$CAFFEINATE_PID" 2>/dev/null' EXIT

source .venv/bin/activate
python3 onboard.py
python3 app.py
deactivate