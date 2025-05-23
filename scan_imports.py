# scan_imports.py
import os
import re

def scan_project_for_import(project_root_dir, import_string_pattern):
    """
    Scans the project directory for Python files containing a specific import pattern.

    Args:
        project_root_dir (str): The root directory of your project.
        import_string_pattern (str): The regular expression pattern to search for in import statements.
                                     Example: r"from .*models import Message"
    Returns:
        list: A list of file paths where the pattern was found.
    """
    found_files = []
    import_regex = re.compile(import_string_pattern)

    for root, dirs, files in os.walk(project_root_dir):
        # Exclude common directories that don't contain source code
        dirs[:] = [d for d in dirs if d not in ['.git', 'env', '__pycache__', 'node_modules', '.next', 'build', 'dist', '.venv']]
        
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line_num, line in enumerate(f, 1):
                            if import_regex.search(line):
                                print(f"Found in: {file_path}:{line_num}: {line.strip()}")
                                found_files.append(file_path)
                                break # Found in this file, move to next file
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
    return found_files

if __name__ == "__main__":
    project_root = os.path.abspath(os.path.dirname(__file__))
    
    # Define the pattern to search for.
    # We are looking for "from [anything].models import Message"
    # The 'r' before the string makes it a raw string, good for regex.
    # '.*' matches any character (except newline) zero or more times.
    # 'Message\\b' ensures it's the whole word 'Message' (not 'MessageFoo').
    problematic_import_pattern = r"from .*models import Message\b"

    print(f"Scanning project root: {project_root}")
    print(f"Searching for import pattern: '{problematic_import_pattern}'")
    
    files_with_problem = scan_project_for_import(project_root, problematic_import_pattern)
    
    if files_with_problem:
        print("\n--- Summary of files with problematic import ---")
        for f in files_with_problem:
            print(f)
        print("\nPlease check and update these files to use 'EmbeddingMessage' instead.")
    else:
        print("\nNo files found with the problematic import pattern. This is good!")