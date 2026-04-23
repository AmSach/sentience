#!/bin/bash
echo "================================"
echo "  Sentience v4.0 Installer"
echo "================================"
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found. Please install Python 3.10+"
    exit 1
fi

echo "[1/3] Installing core dependencies..."
pip3 install flask flask-cors requests lz4 psutil --quiet

echo "[2/3] Installing optional dependencies..."
pip3 install sentence-transformers chromadb numpy --quiet 2>/dev/null || true

echo "[3/3] Installing GUI dependencies..."
pip3 install PySide6 --quiet 2>/dev/null || true

echo
echo "================================"
echo "  Installation Complete!"
echo "================================"
echo
echo "Next steps:"
echo "1. Get a free API key from https://console.groq.com"
echo "2. Set it: export GROQ_API_KEY=gsk_your_key_here"
echo "3. Run: python3 sentience.py"
echo
echo "Or use Ollama for 100% local:"
echo "1. Install: https://ollama.com"
echo "2. Run: ollama pull llama3.2"
echo "3. Run: python3 sentience.py"
