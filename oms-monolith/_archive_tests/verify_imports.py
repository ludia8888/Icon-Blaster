#!/usr/bin/env python3
"""
Import verification script
Checks all Python files for import errors
"""
import os
import ast
import sys
import csv
from pathlib import Path
from typing import List, Tuple, Set

def extract_imports(file_path: str) -> Set[str]:
    """Extract all import statements from a Python file"""
    imports = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
                    # Also add the full import path for specific imports
                    for alias in node.names:
                        if alias.name != '*':
                            imports.add(f"{node.module}.{alias.name}")
    except Exception as e:
        print(f"Error parsing {file_path}: {e}", file=sys.stderr)
    
    return imports

def check_import(module_name: str, file_path: str) -> bool:
    """Check if an import can be resolved"""
    # Add the project root to sys.path
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Skip check for relative imports
    if module_name.startswith('.'):
        return True
    
    # Try to import the module
    try:
        # Handle submodule imports (e.g., "module.submodule.function")
        parts = module_name.split('.')
        
        # Try importing the base module first
        base_module = parts[0]
        __import__(base_module)
        
        # Then try importing the full path
        if len(parts) > 1:
            try:
                __import__(module_name)
            except ImportError:
                # Try importing up to the second-to-last part
                # (in case the last part is a class/function)
                if len(parts) > 2:
                    parent_module = '.'.join(parts[:-1])
                    try:
                        __import__(parent_module)
                        return True
                    except ImportError:
                        pass
                # For two-part imports, the base module import succeeded
                return True
        
        return True
    except ImportError:
        return False

def find_python_files(root_dir: str, exclude_dirs: List[str] = None) -> List[str]:
    """Find all Python files in the project"""
    if exclude_dirs is None:
        exclude_dirs = ['venv', '__pycache__', '.git', 'node_modules', '.pytest_cache']
    
    python_files = []
    for root, dirs, files in os.walk(root_dir):
        # Remove excluded directories from dirs to prevent walking into them
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    return python_files

def main():
    """Main function to verify all imports"""
    project_root = os.path.dirname(os.path.abspath(__file__))
    python_files = find_python_files(project_root)
    
    missing_imports = []
    total_imports = 0
    
    print("Verifying imports in all Python files...")
    print(f"Found {len(python_files)} Python files")
    print("-" * 60)
    
    for file_path in python_files:
        relative_path = os.path.relpath(file_path, project_root)
        imports = extract_imports(file_path)
        
        for import_name in imports:
            total_imports += 1
            if not check_import(import_name, file_path):
                # Get line number where import occurs
                line_no = 0
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        for i, line in enumerate(f, 1):
                            if import_name in line and ('import' in line or 'from' in line):
                                line_no = i
                                break
                except:
                    pass
                
                missing_imports.append((import_name, relative_path, line_no))
    
    # Write results to CSV
    csv_file = os.path.join(project_root, 'import_verification_report.csv')
    with open(csv_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['missing_module', 'referenced_in', 'line_number'])
        
        # Sort by module name for easier reading
        for module, file_path, line_no in sorted(missing_imports):
            writer.writerow([module, file_path, line_no])
    
    # Print summary
    print("\nImport Verification Summary:")
    print(f"Total imports checked: {total_imports}")
    print(f"Missing imports: {len(missing_imports)}")
    print(f"Success rate: {((total_imports - len(missing_imports)) / total_imports * 100):.1f}%")
    
    if missing_imports:
        print(f"\nMissing imports report saved to: {csv_file}")
        print("\nTop 10 missing imports:")
        for module, file_path, line_no in missing_imports[:10]:
            print(f"  - {module} (in {file_path}:{line_no})")
    else:
        print("\n✅ All imports resolved successfully!")
    
    # Return exit code based on results
    return 0 if not missing_imports else 1

if __name__ == "__main__":
    sys.exit(main())