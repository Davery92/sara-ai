# test_import.py
# Make sure this file is in your services/gateway/ directory

import sys
import os
from pathlib import Path
import types # New import for creating a module manually

# Ensure the root of the repository is in the Python path
# This allows imports like 'services.gateway.app.db.models' to resolve correctly
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

print(f"DEBUG: sys.path before specific import: {sys.path}")

# Now, import directly from the source structure, as the application would
try:
    from services.gateway.app.db.models import Base, EmbeddingMessage, User, Chat, ChatMessage, Memory # Ensure all models are imported
    print("SUCCESS: Directly imported models from services.gateway.app.db.models.")
    
    # You can now test properties of these imported classes
    # For example, to check the type of EmbeddingMessage.embedding
    # print(f"DEBUG: Type of EmbeddingMessage.embedding: {EmbeddingMessage.embedding.type}")
    
except ImportError as e:
    print(f"FAILURE: Could not import models directly from services.gateway.app.db.models: {e}")
    print("This means the Python path setup for this script is incorrect or the module structure is unexpected.")
    sys.exit(1)
except AttributeError as e:
    print(f"FAILURE: Attribute error after import (e.g., class not found): {e}")
    sys.exit(1)
except Exception as e:
    print(f"FAILURE: Unexpected error during direct import: {e}")
    sys.exit(1)

# The rest of the test_import.py script can then use these imported classes
# No need for manual file reading and exec() if the import works directly.
# Remove the manual `exec` block entirely.
# The original purpose of `test_import.py` was likely to debug a `PYTHONPATH` issue.
# If this direct import now works, the `PYTHONPATH` setup is confirmed correct for the source files.