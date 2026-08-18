import os
from pathlib import Path

def find_python_files(repo_root):
    """
    Recursively scans the repo_root directory to find all Python (.py) files.
    Returns relative paths with forward slashes, ignoring common virtual envs, 
    caches, and build directories.
    """
    root = Path(repo_root).resolve()
    python_files = []
    
    ignore_dirs = {
        '.git', '.venv', 'venv', 'env', 'site-packages', 
        '__pycache__', 'build', 'dist'
    }
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Modify dirnames in-place to prevent os.walk from recursing into ignored dirs
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        
        for filename in filenames:
            if filename.endswith('.py'):
                full_path = Path(dirpath) / filename
                try:
                    rel_path = full_path.relative_to(root)
                    python_files.append(rel_path.as_posix())
                except ValueError:
                    # Handle edge cases where paths cannot be made relative
                    pass
                    
    # Sort paths for deterministic output
    python_files.sort()
    return python_files
