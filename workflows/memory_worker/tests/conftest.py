import sys
import os
import pytest

# Add the parent directory to sys.path to ensure activities module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) 