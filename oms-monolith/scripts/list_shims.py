#!/usr/bin/env python3
"""
Shim 목록 자동화 스크립트
현재 활성화된 모든 Compatibility Shim을 추적하고 상태를 보고합니다.

사용법: python scripts/list_shims.py [--format=table|json|csv]
"""
import re
import sys
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

class ShimTracker:
    def __init__(self, shim_file: str = "shared/__init__.py"):
        self.shim_file = Path(shim_file)
        self.shims = []
        
    def parse_shims(self) -> List[Dict[str, any]]:
        """Shim 파일을 파싱하여 모든 alias 정보를 추출"""
        if not self.shim_file.exists():
            print(f"Error: {self.shim_file} not found")
            return []
        
        with open(self.shim_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        current_todo = None
        for i, line in enumerate(lines, 1):
            # TODO 주석 찾기
            todo_match = re.search(r'#\s*TODO\(([^)]+)\):\s*(.*)', line)
            if todo_match:
                current_todo = {
                    'id': todo_match.group(1),
                    'description': todo_match.group(2).strip()
                }
            
            # _alias 호출 찾기
            alias_match = re.search(r'_alias\("([^"]+)",\s*"([^"]+)"\)', line)
            if alias_match:
                shim = {
                    'line': i,
                    'real_path': alias_match.group(1),
                    'alias_path': alias_match.group(2),
                    'todo_id': current_todo['id'] if current_todo else None,
                    'description': current_todo['description'] if current_todo else 'No description',
                    'status': 'active'
                }
                self.shims.append(shim)
                # Reset current_todo after use
                current_todo = None
        
        return self.shims
    
    def check_usage(self, shim: Dict[str, any]) -> Tuple[int, List[str]]:
        """특정 shim의 사용 현황을 체크"""
        alias_path = shim['alias_path']
        usage_count = 0
        usage_files = []
        
        # 프로젝트 전체에서 해당 import 검색
        project_root = Path('.').resolve()
        for py_file in project_root.rglob('*.py'):
            if 'venv' in str(py_file) or '__pycache__' in str(py_file):
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # import 패턴 검색
                if f"from {alias_path}" in content or f"import {alias_path}" in content:
                    usage_count += 1
                    usage_files.append(str(py_file.relative_to(project_root)))
                    
            except Exception:
                pass
        
        return usage_count, usage_files[:3]  # 처음 3개만 표시
    
    def generate_report(self, format: str = 'table'):
        """리포트 생성"""
        self.parse_shims()
        
        if format == 'table':
            self._print_table()
        elif format == 'json':
            self._print_json()
        elif format == 'csv':
            self._print_csv()
        else:
            print(f"Unknown format: {format}")
    
    def _print_table(self):
        """테이블 형식으로 출력"""
        print("=" * 100)
        print(f"COMPATIBILITY SHIM STATUS REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 100)
        print(f"{'Line':>6} | {'TODO ID':15} | {'Alias Path':35} | {'Real Path':35} | {'Usage'}")
        print("-" * 100)
        
        total_usage = 0
        for shim in self.shims:
            usage_count, usage_files = self.check_usage(shim)
            total_usage += usage_count
            
            print(f"{shim['line']:>6} | {shim['todo_id'] or 'NO-ID':15} | "
                  f"{shim['alias_path'][:35]:35} | {shim['real_path'][:35]:35} | "
                  f"{usage_count:>3} files")
            
            if usage_files and usage_count > 0:
                for file in usage_files:
                    print(f"{'':>6} | {'':15} | {'└─ ' + file:72}")
        
        print("=" * 100)
        print(f"SUMMARY: {len(self.shims)} shims, {total_usage} total usages")
        print("=" * 100)
        
        # Progress tracking
        print("\nPROGRESS TRACKING:")
        todo_counts = {}
        for shim in self.shims:
            todo_id = shim['todo_id'] or 'NO-ID'
            todo_counts[todo_id] = todo_counts.get(todo_id, 0) + 1
        
        for todo_id, count in sorted(todo_counts.items()):
            print(f"  {todo_id}: {count} shims")
        
        print(f"\n✅ Target: 0 shims = Clean codebase")
        print(f"📊 Current: {len(self.shims)} shims remaining")
        
    def _print_json(self):
        """JSON 형식으로 출력"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_shims': len(self.shims),
            'shims': []
        }
        
        for shim in self.shims:
            usage_count, usage_files = self.check_usage(shim)
            shim_data = shim.copy()
            shim_data['usage_count'] = usage_count
            shim_data['usage_files'] = usage_files
            report['shims'].append(shim_data)
        
        print(json.dumps(report, indent=2))
    
    def _print_csv(self):
        """CSV 형식으로 출력"""
        writer = csv.writer(sys.stdout)
        writer.writerow(['Line', 'TODO_ID', 'Alias_Path', 'Real_Path', 'Usage_Count', 'Description'])
        
        for shim in self.shims:
            usage_count, _ = self.check_usage(shim)
            writer.writerow([
                shim['line'],
                shim['todo_id'] or 'NO-ID',
                shim['alias_path'],
                shim['real_path'],
                usage_count,
                shim['description']
            ])

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Track and report Compatibility Shims')
    parser.add_argument('--format', choices=['table', 'json', 'csv'], 
                       default='table', help='Output format')
    parser.add_argument('--file', default='shared/__init__.py',
                       help='Shim file path')
    
    args = parser.parse_args()
    
    tracker = ShimTracker(args.file)
    tracker.generate_report(args.format)

if __name__ == '__main__':
    main()