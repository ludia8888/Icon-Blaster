#!/usr/bin/env python3
"""
Migrate Pydantic V1 Config classes to V2 ConfigDict
"""
import os
import re
from pathlib import Path
from typing import List, Tuple

def find_files_with_config_class(directory: str = ".") -> List[Path]:
    """Find all Python files containing 'class Config:'"""
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
                        if 'class Config:' in content and 'from pydantic' in content:
                            files.append(filepath)
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    return files


def extract_config_class(content: str) -> List[Tuple[str, str]]:
    """Extract Config class content from file"""
    config_blocks = []
    
    # Find all class Config: blocks
    pattern = r'(\s*)class Config:\s*\n((?:\1\s+.*\n)*)'
    matches = re.finditer(pattern, content)
    
    for match in matches:
        indent = match.group(1)
        config_content = match.group(2)
        config_blocks.append((match.group(0), indent, config_content))
    
    return config_blocks


def convert_config_to_configdict(indent: str, config_content: str) -> str:
    """Convert Config class content to ConfigDict"""
    # Parse config attributes
    attributes = {}
    
    # Common patterns
    patterns = {
        'use_enum_values': r'use_enum_values\s*=\s*(True|False)',
        'arbitrary_types_allowed': r'arbitrary_types_allowed\s*=\s*(True|False)',
        'validate_assignment': r'validate_assignment\s*=\s*(True|False)',
        'populate_by_name': r'allow_population_by_field_name\s*=\s*(True|False)',
        'json_encoders': r'json_encoders\s*=\s*({[^}]+})',
        'json_schema_extra': r'schema_extra\s*=\s*({[^}]+})',
        'extra': r'extra\s*=\s*"?(forbid|allow|ignore)"?',
    }
    
    for new_name, pattern in patterns.items():
        match = re.search(pattern, config_content)
        if match:
            value = match.group(1)
            # Handle populate_by_name special case
            if new_name == 'populate_by_name' and value == 'True':
                attributes[new_name] = 'True'
            else:
                attributes[new_name] = value
    
    # Build ConfigDict
    if not attributes:
        return None
    
    config_dict_parts = []
    for key, value in attributes.items():
        config_dict_parts.append(f"{key}={value}")
    
    config_dict = f"{indent}model_config = ConfigDict(\n"
    for i, part in enumerate(config_dict_parts):
        config_dict += f"{indent}    {part}"
        if i < len(config_dict_parts) - 1:
            config_dict += ","
        config_dict += "\n"
    config_dict += f"{indent})\n"
    
    return config_dict


def migrate_file(filepath: Path) -> bool:
    """Migrate a single file from Pydantic V1 to V2"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Check if ConfigDict is already imported
        if 'ConfigDict' not in content and 'class Config:' in content:
            # Add ConfigDict import
            if 'from pydantic import' in content:
                content = re.sub(
                    r'(from pydantic import .*?)(\n)',
                    lambda m: m.group(1) + (', ConfigDict' if ', ConfigDict' not in m.group(1) else '') + m.group(2),
                    content,
                    count=1
                )
            else:
                # Find where to insert import
                import_match = re.search(r'(import .*\n)', content)
                if import_match:
                    content = content[:import_match.end()] + 'from pydantic import ConfigDict\n' + content[import_match.end():]
        
        # Extract and convert Config classes
        config_blocks = extract_config_class(content)
        
        for config_block, indent, config_content in config_blocks:
            config_dict = convert_config_to_configdict(indent, config_content)
            if config_dict:
                # Replace class Config with model_config
                content = content.replace(config_block, config_dict)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        
        return False
    
    except Exception as e:
        print(f"Error migrating {filepath}: {e}")
        return False


def main():
    """Main migration function"""
    print("Starting Pydantic V2 migration...")
    
    # Find all files with Config classes
    files = find_files_with_config_class('.')
    print(f"Found {len(files)} files with Config classes")
    
    # Migrate each file
    migrated = 0
    for filepath in files:
        print(f"Processing {filepath}...")
        if migrate_file(filepath):
            print(f"  ✓ Migrated {filepath}")
            migrated += 1
        else:
            print(f"  - No changes needed for {filepath}")
    
    print(f"\nMigration complete! Migrated {migrated} files.")


if __name__ == "__main__":
    main()