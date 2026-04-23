#!/bin/bash
echo "========================================"
echo "  Sentience - Local AI Computer"
echo "========================================"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python not found!"
    echo "Please install Python 3.10+"
    exit 1
fi

# Create venv
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create config dir
mkdir -p ~/.sentience

echo ""
echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo ""
echo "To run Sentience:"
echo "  1. Set your API key:"
echo "     export GROQ_API_KEY=your_key_here"
echo ""
echo "  2. Run: python src/main.py"
echo ""
echo "Get free API key from: https://console.groq.com"
