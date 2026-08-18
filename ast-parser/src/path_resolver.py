from pathlib import Path

def get_possible_module_files(base_dir_parts, module_parts):
    """
    Generates candidate python file paths for a module given its name parts.
    E.g. base_dir=['src'], module=['utils'] -> ['src/utils.py', 'src/utils/__init__.py']
    """
    joined_parts = base_dir_parts + module_parts
    path_str = "/".join(joined_parts)
    
    candidates = []
    if path_str:
        candidates.append(f"{path_str}.py")
        candidates.append(f"{path_str}/__init__.py")
    else:
        candidates.append("__init__.py")
    return candidates

def resolve_all_imports(repo_files, file_functions, file_imports):
    """
    Resolves all import statements inside the repository to concrete paths.
    Returns: dict of file_path -> dict of local_name -> symbol_info
    """
    repo_files_set = set(repo_files)
    resolved_imports = {}
    
    for file_path, imports in file_imports.items():
        local_symbols = {}
        # Get relative directory parts of the importing file
        file_dir_parts = Path(file_path).parent.as_posix().split('/')
        if file_dir_parts == ['.'] or file_dir_parts == ['']:
            file_dir_parts = []
            
        for imp in imports:
            if imp['type'] == 'import':
                parts = imp['name'].split('.')
                resolved_module = None
                matched_parts_count = 0
                
                # Check absolute imports relative to local file directory, then relative to root
                for root_relative in [False, True]:
                    base_parts = [] if root_relative else file_dir_parts
                    for i in range(len(parts), 0, -1):
                        sub_parts = parts[:i]
                        candidates = get_possible_module_files(base_parts, sub_parts)
                        for cand in candidates:
                            if cand in repo_files_set:
                                resolved_module = cand
                                matched_parts_count = i
                                break
                        if resolved_module:
                            break
                    if resolved_module:
                        break
                
                if resolved_module:
                    if imp['asname'] != imp['name']:
                        # Alias is used
                        local_symbols[imp['asname']] = {
                            'file': resolved_module,
                            'is_module': True,
                            'remaining_parts': parts[matched_parts_count:]
                        }
                    else:
                        # No alias, map the exact prefix that resolved
                        resolved_prefix = ".".join(parts[:matched_parts_count])
                        local_symbols[resolved_prefix] = {
                            'file': resolved_module,
                            'is_module': True,
                            'remaining_parts': parts[matched_parts_count:]
                        }
                        
            elif imp['type'] == 'import_from':
                module_str = imp['module']
                module_parts = module_str.split('.') if module_str else []
                level = imp['level']
                
                if level > 0:
                    # Relative import
                    parents = list(Path(file_path).parents)
                    if level <= len(parents):
                        base_dir_path = parents[level - 1].as_posix()
                        base_parts = base_dir_path.split('/') if base_dir_path not in ('.', '') else []
                    else:
                        base_parts = []
                else:
                    # Absolute import
                    base_parts = file_dir_parts
                    
                resolved_module = None
                
                if level > 0:
                    candidates = get_possible_module_files(base_parts, module_parts)
                    for cand in candidates:
                        if cand in repo_files_set:
                            resolved_module = cand
                            break
                else:
                    # Try local directory first
                    candidates = get_possible_module_files(base_parts, module_parts)
                    for cand in candidates:
                        if cand in repo_files_set:
                            resolved_module = cand
                            break
                    # If not resolved, try root-relative
                    if not resolved_module:
                        candidates = get_possible_module_files([], module_parts)
                        for cand in candidates:
                            if cand in repo_files_set:
                                resolved_module = cand
                                break
                                
                if resolved_module:
                    name = imp['name']
                    asname = imp['asname']
                    
                    is_submodule = False
                    if resolved_module.endswith('__init__.py'):
                        package_dir = resolved_module[:-12]
                        submodule_path = f"{package_dir}/{name}.py" if package_dir else f"{name}.py"
                        submodule_init_path = f"{package_dir}/{name}/__init__.py" if package_dir else f"{name}/__init__.py"
                        if submodule_path in repo_files_set:
                            local_symbols[asname] = {
                                'file': submodule_path,
                                'is_module': True
                            }
                            is_submodule = True
                        elif submodule_init_path in repo_files_set:
                            local_symbols[asname] = {
                                'file': submodule_init_path,
                                'is_module': True
                            }
                            is_submodule = True
                            
                    if not is_submodule:
                        local_symbols[asname] = {
                            'file': resolved_module,
                            'name': name
                        }
                else:
                    if level > 0 and not module_str:
                        name = imp['name']
                        asname = imp['asname']
                        candidates = get_possible_module_files(base_parts, [name])
                        for cand in candidates:
                            if cand in repo_files_set:
                                local_symbols[asname] = {
                                    'file': cand,
                                    'is_module': True
                                }
                                break
                                
        resolved_imports[file_path] = local_symbols
        
    return resolved_imports

