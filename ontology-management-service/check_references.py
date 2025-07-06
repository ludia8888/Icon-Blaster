#!/usr/bin/env python3
"""
Check references to potentially unused files
"""
import subprocess
import json
from pathlib import Path

# Load the analysis results
with open('import_analysis.json', 'r') as f:
    analysis = json.load(f)

# Files to check (excluding tests and scripts)
files_to_check = [
    f for f in analysis['categories'].get('other', [])
    if not f.endswith('__init__.py') and 
    not f.startswith('test_') and
    not f == 'analyze_imports.py' and
    not f == 'trace_imports.py' and
    not f == 'check_references.py'
]

print(f"🔍 Checking references for {len(files_to_check)} files...")

# Categories for organization
definitely_unused = []
possibly_used = []
dynamically_imported = []

for file in files_to_check[:20]:  # Check first 20 files
    # Get module name from file path
    module_name = file.replace('/', '.').replace('.py', '')
    base_name = Path(file).stem
    
    # Search for imports
    import_patterns = [
        f"from {module_name}",
        f"import {module_name}",
        f"'{module_name}'",
        f'"{module_name}"',
        base_name
    ]
    
    found = False
    references = []
    
    for pattern in import_patterns:
        try:
            result = subprocess.run(
                ['grep', '-r', pattern, '.', '--include=*.py', '--exclude-dir=venv'],
                capture_output=True,
                text=True
            )
            
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                # Filter out self-references
                external_refs = [
                    line for line in lines 
                    if not line.startswith(f"./{file}:") and line.strip()
                ]
                
                if external_refs:
                    found = True
                    references.extend(external_refs[:3])  # Keep first 3 references
                    
        except Exception as e:
            print(f"Error searching for {pattern}: {e}")
    
    if found:
        possibly_used.append({
            'file': file,
            'references': references[:3]
        })
    else:
        definitely_unused.append(file)
    
    print(f"{'✅' if found else '❌'} {file}")

# Save results
results = {
    'definitely_unused': definitely_unused,
    'possibly_used': possibly_used,
    'total_checked': len(files_to_check),
    'sample_size': min(20, len(files_to_check))
}

with open('reference_check.json', 'w') as f:
    json.dump(results, f, indent=2)

print(f"\n📊 Results:")
print(f"❌ Definitely unused: {len(definitely_unused)}")
print(f"⚠️  Possibly used: {len(possibly_used)}")

if definitely_unused:
    print(f"\n🗑️  Safe to remove (no references found):")
    for file in definitely_unused[:10]:
        print(f"  - {file}")
    if len(definitely_unused) > 10:
        print(f"  ... and {len(definitely_unused) - 10} more")

print("\n✅ Full results saved to reference_check.json")