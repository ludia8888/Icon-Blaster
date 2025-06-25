#!/usr/bin/env python3
"""
Shim 문서 자동 생성 스크립트
특정 shim에 대한 마이그레이션 문서를 템플릿에서 자동 생성합니다.

사용법: python scripts/generate_shim_doc.py --id OMS-SHIM-003 --real "core.auth" --alias "shared.auth"
"""
import argparse
import re
from datetime import datetime, timedelta
from pathlib import Path
import subprocess

def find_shim_in_file(shim_file: Path, real_path: str, alias_path: str):
    """Find the shim line number and context"""
    with open(shim_file, 'r') as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        if f'_alias("{real_path}"' in line and f'"{alias_path}")' in line:
            # Look for TODO in previous lines
            todo_info = None
            for j in range(max(0, i-3), i):
                if 'TODO' in lines[j]:
                    todo_match = re.search(r'TODO\(([^)]+)\):\s*(.*)', lines[j])
                    if todo_match:
                        todo_info = {
                            'id': todo_match.group(1),
                            'desc': todo_match.group(2).strip()
                        }
                    break
            
            return {
                'line_number': i,
                'line_content': line.strip(),
                'todo': todo_info
            }
    return None

def find_usages(alias_path: str):
    """Find all files using this import"""
    try:
        result = subprocess.run(
            ['grep', '-r', f'from {alias_path}', '.', '--include=*.py'],
            capture_output=True,
            text=True
        )
        
        usages = []
        for line in result.stdout.strip().split('\n'):
            if line and 'venv' not in line and '__pycache__' not in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    file_path = parts[0].replace('./', '')
                    # Find line number
                    with open(file_path, 'r') as f:
                        for i, file_line in enumerate(f, 1):
                            if f'from {alias_path}' in file_line:
                                usages.append(f"{file_path}:{i}")
                                break
        
        return usages[:5]  # Return first 5 usages
    except:
        return []

def generate_shim_doc(shim_id: str, real_path: str, alias_path: str, 
                     type_: str = "Path Migration", priority: str = "Medium"):
    """Generate shim documentation from template"""
    
    template_path = Path('shims/SHIM_TEMPLATE.md')
    if not template_path.exists():
        print(f"Error: Template not found at {template_path}")
        return
    
    # Find shim details
    shim_info = find_shim_in_file(Path('shared/__init__.py'), real_path, alias_path)
    if not shim_info:
        print(f"Warning: Shim not found in shared/__init__.py")
        line_number = "XXX"
        line_content = f'_alias("{real_path}", "{alias_path}")'
    else:
        line_number = shim_info['line_number']
        line_content = shim_info['line_content']
    
    # Find usages
    usages = find_usages(alias_path)
    
    # Load template
    with open(template_path, 'r') as f:
        template = f.read()
    
    # Calculate dates
    today = datetime.now()
    target_date = today + timedelta(days=3)  # Default 3 days for completion
    
    # Replacements
    replacements = {
        'OMS-SHIM-XXX': shim_id,
        '[Brief Description]': f"{alias_path} → {real_path}",
        '[Path Migration|Namespace Restructuring|Module Integration]': type_,
        '[High|Medium|Low]': priority,
        '🔴 Pending | 🟡 In Progress | ✅ Complete': '🔴 Pending',
        'YYYY-MM-DD': today.strftime('%Y-%m-%d'),
        'Target Completion: YYYY-MM-DD': f"Target Completion: {target_date.strftime('%Y-%m-%d')}",
        'LINE_NUMBER': str(line_number),
        '"actual.path"': f'"{real_path}"',
        '"expected.import.path"': f'"{alias_path}"',
        'expected.import.path': alias_path,
        'actual.path': real_path,
        '# shared/__init__.py:LINE_NUMBER': f'# shared/__init__.py:{line_number}',
        '_alias("actual.path", "expected.import.path")': line_content,
        '[What import is expected]': f"Code expects to import from `{alias_path}`",
        '[Where the actual file is located]': f"Actual module is at `{real_path}`",
        '[Why this causes confusion]': "Import path doesn't match actual file location",
        '`path/to/file1.py:LINE`': '\n'.join(f"- `{usage}`" for usage in usages) if usages else '- No usages found',
        'new/directory/structure': '/'.join(alias_path.split('.')[:-1]),
        'old/file.py': f"{real_path.replace('.', '/')}.py",
        'new/directory/': f"{alias_path.replace('.', '/')}",
        'from expected.import.path import Something': f"from {alias_path} import [ClassName]",
        'from new.correct.path import Something': f"from {alias_path} import [ClassName]",
    }
    
    # Apply replacements
    content = template
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    # Write output
    output_path = Path(f'shims/{shim_id}.md')
    with open(output_path, 'w') as f:
        f.write(content)
    
    print(f"✅ Generated shim documentation: {output_path}")
    print(f"📝 Found {len(usages)} usage(s) of {alias_path}")
    if usages:
        print("   First few usages:")
        for usage in usages[:3]:
            print(f"   - {usage}")

def main():
    parser = argparse.ArgumentParser(
        description='Generate shim migration documentation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/generate_shim_doc.py --id OMS-SHIM-003 --real "api.gateway.auth" --alias "shared.auth"
  python scripts/generate_shim_doc.py --id OMS-SHIM-004 --real "core.event_publisher.models" --alias "services.event_publisher.core.models" --type "Namespace Restructuring" --priority High
        """
    )
    
    parser.add_argument('--id', required=True, help='Shim ID (e.g., OMS-SHIM-003)')
    parser.add_argument('--real', required=True, help='Real module path')
    parser.add_argument('--alias', required=True, help='Alias (expected) path')
    parser.add_argument('--type', default='Path Migration', 
                       choices=['Path Migration', 'Namespace Restructuring', 'Module Integration'],
                       help='Type of shim')
    parser.add_argument('--priority', default='Medium',
                       choices=['High', 'Medium', 'Low'],
                       help='Priority level')
    
    args = parser.parse_args()
    
    generate_shim_doc(
        shim_id=args.id,
        real_path=args.real,
        alias_path=args.alias,
        type_=args.type,
        priority=args.priority
    )

if __name__ == '__main__':
    main()