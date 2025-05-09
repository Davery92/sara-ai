"""
This module initializes the import structure for the gateway app.
It's designed to be imported at the top of entry point files like main.py.
"""
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Add app directory to Python path for direct imports like 'from app import X'
app_dir = Path(__file__).parent.absolute()
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir)) 