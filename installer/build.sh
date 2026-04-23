#!/bin/bash
# Sentience Windows Build Script
echo "Building Sentience..."
pip install -r requirements.txt
playwright install chromium --with-deps
pyinstaller --name=Sentience --onefile --windowed \
  --add-data="ui:ui" \
  --add-data="agent:agent" \
  --add-data="browser:browser" \
  --add-data="memory:memory" \
  --add-data="storage:storage" \
  --add-data="integrations:integrations" \
  --hidden-import=flask --hidden-import=flask_cors \
  --hidden-import=playwright --hidden-import=lz4.frame \
  sentience.py
echo "Done: dist/Sentience.exe"
