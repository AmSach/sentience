#!/usr/bin/env python3
"""Build Windows installer with PyInstaller."""
import os, sys, subprocess, shutil

def build_windows():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))
    print("Building Sentience Windows installer...")
    
    pyinstaller_args = [
        "pyinstaller", "--name=Sentience", "--onefile", "--windowed",
        "--add-data=ui:ui", "--add-data=browser:browser", "--add-data=agent:agent",
        "--add-data=memory:memory", "--add-data=storage:storage", "--add-data=integrations:integrations",
        "--hidden-import=flask", "--hidden-import=flask_cors",
        "--hidden-import=playwright", "--hidden-import=lz4.frame",
        "--collect-all=playwright", "--collect-all=lz4",
        "sentience.py", "--distpath=dist/windows", "--workpath=build"
    ]
    
    result = subprocess.run(["pip", "install", "pyinstaller"], capture_output=True)
    result = subprocess.run(pyinstaller_args, capture_output=True, text=True)
    if result.returncode == 0:
        print("Build successful: dist/windows/Sentience.exe")
    else:
        print(f"Build failed: {result.stderr[-500:]}")
