#!/usr/bin/env python3
"""
OMS Import Fixer Script
모든 잘못된 import 경로를 일괄 수정
"""
import os
import re
from pathlib import Path
import argparse
from typing import Dict, List, Tuple

# Import 매핑 규칙
IMPORT_MAPPINGS = {
    # services.* → core.*
    r'from services\.validation_service\.core\.': r'from core.validation.',
    r'from services\.branch_service\.core\.': r'from core.branch.',
    r'from services\.schema_service\.core\.': r'from core.schema.',
    r'from services\.(\w+)_service\.core\.': r'from core.\1.',
    
    # shared.models.* → models.*
    r'from shared\.models\.': r'from models.',
    
    # shared.clients.* → database.clients.*
    r'from shared\.clients\.': r'from database.clients.',
    
    # shared.cache.* → 임시 처리 (나중에 stub으로)
    r'from shared\.cache\.smart_cache import SmartCacheManager': 
        r'from shared.cache.smart_cache import SmartCacheManager',
    
    # shared.events → 임시 처리
    r'from shared\.events import EventPublisher': 
        r'from shared.events import EventPublisher',
    
    # shared.database.* → shared.database.*
    r'from shared\.database\.': r'from shared.database.',
    
    # shared.observability → shared.observability
    r'from shared\.observability': r'from shared.observability',
    
    # shared.security.* → shared.security.*
    r'from shared\.security\.': r'from shared.security.',
    
    # shared.utils → shared.utils
    r'from shared\.utils': r'from shared.utils',
}

class ImportFixer:
    def __init__(self, root_path: str = '.'):
        self.root_path = Path(root_path)
        self.fixed_files = []
        self.errors = []
        
    def fix_file(self, file_path: Path) -> Tuple[bool, List[str]]:
        """단일 파일의 import 수정"""
        try:
            content = file_path.read_text(encoding='utf-8')
            original_content = content
            changes = []
            
            for pattern, replacement in IMPORT_MAPPINGS.items():
                matches = re.finditer(pattern, content)
                for match in matches:
                    old_import = match.group(0)
                    new_import = re.sub(pattern, replacement, old_import)
                    changes.append(f"  {old_import} → {new_import}")
                
                content = re.sub(pattern, replacement, content)
            
            if content != original_content:
                file_path.write_text(content, encoding='utf-8')
                return True, changes
            
            return False, []
            
        except Exception as e:
            self.errors.append(f"Error in {file_path}: {str(e)}")
            return False, []
    
    def fix_all_imports(self, dry_run: bool = False) -> Dict[str, int]:
        """모든 Python 파일의 import 수정"""
        stats = {
            'total_files': 0,
            'fixed_files': 0,
            'total_changes': 0,
            'errors': 0
        }
        
        # 모든 Python 파일 찾기
        py_files = list(self.root_path.glob('**/*.py'))
        
        # 제외할 경로
        exclude_patterns = ['venv/', '__pycache__/', '.git/', 'scripts/fix_imports.py']
        py_files = [f for f in py_files if not any(ex in str(f) for ex in exclude_patterns)]
        
        stats['total_files'] = len(py_files)
        
        print(f"Found {len(py_files)} Python files to check...")
        
        for py_file in py_files:
            if dry_run:
                # Dry run 모드: 실제로 수정하지 않고 변경사항만 확인
                content = py_file.read_text(encoding='utf-8')
                original_content = content
                changes = []
                
                for pattern, replacement in IMPORT_MAPPINGS.items():
                    matches = list(re.finditer(pattern, content))
                    for match in matches:
                        old_import = match.group(0)
                        new_import = re.sub(pattern, replacement, old_import)
                        changes.append(f"  {old_import} → {new_import}")
                    content = re.sub(pattern, replacement, content)
                
                if content != original_content:
                    print(f"\n📝 {py_file.relative_to(self.root_path)}:")
                    for change in changes:
                        print(change)
                    stats['fixed_files'] += 1
                    stats['total_changes'] += len(changes)
            else:
                # 실제 수정 모드
                fixed, changes = self.fix_file(py_file)
                if fixed:
                    print(f"\n✅ Fixed {py_file.relative_to(self.root_path)}:")
                    for change in changes:
                        print(change)
                    self.fixed_files.append(py_file)
                    stats['fixed_files'] += 1
                    stats['total_changes'] += len(changes)
        
        stats['errors'] = len(self.errors)
        
        return stats
    
    def report(self, stats: Dict[str, int], dry_run: bool = False):
        """수정 결과 리포트"""
        print("\n" + "="*60)
        print(f"Import Fix {'Preview' if dry_run else 'Complete'}!")
        print("="*60)
        print(f"Total files scanned: {stats['total_files']}")
        print(f"Files {'to be fixed' if dry_run else 'fixed'}: {stats['fixed_files']}")
        print(f"Total import changes: {stats['total_changes']}")
        
        if stats['errors'] > 0:
            print(f"\n❌ Errors encountered: {stats['errors']}")
            for error in self.errors:
                print(f"  - {error}")
        
        if not dry_run and stats['fixed_files'] > 0:
            print(f"\n✨ Successfully fixed {stats['fixed_files']} files!")

def main():
    parser = argparse.ArgumentParser(description='Fix OMS import statements')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Preview changes without modifying files')
    parser.add_argument('--path', default='.', 
                       help='Root path to search for Python files')
    
    args = parser.parse_args()
    
    fixer = ImportFixer(args.path)
    
    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no files will be modified")
    else:
        print("🚀 Running in FIX mode - files will be modified")
        response = input("Are you sure you want to continue? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            return
    
    stats = fixer.fix_all_imports(dry_run=args.dry_run)
    fixer.report(stats, dry_run=args.dry_run)

if __name__ == '__main__':
    main()