#!/usr/bin/env python3
"""
Update .model_dump() calls to .model_dump() for Pydantic V2
"""
import os
import re
from pathlib import Path
from typing import List

def find_files_with_dict_method(directory: str = ".") -> List[Path]:
    """Find all Python files containing '.model_dump()'"""
    files = []
    for root, dirs, filenames in os.walk(directory):
        # Skip virtual environments and cache directories
        dirs[:] = [d for d in dirs if d not in ['venv', '.venv', '__pycache__', '.git', 'archive_*']]
        
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = Path(root) / filename
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if '.model_dump()' in content:
                            files.append(filepath)
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    return files


def update_dict_to_model_dump(filepath: Path) -> bool:
    """Update .model_dump() to .model_dump() in a file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Replace .model_dump() with .model_dump()
        # This pattern matches .model_dump() but not dict() constructor
        content = re.sub(r'\.dict\(\)', '.model_dump()', content)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
    
    except Exception as e:
        print(f"Error updating {filepath}: {e}")
        return False


def main():
    """Main function"""
    print("Updating .model_dump() to .model_dump()...")
    
    # Find all files with .model_dump()
    files = find_files_with_dict_method('.')
    # Filter out archive directories
    files = [f for f in files if not any(part.startswith('archive_') for part in f.parts)]
    
    print(f"Found {len(files)} files with .model_dump() (excluding archives)")
    
    # Update each file
    updated = 0
    for filepath in files:
        print(f"Processing {filepath}...")
        if update_dict_to_model_dump(filepath):
            print(f"  ✓ Updated {filepath}")
            updated += 1
        else:
            print(f"  - No changes needed for {filepath}")
    
    print(f"\nUpdate complete! Updated {updated} files.")


if __name__ == "__main__":
    main()