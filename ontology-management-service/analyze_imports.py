#!/usr/bin/env python3
"""
Static import analysis to find unused modules
"""
import ast
import os
from pathlib import Path
from collections import defaultdict
import json

class ImportAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.imports = set()
        
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)
        
    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module)
        self.generic_visit(node)

def analyze_file(filepath):
    """Analyze a single Python file for imports"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        
        analyzer = ImportAnalyzer()
        analyzer.visit(tree)
        return analyzer.imports
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")
        return set()

def find_all_imports(root_dir):
    """Find all import relationships in the project"""
    import_graph = defaultdict(set)
    all_files = set()
    
    for root, dirs, files in os.walk(root_dir):
        # Skip venv and cache
        dirs[:] = [d for d in dirs if d not in ['venv', '__pycache__', '.git', 'node_modules']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = Path(root) / file
                relative_path = filepath.relative_to(root_dir)
                all_files.add(str(relative_path))
                
                # Analyze imports
                imports = analyze_file(filepath)
                
                # Convert imports to project-relative paths
                for imp in imports:
                    # Convert module path to file path
                    imp_parts = imp.split('.')
                    
                    # Check if it's a project module
                    if imp_parts[0] in ['api', 'core', 'database', 'middleware', 'shared', 'bootstrap']:
                        import_graph[str(relative_path)].add(imp)
                        
    return all_files, import_graph

def find_entry_points():
    """Find main entry points"""
    return [
        'main.py',
        'api/graphql/modular_main.py',
        'api/graphql/main.py',
        'bootstrap/app.py',
        'grpc_services/server.py'
    ]

def trace_dependencies(entry_points, import_graph, all_files):
    """Trace all dependencies from entry points"""
    used_files = set(entry_points)
    to_check = list(entry_points)
    
    while to_check:
        current = to_check.pop()
        
        # Get imports from current file
        for imp in import_graph.get(current, []):
            # Convert import to possible file paths
            imp_parts = imp.split('.')
            possible_paths = [
                f"{'/'.join(imp_parts)}.py",
                f"{'/'.join(imp_parts)}/__init__.py"
            ]
            
            for path in possible_paths:
                if path in all_files and path not in used_files:
                    used_files.add(path)
                    to_check.append(path)
                    
    return used_files

def main():
    root_dir = Path(__file__).parent
    print(f"🔍 Analyzing imports in {root_dir}")
    
    # Find all files and imports
    all_files, import_graph = find_all_imports(root_dir)
    print(f"📁 Found {len(all_files)} Python files")
    
    # Find entry points
    entry_points = find_entry_points()
    print(f"🚀 Entry points: {len(entry_points)}")
    
    # Trace dependencies
    used_files = trace_dependencies(entry_points, import_graph, all_files)
    print(f"✅ Used files: {len(used_files)}")
    
    # Find unused files
    unused_files = all_files - used_files
    print(f"❌ Potentially unused: {len(unused_files)}")
    
    # Categorize unused files
    categories = defaultdict(list)
    for file in unused_files:
        if file.startswith('tests/'):
            categories['tests'].append(file)
        elif file.startswith('scripts/'):
            categories['scripts'].append(file)
        elif file.startswith('migrations/'):
            categories['migrations'].append(file)
        elif 'archive' in file:
            categories['archive'].append(file)
        elif file.startswith('docs/'):
            categories['docs'].append(file)
        else:
            categories['other'].append(file)
    
    # Save results
    results = {
        'total_files': len(all_files),
        'used_files': len(used_files),
        'unused_files': len(unused_files),
        'categories': {k: sorted(v) for k, v in categories.items()}
    }
    
    with open('import_analysis.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n📊 Unused files by category:")
    for category, files in categories.items():
        print(f"\n{category.upper()} ({len(files)} files):")
        for file in sorted(files)[:5]:  # Show first 5
            print(f"  - {file}")
        if len(files) > 5:
            print(f"  ... and {len(files) - 5} more")
    
    print("\n✅ Full results saved to import_analysis.json")

if __name__ == '__main__':
    main()