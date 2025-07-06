#!/usr/bin/env python3
"""
Runtime import tracer to find actually used modules
"""
import sys
import os
from pathlib import Path

# Track imported modules
imported_modules = set()
project_root = Path(__file__).parent.absolute()

class ImportTracer:
    def __init__(self):
        self.original_import = __builtins__.__import__
        
    def trace_import(self, name, *args, **kwargs):
        # Call original import
        module = self.original_import(name, *args, **kwargs)
        
        # Track if it's a project module
        if hasattr(module, '__file__') and module.__file__:
            module_path = Path(module.__file__).absolute()
            try:
                # Check if module is within project
                relative_path = module_path.relative_to(project_root)
                imported_modules.add(str(relative_path))
            except ValueError:
                # Module is outside project
                pass
                
        return module
    
    def start(self):
        __builtins__.__import__ = self.trace_import
        
    def stop(self):
        __builtins__.__import__ = self.original_import
        
    def get_results(self):
        return sorted(imported_modules)

# Start tracing
tracer = ImportTracer()
tracer.start()

# Import main app
try:
    from main import app
    print("✅ Successfully imported main app")
except Exception as e:
    print(f"❌ Failed to import main app: {e}")

# Import test suites
try:
    import pytest
    print("✅ Successfully imported pytest")
except Exception as e:
    print(f"❌ Failed to import pytest: {e}")

# Stop tracing
tracer.stop()

# Save results
with open('imported_modules.txt', 'w') as f:
    for module in tracer.get_results():
        f.write(f"{module}\n")

print(f"\n📊 Found {len(imported_modules)} imported modules")
print("Results saved to imported_modules.txt")

# Find all Python files
all_python_files = set()
for root, dirs, files in os.walk(project_root):
    # Skip venv and __pycache__
    dirs[:] = [d for d in dirs if d not in ['venv', '__pycache__', '.git']]
    
    for file in files:
        if file.endswith('.py'):
            file_path = Path(root) / file
            try:
                relative_path = file_path.relative_to(project_root)
                all_python_files.add(str(relative_path))
            except ValueError:
                pass

# Find unused files
unused_files = all_python_files - imported_modules

# Save unused files
with open('unused_modules.txt', 'w') as f:
    for module in sorted(unused_files):
        f.write(f"{module}\n")

print(f"📁 Total Python files: {len(all_python_files)}")
print(f"✅ Imported modules: {len(imported_modules)}")
print(f"❌ Potentially unused: {len(unused_files)}")
print("Unused modules saved to unused_modules.txt")