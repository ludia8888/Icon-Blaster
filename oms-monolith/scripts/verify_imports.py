#!/usr/bin/env python3
"""
모듈 존재 여부 전수 검사 스크립트
사용: python scripts/verify_imports.py [프로젝트_루트]

모든 Python 파일의 import를 실제로 로딩해보고 실패 목록을 CSV로 출력합니다.
"""

import ast
import importlib
import pathlib
import sys
import csv
from typing import List, Set, Tuple

# 프로젝트 루트 설정
PROJECT_ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path.insert(0, str(PROJECT_ROOT))

def extract_modules(file_path: pathlib.Path) -> Set[Tuple[str, int]]:
    """
    Python 파일에서 import하는 모든 모듈명과 라인 번호를 추출
    
    Returns:
        Set of (module_name, line_number) tuples
    """
    modules = set()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content, filename=str(file_path))
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add((alias.name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                # Skip relative imports to avoid false positives
                if node.level > 0:  # This is a relative import
                    continue
                    
                if node.module:
                    modules.add((node.module, node.lineno))
                    # Skip individual imported names to avoid false positives
                    # 사용자 피드백: "from core.history.models import CommitDetail" 같은 구문을
                    # "core.history.models.CommitDetail" 로 잘못 파싱해 "모듈 없음"으로 표기하는 문제 해결
    except Exception as e:
        print(f"⚠️  Error parsing {file_path}: {e}")
    
    return modules

def check_module_exists(module_name: str) -> bool:
    """
    Check if a module can be imported
    """
    try:
        # Split module and attribute if present
        parts = module_name.split('.')
        
        # Try to import the module
        for i in range(len(parts), 0, -1):
            try:
                mod_path = '.'.join(parts[:i])
                mod = importlib.import_module(mod_path)
                
                # Check if remaining parts are attributes
                for attr in parts[i:]:
                    if not hasattr(mod, attr):
                        return False
                    mod = getattr(mod, attr)
                
                return True
            except:
                continue
                
        return False
    except:
        return False

# Collect missing modules
missing: List[Tuple[str, str, int]] = []  # (module, file, line)
checked_modules = set()  # Cache to avoid duplicate checks

# Exclude patterns
exclude_patterns = [
    'venv/', 
    '__pycache__/', 
    '.git/', 
    'scripts/verify_imports.py',
    'test_',  # Test files might have special imports
    'tests/',
]

# Scan all Python files
py_files = list(PROJECT_ROOT.rglob("*.py"))
total_files = len(py_files)

print(f"🔍 Scanning {total_files} Python files in {PROJECT_ROOT}")
print("="*60)

for idx, py_file in enumerate(py_files, 1):
    # Skip excluded files
    if any(pattern in str(py_file) for pattern in exclude_patterns):
        continue
    
    relative_path = py_file.relative_to(PROJECT_ROOT)
    
    # Progress indicator
    if idx % 10 == 0:
        print(f"Progress: {idx}/{total_files} files...")
    
    # Extract modules from file
    modules = extract_modules(py_file)
    
    for module_name, line_no in modules:
        # Skip already checked modules
        if module_name in checked_modules:
            continue
        
        checked_modules.add(module_name)
        
        # Skip built-in modules
        if module_name in sys.builtin_module_names:
            continue
        
        # Check if module exists
        if not check_module_exists(module_name):
            missing.append((module_name, str(relative_path), line_no))

# Remove duplicates and sort
missing = sorted(set(missing))

# Group by module for better readability
module_files = {}
for module, file, line in missing:
    if module not in module_files:
        module_files[module] = []
    module_files[module].append((file, line))

# Output results
print("\n" + "="*60)
print("📊 IMPORT VERIFICATION RESULTS")
print("="*60)

if not missing:
    print("✅ All imports resolved successfully!")
else:
    print(f"❌ Found {len(module_files)} missing modules:\n")
    
    for module, locations in sorted(module_files.items()):
        print(f"❌ {module}")
        for file, line in locations[:3]:  # Show first 3 occurrences
            print(f"   └─ {file}:{line}")
        if len(locations) > 3:
            print(f"   └─ ... and {len(locations)-3} more locations")
        print()

# Write CSV report
outfile = PROJECT_ROOT / "import_verification_report.csv"
with outfile.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["missing_module", "referenced_in", "line_number"])
    writer.writerows(missing)

print(f"\n📄 Detailed report saved to: {outfile}")

# Summary statistics
print("\n📈 SUMMARY:")
print(f"   Total files scanned: {total_files}")
print(f"   Files with issues: {len(set(m[1] for m in missing))}")
print(f"   Unique missing modules: {len(module_files)}")
print(f"   Total missing imports: {len(missing)}")

# Suggest common fixes
if module_files:
    print("\n💡 COMMON PATTERNS DETECTED:")
    
    services_modules = [m for m in module_files if m.startswith("services.")]
    if services_modules:
        print(f"\n   • {len(services_modules)} 'services.*' imports")
        print("     → These need path remapping in compatibility shim")
    
    shared_modules = [m for m in module_files if m.startswith("shared.") and "shared." in m]
    if shared_modules:
        print(f"\n   • {len(shared_modules)} 'shared.*' imports")
        print("     → Check if real path differs from import path")

sys.exit(0 if not missing else 1)