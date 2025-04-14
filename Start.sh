#!/bin/bash

# Set up a Python virtual environment and run main.py

# Variables
PYTHON_SCRIPT="main.py"
VENV_DIR="venv"
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
FAST_START="FALSE"

# Navigate to the script directory
cd "$SCRIPT_DIR" || {
    echo "Failed to set current directory."
    exit 1
}

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate" || {
    echo "Failed to activate virtual environment."
    exit 1
}

# Install dependencies if needed
if [ ! -d "$VENV_DIR/lib/python3."*/site-packages/PyQt6 ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Run the Python script
echo "Starting $PYTHON_SCRIPT..."
python3 "$PYTHON_SCRIPT"

# Deactivate virtual environment
deactivate

read -p "Press enter to continue..."