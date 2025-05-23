# test_import.py
# Make sure this file is in your services/gateway/ directory

import sys
import os
from pathlib import Path
import types # New import for creating a module manually

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent.absolute()
# sys.path.insert(0, str(project_root)) # Keep this for general project path

print(f"DEBUG: sys.path before specific import: {sys.path}")

models_module_name = "services.gateway.app.db.models"
models_file_absolute_path = Path(__file__).parent.absolute() / "app" / "db" / "models.py"

print(f"DEBUG: Attempting to load and execute code from: {models_file_absolute_path}")

# --- ULTIMATE BYPASS ---
# Manually create a module object
temp_models_module = types.ModuleType(models_module_name)
temp_models_module.__file__ = str(models_file_absolute_path) # Set its __file__ attribute

# Read the content of the models.py file
try:
    with open(models_file_absolute_path, 'r') as f:
        models_code = f.read()
except FileNotFoundError:
    print(f"CRITICAL ERROR: models.py not found at {models_file_absolute_path}")
    sys.exit(1)
except Exception as e:
    print(f"CRITICAL ERROR: Could not read models.py: {e}")
    sys.exit(1)

print("\n--- Start models.py content (manually loaded) ---")
print(models_code)
print("--- End models.py content (manually loaded) ---\n")

# Execute the code from models.py in the context of the new module object
# This will run the 'print' statements inside models.py, and define Base/DummyClass
try:
    exec(models_code, temp_models_module.__dict__)
    sys.modules[models_module_name] = temp_models_module # Add to sys.modules for later imports

    # Now, try to access the classes from this *newly created* module object
    # This will be the true test of what was defined in the manually loaded file.
    Base = temp_models_module.Base
    DummyClassForTesting = temp_models_module.DummyClassForTesting
    
    print("SUCCESS: Manually loaded and accessed Base, DummyClassForTesting.")

except ImportError as e:
    print(f"FAILURE: ImportError AFTER MANUAL LOAD: {e}")
except AttributeError as e:
    print(f"FAILURE: AttributeError (class not found AFTER MANUAL LOAD): {e}")
except Exception as e:
    print(f"FAILURE: Other error AFTER MANUAL LOAD: {e}")

# No need for the original try/except block anymore, as we're doing it manually.