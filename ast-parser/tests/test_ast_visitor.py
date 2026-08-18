import sys
import json
from pathlib import Path
import pytest

# Append src to sys.path so tests can find and import modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from file_finder import find_python_files
from ast_visitor import parse_file
from path_resolver import resolve_all_imports, resolve_call

def test_file_finder(tmp_path):
    """
    Verifies that file_finder recursively finds Python files and respects the ignore list.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "venv").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "build").mkdir()
    (tmp_path / "dist").mkdir()
    
    (tmp_path / "src/main.py").write_text("def f(): pass")
    (tmp_path / "src/utils.py").write_text("def g(): pass")
    (tmp_path / "venv/lib.py").write_text("def h(): pass")
    (tmp_path / ".git/config.py").write_text("def i(): pass")
    (tmp_path / "__pycache__/cache.py").write_text("def j(): pass")
    (tmp_path / "build/out.py").write_text("def b(): pass")
    (tmp_path / "dist/dist.py").write_text("def d(): pass")
    (tmp_path / "root.py").write_text("def k(): pass")
    (tmp_path / "test.txt").write_text("not python")
    
    files = find_python_files(tmp_path)
    assert files == ["root.py", "src/main.py", "src/utils.py"]

def test_ast_parser_syntax_error(tmp_path):
    """
    Verifies that a file with SyntaxError throws a SyntaxError during parsing.
    """
    bad_file = tmp_path / "bad.py"
    bad_file.write_text("def crash(")
    
    with pytest.raises(SyntaxError):
        parse_file(bad_file)

def test_dependency_resolution_end_to_end(tmp_path):
    """
    End-to-end unit tests covering imports, relative imports, class methods, self references,
    transitive imports (re-exports), local calls, and external import exclusions.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src/database").mkdir()
    
    # 1. Define utility module
    (tmp_path / "src/utils.py").write_text("""
def helper():
    pass

def other_helper():
    pass
""")
    
    # 2. Define database submodule
    (tmp_path / "src/database/connection.py").write_text("""
def connect():
    pass
""")

    # 3. Define database package initializer (re-exporting connection using relative import)
    (tmp_path / "src/database/__init__.py").write_text("""
from .connection import connect
""")

    # 4. Define models module with classes and methods
    (tmp_path / "src/models.py").write_text("""
class User:
    def save(self):
        self.validate()
        
    def validate(self):
        pass
""")

    # 5. Define main entry point calling functions and class methods
    (tmp_path / "src/main.py").write_text("""
import os
import requests
from utils import helper
from database import connect
from models import User

def main():
    helper()
    helper()  # Duplicate call
    connect()
    User.save(None)
    local_func()

def local_func():
    pass
""")

    # 6. Syntax error file
    (tmp_path / "bad.py").write_text("def error_syntax(")

    files = find_python_files(tmp_path)
    file_functions = {}
    file_imports = {}
    
    for f in files:
        full_path = tmp_path / f
        try:
            funcs, imps = parse_file(full_path)
            file_functions[f] = funcs
            file_imports[f] = imps
        except SyntaxError:
            # Handle and skip bad.py syntax error
            continue

    # Verify that bad.py is successfully skipped
    assert "bad.py" not in file_functions
    
    # Resolve imports
    resolved_imports = resolve_all_imports(files, file_functions, file_imports)
    
    # Verify absolute and package imports
    main_imports = resolved_imports["src/main.py"]
    assert main_imports["helper"] == {"file": "src/utils.py", "name": "helper"}
    assert main_imports["connect"] == {"file": "src/database/__init__.py", "name": "connect"}
    assert main_imports["User"] == {"file": "src/models.py", "name": "User"}
    
    # Verify external libraries requests/os are not resolved into mock repository files
    assert "os" not in main_imports
    assert "requests" not in main_imports
    
    # Resolve calls for src/main.py::main
    repo_files_set = set(files)
    main_calls = file_functions["src/main.py"]["main"]
    resolved_targets = set()
    for call_info in main_calls:
        target = resolve_call(
            "src/main.py", "main", call_info,
            file_functions, resolved_imports, repo_files_set
        )
        if target:
            resolved_targets.add(target)
            
    # Verify expected resolution targets (with duplicate call to helper de-duplicated into a set)
    expected_targets = {
        "src/utils.py::helper",
        "src/database/connection.py::connect",  # Transitively resolved
        "src/models.py::User.save",
        "src/main.py::local_func"
    }
    assert resolved_targets == expected_targets
    
    # Resolve class method calls using self
    save_calls = file_functions["src/models.py"]["User.save"]
    resolved_save_targets = set()
    for call_info in save_calls:
        target = resolve_call(
            "src/models.py", "User.save", call_info,
            file_functions, resolved_imports, repo_files_set
        )
        if target:
            resolved_save_targets.add(target)
            
    assert resolved_save_targets == {"src/models.py::User.validate"}
