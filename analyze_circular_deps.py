#!/usr/bin/env python3
"""Analyze circular dependencies in Arrakis ontology-management-service"""
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

def extract_imports(file_path):
    """Extract import statements from a Python file"""
    imports = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Match various import patterns
        import_patterns = [
            r'^from\s+(\S+)\s+import',
            r'^import\s+(\S+)'
        ]
        
        for line in content.split('\n'):
            line = line.strip()
            for pattern in import_patterns:
                match = re.match(pattern, line)
                if match:
                    module = match.group(1)
                    # Only consider local modules
                    if not module.startswith('.') and any(module.startswith(prefix) for prefix in ['core', 'middleware', 'bootstrap', 'database', 'api', 'shared', 'models']):
                        imports.append(module)
                        
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    
    return imports

def get_module_from_path(file_path, base_path):
    """Convert file path to module path"""
    rel_path = os.path.relpath(file_path, base_path)
    module = rel_path.replace(os.sep, '.').replace('.py', '')
    return module

def analyze_dependencies(base_path):
    """Analyze all Python files for dependencies"""
    dependencies = defaultdict(set)
    file_to_module = {}
    
    # Find all Python files
    for root, dirs, files in os.walk(base_path):
        # Skip venv, __pycache__, and archive directories
        dirs[:] = [d for d in dirs if d not in ['venv', '__pycache__', '.git'] and not d.startswith('archive_')]
        
        for file in files:
            if file.endswith('.py') and not file.startswith('test_'):
                file_path = os.path.join(root, file)
                module = get_module_from_path(file_path, base_path)
                file_to_module[file_path] = module
                
                imports = extract_imports(file_path)
                for imp in imports:
                    # Convert import to module prefix
                    imp_parts = imp.split('.')
                    for i in range(1, len(imp_parts) + 1):
                        partial_module = '.'.join(imp_parts[:i])
                        dependencies[module].add(partial_module)
    
    return dependencies, file_to_module

def find_circular_dependencies(dependencies):
    """Find circular dependencies using DFS"""
    def dfs(node, path, visited, rec_stack):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        
        cycles = []
        
        for neighbor in dependencies.get(node, []):
            if neighbor in rec_stack:
                # Found a cycle
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycles.append(cycle)
            elif neighbor not in visited:
                cycles.extend(dfs(neighbor, path.copy(), visited, rec_stack))
        
        rec_stack.remove(node)
        return cycles
    
    visited = set()
    all_cycles = []
    
    for node in dependencies:
        if node not in visited:
            cycles = dfs(node, [], visited, set())
            all_cycles.extend(cycles)
    
    # Remove duplicate cycles
    unique_cycles = []
    seen = set()
    for cycle in all_cycles:
        # Normalize cycle (start with smallest element)
        if len(cycle) > 1:
            min_idx = cycle.index(min(cycle))
            normalized = tuple(cycle[min_idx:] + cycle[:min_idx])
            if normalized not in seen:
                seen.add(normalized)
                unique_cycles.append(list(normalized)[:-1])  # Remove duplicate last element
    
    return unique_cycles

def main():
    base_path = "/Users/isihyeon/Desktop/Arrakis-Project/ontology-management-service"
    
    print("Analyzing dependencies in Arrakis ontology-management-service...")
    print("=" * 80)
    
    dependencies, file_to_module = analyze_dependencies(base_path)
    
    # Find circular dependencies
    cycles = find_circular_dependencies(dependencies)
    
    if cycles:
        print(f"\n🔴 Found {len(cycles)} circular dependency patterns:\n")
        
        for i, cycle in enumerate(cycles, 1):
            print(f"{i}. Circular dependency chain:")
            for j, module in enumerate(cycle):
                if j < len(cycle) - 1:
                    print(f"   {module} → {cycle[j+1]}")
                else:
                    print(f"   {module} → {cycle[0]} (cycle completes)")
            print()
    else:
        print("\n✅ No circular dependencies found!")
    
    # Analyze specific problematic patterns
    print("\n" + "=" * 80)
    print("Analyzing specific dependency patterns...")
    
    # Check bootstrap → core → bootstrap
    bootstrap_to_core = []
    core_to_bootstrap = []
    
    for module, imports in dependencies.items():
        if module.startswith('bootstrap'):
            for imp in imports:
                if imp.startswith('core'):
                    bootstrap_to_core.append((module, imp))
        elif module.startswith('core'):
            for imp in imports:
                if imp.startswith('bootstrap'):
                    core_to_bootstrap.append((module, imp))
    
    if bootstrap_to_core and core_to_bootstrap:
        print("\n⚠️  Potential circular dependency between bootstrap and core:")
        print("\nBootstrap → Core:")
        for src, dst in bootstrap_to_core[:5]:
            print(f"  {src} imports {dst}")
        if len(bootstrap_to_core) > 5:
            print(f"  ... and {len(bootstrap_to_core) - 5} more")
            
        print("\nCore → Bootstrap:")
        for src, dst in core_to_bootstrap[:5]:
            print(f"  {src} imports {dst}")
        if len(core_to_bootstrap) > 5:
            print(f"  ... and {len(core_to_bootstrap) - 5} more")
    
    # Check middleware → core → middleware
    middleware_to_core = []
    core_to_middleware = []
    
    for module, imports in dependencies.items():
        if module.startswith('middleware'):
            for imp in imports:
                if imp.startswith('core'):
                    middleware_to_core.append((module, imp))
        elif module.startswith('core'):
            for imp in imports:
                if imp.startswith('middleware'):
                    core_to_middleware.append((module, imp))
    
    if middleware_to_core and core_to_middleware:
        print("\n⚠️  Potential circular dependency between middleware and core:")
        print("\nMiddleware → Core:")
        for src, dst in middleware_to_core[:5]:
            print(f"  {src} imports {dst}")
        if len(middleware_to_core) > 5:
            print(f"  ... and {len(middleware_to_core) - 5} more")
            
        print("\nCore → Middleware:")
        for src, dst in core_to_middleware[:5]:
            print(f"  {src} imports {dst}")
        if len(core_to_middleware) > 5:
            print(f"  ... and {len(core_to_middleware) - 5} more")
    
    # Check database → middleware → database
    database_to_middleware = []
    middleware_to_database = []
    
    for module, imports in dependencies.items():
        if module.startswith('database'):
            for imp in imports:
                if imp.startswith('middleware'):
                    database_to_middleware.append((module, imp))
        elif module.startswith('middleware'):
            for imp in imports:
                if imp.startswith('database'):
                    middleware_to_database.append((module, imp))
    
    if database_to_middleware and middleware_to_database:
        print("\n⚠️  Potential circular dependency between database and middleware:")
        print("\nDatabase → Middleware:")
        for src, dst in database_to_middleware[:5]:
            print(f"  {src} imports {dst}")
        if len(database_to_middleware) > 5:
            print(f"  ... and {len(database_to_middleware) - 5} more")
            
        print("\nMiddleware → Database:")
        for src, dst in middleware_to_database[:5]:
            print(f"  {src} imports {dst}")

if __name__ == "__main__":
    main()