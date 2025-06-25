#!/usr/bin/env python3
"""
Enhanced Import Verification Tool
더 정확한 import 오류 탐지 및 분류
"""
import os
import sys
import ast
import importlib.util
from pathlib import Path
from typing import Dict, List, Set, Tuple
import re

class ImportAnalyzer:
    def __init__(self, root_path: str = '.'):
        self.root_path = Path(root_path)
        self.missing_imports = []
        self.successful_imports = []
        self.false_positives = []
        
    def is_stdlib_module(self, module_name: str) -> bool:
        """표준 라이브러리 모듈인지 확인"""
        stdlib_modules = {
            'sys', 'os', 'json', 'datetime', 'typing', 'pathlib', 'asyncio',
            'logging', 'uuid', 'hashlib', 'base64', 'time', 'random',
            'functools', 'itertools', 'collections', 'dataclasses',
            'abc', 'contextlib', 'enum', 'io', 'math', 're', 'string',
            'urllib', 'http', 'email', 'xml', 'html', 'warnings'
        }
        return module_name.split('.')[0] in stdlib_modules
    
    def is_external_library(self, module_name: str) -> bool:
        """외부 라이브러리인지 확인"""
        external_libs = {
            'fastapi', 'uvicorn', 'pydantic', 'redis', 'motor', 'terminusdb_client',
            'nats', 'httpx', 'graphene', 'websockets', 'strawberry', 'pytest',
            'prometheus_client', 'opentelemetry', 'aiofiles', 'aiocache',
            'tenacity', 'structlog', 'sentry_sdk', 'celery', 'flower',
            'alembic', 'sqlalchemy', 'apscheduler', 'croniter', 'jsonschema',
            'orjson', 'minio', 'passlib', 'pyotp', 'boto3', 'grpcio',
            'protobuf', 'slowapi', 'pyyaml', 'pandas', 'numpy', 'scipy'
        }
        return module_name.split('.')[0] in external_libs
    
    def extract_imports_from_file(self, file_path: Path) -> List[Tuple[str, int]]:
        """파일에서 import 구문 추출"""
        imports = []
        try:
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content, filename=str(file_path))
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append((alias.name, node.lineno))
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        module_parts = []
                        if node.level > 0:  # Relative import
                            module_parts.append('.' * node.level)
                        module_parts.append(node.module)
                        module_name = ''.join(module_parts)
                        imports.append((module_name, node.lineno))
                        
                        # Also check individual imported names
                        for alias in node.names:
                            full_name = f"{node.module}.{alias.name}"
                            imports.append((full_name, node.lineno))
                            
        except Exception as e:
            print(f"Error parsing {file_path}: {e}")
            
        return imports
    
    def test_import(self, module_name: str, file_path: Path) -> bool:
        """실제 import 테스트"""
        if self.is_stdlib_module(module_name):
            return True
            
        if self.is_external_library(module_name):
            try:
                __import__(module_name.split('.')[0])
                return True
            except ImportError:
                return False
        
        # 프로젝트 내부 모듈 테스트
        try:
            # Python path 설정
            original_path = sys.path.copy()
            sys.path.insert(0, str(self.root_path))
            
            # Relative import 처리
            if module_name.startswith('.'):
                # 상대 경로를 절대 경로로 변환
                relative_parts = module_name.split('.')
                level = len([p for p in relative_parts if p == ''])
                module_parts = [p for p in relative_parts if p != '']
                
                # 파일의 패키지 경로 계산
                file_package = str(file_path.parent.relative_to(self.root_path)).replace('/', '.')
                if file_package == '.':
                    file_package = ''
                
                package_parts = file_package.split('.') if file_package else []
                if level > len(package_parts):
                    return False
                    
                base_package_parts = package_parts[:-level+1] if level > 1 else package_parts
                absolute_module = '.'.join(base_package_parts + module_parts)
                module_name = absolute_module
            
            # Import 시도
            __import__(module_name)
            return True
            
        except ImportError:
            return False
        except Exception:
            return False
        finally:
            sys.path = original_path
    
    def analyze_project(self) -> Dict[str, List]:
        """전체 프로젝트 분석"""
        py_files = list(self.root_path.glob('**/*.py'))
        
        # 제외할 경로
        exclude_patterns = [
            '__pycache__', '.git', 'venv', '.venv',
            'node_modules', '.pytest_cache', 'build', 'dist'
        ]
        
        py_files = [
            f for f in py_files 
            if not any(pattern in str(f) for pattern in exclude_patterns)
        ]
        
        print(f"Analyzing {len(py_files)} Python files...")
        
        all_imports = set()
        file_import_map = {}
        
        for py_file in py_files:
            imports = self.extract_imports_from_file(py_file)
            file_import_map[py_file] = imports
            for import_name, _ in imports:
                all_imports.add(import_name)
        
        print(f"Found {len(all_imports)} unique imports")
        
        # Import 테스트
        for import_name in sorted(all_imports):
            # 각 import가 사용된 파일들 찾기
            using_files = [
                (f, line) for f, imports in file_import_map.items() 
                for imp, line in imports if imp == import_name
            ]
            
            if not using_files:
                continue
                
            # 첫 번째 파일을 기준으로 테스트
            test_file = using_files[0][0]
            
            if self.test_import(import_name, test_file):
                self.successful_imports.append({
                    'module': import_name,
                    'files': using_files,
                    'status': 'success'
                })
            else:
                # 실패한 경우 카테고리 분류
                category = self.categorize_failed_import(import_name)
                self.missing_imports.append({
                    'module': import_name,
                    'files': using_files,
                    'category': category,
                    'status': 'failed'
                })
        
        return {
            'successful': self.successful_imports,
            'missing': self.missing_imports,
            'false_positives': self.false_positives
        }
    
    def categorize_failed_import(self, module_name: str) -> str:
        """실패한 import 분류"""
        if self.is_external_library(module_name):
            return 'external_missing'
        elif module_name.startswith('.'):
            return 'relative_import_issue'
        elif any(pattern in module_name for pattern in ['__pycache__', '.pyc']):
            return 'false_positive'
        elif module_name.count('.') > 3:
            return 'deep_module_path'
        else:
            return 'internal_missing'
    
    def generate_report(self, results: Dict) -> str:
        """결과 리포트 생성"""
        report = []
        report.append("=" * 60)
        report.append("Enhanced Import Analysis Report")
        report.append("=" * 60)
        
        successful = results['successful']
        missing = results['missing']
        
        report.append(f"\n📊 Summary:")
        report.append(f"  ✅ Successful imports: {len(successful)}")
        report.append(f"  ❌ Missing imports: {len(missing)}")
        
        # 카테고리별 분류
        categories = {}
        for item in missing:
            cat = item['category']
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)
        
        report.append(f"\n📋 Missing imports by category:")
        for category, items in categories.items():
            report.append(f"  {category}: {len(items)} items")
        
        # 상세 리스트
        report.append(f"\n❌ Missing Imports Detail:")
        for category, items in categories.items():
            if not items:
                continue
                
            report.append(f"\n  {category.upper()}:")
            for item in items[:10]:  # 상위 10개만
                files_str = ', '.join([
                    f"{f.name}:{line}" for f, line in item['files'][:3]
                ])
                report.append(f"    - {item['module']} (used in: {files_str})")
            
            if len(items) > 10:
                report.append(f"    ... and {len(items) - 10} more")
        
        return '\n'.join(report)

def main():
    analyzer = ImportAnalyzer()
    results = analyzer.analyze_project()
    report = analyzer.generate_report(results)
    
    print(report)
    
    # CSV 리포트 생성
    csv_path = "enhanced_import_report.csv"
    with open(csv_path, 'w') as f:
        f.write("module,status,category,file,line\n")
        
        for item in results['missing']:
            for file_path, line in item['files']:
                f.write(f"{item['module']},failed,{item['category']},{file_path},{line}\n")
        
        for item in results['successful']:
            for file_path, line in item['files']:
                f.write(f"{item['module']},success,working,{file_path},{line}\n")
    
    print(f"\n📄 Detailed report saved to: {csv_path}")

if __name__ == "__main__":
    main()