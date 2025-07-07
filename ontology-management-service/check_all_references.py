#!/usr/bin/env python3
"""
Check references for ALL potentially unused files
"""
import subprocess
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# Load the analysis results
with open('import_analysis.json', 'r') as f:
    analysis = json.load(f)

# Files to check (excluding some obvious ones)
files_to_check = [
    f for f in analysis['categories'].get('other', [])
    if not f.endswith('__init__.py') and 
    not f.startswith('test_') and
    not f in ['analyze_imports.py', 'trace_imports.py', 'check_references.py', 'check_all_references.py']
]

print(f"🔍 Checking references for {len(files_to_check)} files...")
print("This may take a few minutes...")

def check_file_references(file):
    """Check if a file is referenced anywhere"""
    # Get module name from file path
    module_name = file.replace('/', '.').replace('.py', '')
    base_name = Path(file).stem
    
    # Search patterns
    patterns = [
        f"from {module_name}",
        f"import {module_name}",
        f"'{base_name}'",
        f'"{base_name}"',
    ]
    
    # Special handling for certain file types
    if 'routes' in file or 'endpoints' in file:
        patterns.append(f"/{base_name}")  # URL patterns
        
    found = False
    references = []
    
    for pattern in patterns:
        try:
            result = subprocess.run(
                ['grep', '-r', pattern, '.', 
                 '--include=*.py', 
                 '--include=*.yml', 
                 '--include=*.yaml', 
                 '--include=*.json',
                 '--include=*.sh',
                 '--exclude-dir=venv',
                 '--exclude-dir=__pycache__',
                 '--exclude=check_all_references.py'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.stdout:
                lines = result.stdout.strip().split('\n')
                # Filter out self-references and this script
                external_refs = [
                    line for line in lines 
                    if not line.startswith(f"./{file}:") 
                    and 'check_all_references.py' not in line
                    and line.strip()
                ]
                
                if external_refs:
                    found = True
                    references.extend(external_refs[:2])
                    break  # Found reference, no need to check more patterns
                    
        except subprocess.TimeoutExpired:
            print(f"⏱️  Timeout checking {file}")
        except Exception as e:
            print(f"❌ Error checking {file}: {e}")
    
    return file, found, references

# Use thread pool for faster processing
results = {
    'definitely_unused': [],
    'possibly_used': [],
    'errors': []
}

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(check_file_references, file): file 
               for file in files_to_check}
    
    completed = 0
    for future in as_completed(futures):
        completed += 1
        if completed % 20 == 0:
            print(f"Progress: {completed}/{len(files_to_check)}")
            
        try:
            file, found, references = future.result()
            
            if found:
                results['possibly_used'].append({
                    'file': file,
                    'references': references[:2]
                })
            else:
                results['definitely_unused'].append(file)
                
        except Exception as e:
            results['errors'].append({
                'file': futures[future],
                'error': str(e)
            })

# Sort results
results['definitely_unused'].sort()
results['possibly_used'].sort(key=lambda x: x['file'])

# Categorize unused files
unused_categories = {
    'api_routes': [],
    'database': [],
    'middleware': [],
    'core': [],
    'shared': [],
    'other': []
}

for file in results['definitely_unused']:
    if file.startswith('api/'):
        unused_categories['api_routes'].append(file)
    elif file.startswith('database/'):
        unused_categories['database'].append(file)
    elif file.startswith('middleware/'):
        unused_categories['middleware'].append(file)
    elif file.startswith('core/'):
        unused_categories['core'].append(file)
    elif file.startswith('shared/'):
        unused_categories['shared'].append(file)
    else:
        unused_categories['other'].append(file)

# Save detailed results
final_results = {
    'summary': {
        'total_checked': len(files_to_check),
        'definitely_unused': len(results['definitely_unused']),
        'possibly_used': len(results['possibly_used']),
        'errors': len(results['errors'])
    },
    'unused_by_category': unused_categories,
    'all_unused': results['definitely_unused'],
    'possibly_used': results['possibly_used']
}

with open('unused_files_final.json', 'w') as f:
    json.dump(final_results, f, indent=2)

# Print summary
print(f"\n📊 Final Results:")
print(f"✅ Total files checked: {len(files_to_check)}")
print(f"❌ Definitely unused: {len(results['definitely_unused'])}")
print(f"⚠️  Possibly used: {len(results['possibly_used'])}")
print(f"🚫 Errors: {len(results['errors'])}")

print(f"\n📁 Unused files by category:")
for category, files in unused_categories.items():
    if files:
        print(f"\n{category.upper()} ({len(files)} files):")
        for file in files[:5]:
            print(f"  - {file}")
        if len(files) > 5:
            print(f"  ... and {len(files) - 5} more")

print("\n✅ Full results saved to unused_files_final.json")
print("\n🎯 Recommended actions:")
print("1. Review unused_files_final.json")
print("2. Move definitely_unused files to an archive/ directory")
print("3. Run tests to ensure nothing breaks")
print("4. Delete archive/ after confirming everything works")