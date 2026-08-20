import ast

class DependencyVisitor(ast.NodeVisitor):
    """
    AST visitor to find function/method definitions, function calls, and import statements.
    """
    def __init__(self):
        # Maps function name (including class scope) -> list of CallNode target details
        self.functions = {}
        # List of import statement details
        self.imports = []
        # Scope stack to track classes and nested functions/methods
        self.scope_stack = []
        # Current active function/method scope name (e.g. Class.method)
        self.current_function = "<module>"
        self.functions["<module>"] = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({
                'type': 'import',
                'name': alias.name,
                'asname': alias.asname or alias.name
            })
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            self.imports.append({
                'type': 'import_from',
                'module': node.module,
                'level': node.level,
                'name': alias.name,
                'asname': alias.asname or alias.name
            })
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.scope_stack.append(node.name)
        self.generic_visit(node)
        self.scope_stack.pop()

    def visit_FunctionDef(self, node):
        self.scope_stack.append(node.name)
        func_name = ".".join(self.scope_stack)
        
        # Track previous context for nested functions
        prev_func = self.current_function
        self.current_function = func_name
        self.functions[func_name] = []
        
        self.generic_visit(node)
        
        self.current_function = prev_func
        self.scope_stack.pop()

    def visit_AsyncFunctionDef(self, node):
        self.visit_FunctionDef(node)

    def visit_Call(self, node):
        call_info = self._resolve_call_node(node.func)
        if call_info:
            self.functions[self.current_function].append(call_info)
        self.generic_visit(node)

    def _resolve_call_node(self, node):
        """
        Extracts structural details of the function call target.
        Returns:
            - {'type': 'name', 'name': 'func'} for simple calls.
            - {'type': 'attribute', 'value': 'self', 'attr': 'method'} for attribute calls.
            - None if unresolvable statically.
        """
        if isinstance(node, ast.Name):
            return {'type': 'name', 'name': node.id}
        elif isinstance(node, ast.Attribute):
            val_str = self._resolve_attribute_value(node.value)
            if val_str:
                return {'type': 'attribute', 'value': val_str, 'attr': node.attr}
        return None

    def _resolve_attribute_value(self, node):
        """
        Recursively resolves the value of an Attribute node to a dot-separated string.
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._resolve_attribute_value(node.value)
            if val:
                return f"{val}.{node.attr}"
        return None

def parse_file(file_path):
    """
    Helper function to parse a file's content and extract details.
    Raises SyntaxError if content has invalid python syntax.
    """
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # ast.parse raises SyntaxError if syntax is invalid
    tree = ast.parse(content, filename=str(file_path))
    visitor = DependencyVisitor()
    visitor.visit(tree)
    return visitor.functions, visitor.imports
