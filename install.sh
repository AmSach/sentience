#!/bin/bash
echo "================================"
echo "Sentience v3.0 Installer"
echo "================================"
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Python not found. Please install Python 3.12+"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
pip3 install -r requirements.txt

# Install Playwright
echo "Installing browser..."
playwright install chromium

# Create config directory
mkdir -p ~/.sentience

# Create alias
echo ""
echo "Add to your shell config (~/.bashrc or ~/.zshrc):"
echo "  alias sentience='python3 $(pwd)/sentience.py'"
echo ""
echo "Then reload: source ~/.bashrc"

echo ""
echo "================================"
echo "Installation complete!"
echo "================================"
echo ""
echo "Set your API key:"
echo "  export OPENAI_API_KEY=sk-..."
echo "  or"
echo "  export GROQ_API_KEY=gsk-... (free)"
echo ""
echo "Run:"
echo "  python3 sentience.py --cli"
