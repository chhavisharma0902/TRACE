import argparse
import json
import sys
from pathlib import Path

# Add import fallbacks depending on how the script is executed
try:
    from file_finder import find_python_files
    from ast_visitor import parse_file
    from path_resolver import resolve_all_imports, resolve_call
except ImportError:
    try:
        from src.file_finder import find_python_files
        from src.ast_visitor import parse_file
        from src.path_resolver import resolve_all_imports, resolve_call
    except ImportError:
        # If run from outside, append src directory to system path
        src_path = str(Path(__file__).parent)
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        from file_finder import find_python_files
        from ast_visitor import parse_file
        from path_resolver import resolve_all_imports, resolve_call

def main():
    parser = argparse.ArgumentParser(description="Static dependency analysis parser utilizing AST.")
    parser.add_argument("repo_root", help="Path to the repository root directory to analyze.")
    args = parser.parse_args()
    
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.is_dir():
        print(f"Error: Repository root '{repo_root}' does not exist or is not a directory.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Scanning repository at: {repo_root}")
    python_files = find_python_files(repo_root)
    print(f"Found {len(python_files)} python files.")
    
    file_functions = {}
    file_imports = {}
    file_function_ranges = {}
    
    for file_path in python_files:
        full_path = repo_root / file_path
        try:
            funcs, imps , ranges= parse_file(full_path)
            file_functions[file_path] = funcs
            file_imports[file_path] = imps
            file_function_ranges[file_path] = ranges
        except SyntaxError as e:
            print(f"SyntaxError parsing {file_path}: {e}")
            continue
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            continue
            
    print("Resolving dependencies...")
    repo_files_set = set(python_files)
    resolved_imports = resolve_all_imports(python_files, file_functions, file_imports)
    
    dependencies = {}
    for file_path, funcs in file_functions.items():
        for func_name, calls in funcs.items():
            key = f"{file_path}::{func_name}"
            dep_set = set()
            for call_info in calls:
                target = resolve_call(
                    file_path, func_name, call_info, 
                    file_functions, resolved_imports, repo_files_set
                )
                if target:
                    dep_set.add(target)
            # Ensure dependencies are sorted and de-duplicated
            dependencies[key] = sorted(list(dep_set))
            
    # Sort keys for deterministic, reproducible output
    sorted_dependencies = {k: dependencies[k] for k in sorted(dependencies.keys())}
    
    # Ensure the output directory exists relative to this script
    script_dir = Path(__file__).parent.parent
    output_dir = script_dir / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "ast_dependencies.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sorted_dependencies, f, indent=4)
        
    print(f"Successfully generated dependency analysis. Saved output to {output_file}")

    ranges_output = {}
    for file_path, ranges in file_function_ranges.items():
        for func_name, (start, end) in ranges.items():
            key = f"{file_path}::{func_name}"
            ranges_output[key] = [start, end]

    ranges_file = output_dir / "function_ranges.json"
    with open(ranges_file, 'w', encoding='utf-8') as f:
        json.dump(ranges_output, f, indent=4)

    print(f"Also saved function line ranges to {ranges_file}")
if __name__ == "__main__":
    main()
