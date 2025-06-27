#!/usr/bin/env python3
"""
IAMScope Enum 타입 호환성 체크 스크립트
Enum 타입 변경으로 깨질 수 있는 코드 패턴을 찾습니다
"""
import re
import ast
from pathlib import Path
from typing import List, Tuple


class EnumCompatibilityChecker(ast.NodeVisitor):
    """AST visitor to find potential enum compatibility issues"""
    
    def __init__(self, filename: str):
        self.filename = filename
        self.issues = []
        self.current_line = 0
    
    def visit_Compare(self, node):
        """Check for 'in IAMScope' patterns"""
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, ast.In) and isinstance(comparator, ast.Name):
                if comparator.id == 'IAMScope':
                    self.issues.append((
                        node.lineno,
                        "Checking membership in IAMScope class/enum",
                        "This will behave differently between class and enum"
                    ))
        self.generic_visit(node)
    
    def visit_Call(self, node):
        """Check for IAMScope() constructor calls"""
        if isinstance(node.func, ast.Name) and node.func.id == 'IAMScope':
            self.issues.append((
                node.lineno,
                "Direct IAMScope() constructor call",
                "Enum cannot be instantiated like a class"
            ))
        self.generic_visit(node)
    
    def visit_Attribute(self, node):
        """Check for .value access on IAMScope attributes"""
        if isinstance(node.value, ast.Attribute):
            # Check for IAMScope.SOMETHING.value pattern
            if (hasattr(node.value, 'value') and 
                isinstance(node.value.value, ast.Name) and 
                node.value.value.id == 'IAMScope' and
                node.attr == 'value'):
                self.issues.append((
                    node.lineno,
                    "Accessing .value on IAMScope member",
                    "Only works with Enum, not with class attributes"
                ))
        self.generic_visit(node)


def check_file(file_path: Path) -> List[Tuple[str, int, str, str]]:
    """Check a single file for compatibility issues"""
    try:
        content = file_path.read_text()
        tree = ast.parse(content, filename=str(file_path))
        
        checker = EnumCompatibilityChecker(str(file_path))
        checker.visit(tree)
        
        return [(str(file_path), line, issue, suggestion) 
                for line, issue, suggestion in checker.issues]
    except Exception as e:
        return [(str(file_path), 0, f"Parse error: {e}", "Fix syntax errors first")]


def find_pattern_issues(file_path: Path) -> List[Tuple[str, int, str, str]]:
    """Find pattern-based issues using regex"""
    issues = []
    
    patterns = [
        # Check for hasattr on IAMScope
        (r'hasattr\s*\(\s*IAMScope\s*,', 
         "hasattr() check on IAMScope",
         "This works differently for class vs enum"),
        
        # Check for isinstance with IAMScope
        (r'isinstance\s*\([^,]+,\s*IAMScope\s*\)',
         "isinstance() check with IAMScope",
         "IAMScope is not a valid type for isinstance with enum"),
         
        # Check for iteration over IAMScope
        (r'for\s+\w+\s+in\s+IAMScope\s*:',
         "Iterating over IAMScope",
         "Only works with Enum, not with class"),
    ]
    
    try:
        content = file_path.read_text()
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            for pattern, issue, suggestion in patterns:
                if re.search(pattern, line):
                    issues.append((str(file_path), line_num, issue, suggestion))
    except Exception:
        pass
    
    return issues


def main():
    """Run compatibility check"""
    root_dir = Path(__file__).parent.parent
    
    print("🔍 Checking for IAMScope Enum compatibility issues...\n")
    
    all_issues = []
    
    # Find all Python files
    for py_file in root_dir.rglob("*.py"):
        # Skip test files and migrations
        if any(skip in str(py_file) for skip in ['test_', '__pycache__', 'migrations']):
            continue
        
        # AST-based checking
        issues = check_file(py_file)
        all_issues.extend(issues)
        
        # Pattern-based checking
        pattern_issues = find_pattern_issues(py_file)
        all_issues.extend(pattern_issues)
    
    if all_issues:
        print(f"⚠️  Found {len(all_issues)} potential compatibility issues:\n")
        
        for file_path, line, issue, suggestion in sorted(all_issues):
            print(f"📄 {file_path}:{line}")
            print(f"   Issue: {issue}")
            print(f"   Fix: {suggestion}\n")
    else:
        print("✅ No enum compatibility issues found!")
    
    # Check for IAMScope imports
    print("\n📦 Checking IAMScope imports...")
    
    import_issues = []
    for py_file in root_dir.rglob("*.py"):
        try:
            content = py_file.read_text()
            if 'from core.iam.iam_integration import IAMScope' in content:
                import_issues.append(str(py_file))
        except Exception:
            pass
    
    if import_issues:
        print(f"\n⚠️  Files still importing from old location ({len(import_issues)} files):")
        for file in import_issues[:10]:  # Show first 10
            print(f"   - {file}")
        if len(import_issues) > 10:
            print(f"   ... and {len(import_issues) - 10} more")
        
        print("\n💡 Run the migration script to update these imports:")
        print("   python scripts/migrate_to_msa_auth.py")
    else:
        print("\n✅ All imports are using the correct location!")


if __name__ == "__main__":
    main()