"""
This file helps set the Python path correctly in Docker environments.
Import this at the top of your entry point scripts.
"""
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root)) 