def resolve_symbol_transitively(file_path, symbol_name, file_functions, resolved_imports, visited=None):
    """
    Transitively resolves a symbol in a file to its definition target in the repo (resolves re-exports).
    """
    if visited is None:
        visited = set()
        
    state = (file_path, symbol_name)
    if state in visited:
        return None
    visited.add(state)
    
    defined_funcs = file_functions.get(file_path, [])
    if symbol_name in defined_funcs:
        return f"{file_path}::{symbol_name}"
        
    # Check imports
    file_imports = resolved_imports.get(file_path, {})
    if symbol_name in file_imports:
        imp_info = file_imports[symbol_name]
        if 'name' in imp_info:
            return resolve_symbol_transitively(
                imp_info['file'], imp_info['name'], 
                file_functions, resolved_imports, visited
            )
    return None

def resolve_attribute_chain(current_file, value_str, attr, file_functions, resolved_imports, repo_files_set):
    """
    Resolves call attribute chains (e.g. 'utils.submodule.func()') to concrete definition targets.
    """
    file_imports = resolved_imports.get(current_file, {})
    
    # 1. Direct match check
    if value_str in file_imports:
        imp_info = file_imports[value_str]
        if imp_info.get('is_module'):
            return resolve_symbol_transitively(
                imp_info['file'], attr, file_functions, resolved_imports
            )
            
    # 2. Part-by-part resolution for packages and submodules
    parts = value_str.split('.')
    p0 = parts[0]
    if p0 not in file_imports:
        return None
        
    imp_info = file_imports[p0]
    current_target = imp_info['file']
    
    for part in parts[1:]:
        if current_target.endswith('__init__.py'):
            package_dir = current_target[:-12]
            sub_py = f"{package_dir}/{part}.py" if package_dir else f"{part}.py"
            sub_init = f"{package_dir}/{part}/__init__.py" if package_dir else f"{part}/__init__.py"
            if sub_py in repo_files_set:
                current_target = sub_py
            elif sub_init in repo_files_set:
                current_target = sub_init
            else:
                return None
        else:
            return None
            
    if current_target.endswith('__init__.py'):
        package_dir = current_target[:-12]
        sub_py = f"{package_dir}/{attr}.py" if package_dir else f"{attr}.py"
        sub_init = f"{package_dir}/{attr}/__init__.py" if package_dir else f"{attr}/__init__.py"
        if sub_py in repo_files_set:
            return f"{sub_py}::<module>"
        elif sub_init in repo_files_set:
            return f"{sub_init}::<module>"
            
    return resolve_symbol_transitively(current_target, attr, file_functions, resolved_imports)

def resolve_call(current_file, current_scope, call_info, file_functions, resolved_imports, repo_files_set):
    """
    Resolves a Call target to its target 'file.py::func_name' definition in the repo.
    """
    file_imports = resolved_imports.get(current_file, {})
    
    if call_info['type'] == 'name':
        name = call_info['name']
        
        # 1. Local function call check
        if name in file_functions.get(current_file, []):
            return f"{current_file}::{name}"
            
        # 2. Transitive import check
        res = resolve_symbol_transitively(current_file, name, file_functions, resolved_imports)
        if res:
            return res
            
    elif call_info['type'] == 'attribute':
        value_str = call_info['value']
        attr = call_info['attr']
        
        # 1. Class method called on self: self.method()
        if value_str == 'self':
            if '.' in current_scope:
                class_name = current_scope.rsplit('.', 1)[0]
                local_method = f"{class_name}.{attr}"
                if local_method in file_functions.get(current_file, []):
                    return f"{current_file}::{local_method}"
            return None
            
        # 2. Local class method check: ClassName.method()
        local_class_method = f"{value_str}.{attr}"
        if local_class_method in file_functions.get(current_file, []):
            return f"{current_file}::{local_class_method}"
            
        # 3. Imported class method call check: from models import User; User.save()
        if value_str in file_imports:
            imp_info = file_imports[value_str]
            if 'name' in imp_info:
                target_class_method = f"{imp_info['name']}.{attr}"
                res = resolve_symbol_transitively(imp_info['file'], target_class_method, file_functions, resolved_imports)
                if res:
                    return res
                    
        # 4. Imported module attribute call check: import utils; utils.helper()
        res = resolve_attribute_chain(current_file, value_str, attr, file_functions, resolved_imports, repo_files_set)
        if res:
            return res
            
    return None
