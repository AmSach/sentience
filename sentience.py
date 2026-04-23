#!/usr/bin/env python3
"""
Sentience v4.0 - Entry Point
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.engine import main

if __name__ == "__main__":
    main()
