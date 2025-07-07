#!/usr/bin/env python3
"""
Update @validator decorators to @field_validator for Pydantic V2
"""
import os
import re
from pathlib import Path
from typing import List

def find_files_with_validator(directory: str = ".") -> List[Path]:
    """Find all Python files containing '@validator'"""
    files = []
    for root, dirs, filenames in os.walk(directory):
        # Skip virtual environments and cache directories
        dirs[:] = [d for d in dirs if d not in ['venv', '.venv', '__pycache__', '.git']]
        
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = Path(root) / filename
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if '@validator' in content and 'from pydantic' in content:
                            files.append(filepath)
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    return files


def update_validators_in_file(filepath: Path) -> bool:
    """Update validators in a single file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Update import
        if 'validator' in content and 'field_validator' not in content:
            # Update from pydantic import
            content = re.sub(
                r'from pydantic import (.*?)validator(.*?)(?=\n)',
                lambda m: f'from pydantic import {m.group(1)}field_validator{m.group(2)}',
                content
            )
        
        # Find and update @validator decorators
        # Pattern to match @validator with optional parameters
        pattern = r'@validator\((.*?)\)\s*\n(\s*)def\s+(\w+)\s*\(cls,'
        
        def replace_validator(match):
            params = match.group(1)
            indent = match.group(2)
            method_name = match.group(3)
            
            # Build the replacement
            result = f'@field_validator({params})\n{indent}@classmethod\n{indent}def {method_name}(cls,'
            return result
        
        content = re.sub(pattern, replace_validator, content)
        
        # Also handle @validator without parentheses
        pattern2 = r'@validator\s*\n(\s*)def\s+(\w+)\s*\(cls,'
        
        def replace_validator2(match):
            indent = match.group(1)
            method_name = match.group(2)
            result = f'@field_validator\n{indent}@classmethod\n{indent}def {method_name}(cls,'
            return result
        
        content = re.sub(pattern2, replace_validator2, content)
        
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
    print("Updating @validator to @field_validator...")
    
    # Find all files with @validator
    files = find_files_with_validator('.')
    print(f"Found {len(files)} files with @validator")
    
    # Update each file
    updated = 0
    for filepath in files:
        print(f"Processing {filepath}...")
        if update_validators_in_file(filepath):
            print(f"  ✓ Updated {filepath}")
            updated += 1
        else:
            print(f"  - No changes needed for {filepath}")
    
    print(f"\nUpdate complete! Updated {updated} files.")


if __name__ == "__main__":
    main()