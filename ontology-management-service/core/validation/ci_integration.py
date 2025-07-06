#!/usr/bin/env python3
"""
CI/CD Integration Tool for Naming Convention Validation
명명 규칙 검증을 CI/CD 파이프라인에 통합
"""
import argparse
import json
import sys
import os
import re
import ast
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
import xml.etree.ElementTree as ET
import subprocess

from core.validation.naming_convention import (
    EntityType, NamingConventionEngine, get_naming_engine
)
from core.validation.naming_config import get_naming_config_service


class TextFormatter:
    """텍스트 출력 포맷터"""
    
    def format(self, results: List[Dict]) -> str:
        """텍스트 형식으로 포맷"""
        lines = ["=== Naming Convention Validation Report ===\n"]
        
        # 파일별로 그룹화
        by_file = {}
        for result in results:
            file_path = result.get("file", "unknown")
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(result)
        
        total_issues = 0
        for file_path, file_results in by_file.items():
            issues = [r for r in file_results if not r.get("valid", True)]
            if issues:
                lines.append(f"\n📄 {file_path}")
                for result in issues:
                    total_issues += 1
                    lines.append(f"  ❌ Line {result['line']}: {result['entity_type']} '{result['entity_name']}'")
                    
                    for issue in result.get("issues", []):
                        lines.append(f"     - {issue['message']}")
                        if issue.get("suggestion"):
                            lines.append(f"       💡 Suggestion: {issue['suggestion']}")
        
        if total_issues == 0:
            lines.append("\n✅ All naming conventions passed!")
        else:
            lines.append(f"\n\n❌ Total issues found: {total_issues}")
        
        return "\n".join(lines)


class JSONFormatter:
    """JSON 출력 포맷터"""
    
    def format(self, results: List[Dict]) -> str:
        """JSON 형식으로 포맷"""
        summary = {
            "total_entities": len(results),
            "valid": sum(1 for r in results if r.get("valid", True)),
            "invalid": sum(1 for r in results if not r.get("valid", True)),
            "timestamp": datetime.now().isoformat()
        }
        
        output = {
            "summary": summary,
            "results": results
        }
        
        return json.dumps(output, indent=2)


class JUnitFormatter:
    """JUnit XML 출력 포맷터"""
    
    def format(self, results: List[Dict]) -> str:
        """JUnit XML 형식으로 포맷"""
        root = ET.Element("testsuites")
        testsuite = ET.SubElement(root, "testsuite")
        
        testsuite.set("name", "NamingConvention")
        testsuite.set("tests", str(len(results)))
        testsuite.set("failures", str(sum(1 for r in results if not r.get("valid", True))))
        testsuite.set("timestamp", datetime.now().isoformat())
        
        for result in results:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", f"{result['entity_type']}.{result['entity_name']}")
            testcase.set("classname", result["file"])
            
            if not result.get("valid", True):
                failure = ET.SubElement(testcase, "failure")
                issues = result.get("issues", [])
                if issues:
                    failure.set("type", issues[0]["rule"])
                    failure.set("message", issues[0]["message"])
                    failure.text = "\n".join(f"{i['rule']}: {i['message']}" for i in issues)
        
        return ET.tostring(root, encoding="unicode")


class GitHubFormatter:
    """GitHub Actions 출력 포맷터"""
    
    def format(self, results: List[Dict]) -> str:
        """GitHub Actions 형식으로 포맷"""
        lines = []
        
        for result in results:
            if not result.get("valid", True):
                file_path = result["file"]
                line = result.get("line", 1)
                
                for issue in result.get("issues", []):
                    severity = "error" if issue["severity"] == "error" else "warning"
                    message = issue["message"]
                    
                    # GitHub Actions annotation format
                    lines.append(f"::{severity} file={file_path},line={line}::{message}")
                    
                    if issue.get("suggestion"):
                        lines.append(f"::notice file={file_path},line={line}::💡 Suggestion: {issue['suggestion']}")
        
        return "\n".join(lines)


class CINamingValidator:
    """CI/CD 명명 규칙 검증기"""
    
    # 엔티티 타입 매핑
    ENTITY_PATTERNS = {
        EntityType.OBJECT_TYPE: [
            r'class\s+(\w+).*:',  # Python class
            r'interface\s+(\w+)',  # TypeScript interface
            r'type\s+(\w+)\s*=',  # TypeScript type alias
        ],
        EntityType.PROPERTY: [
            r'self\.(\w+)\s*=',  # Python instance property
            r'(\w+):\s*[\w\[\]\|]+',  # TypeScript property
            r'const\s+(\w+)\s*=',  # const declaration
            r'let\s+(\w+)\s*=',  # let declaration
            r'var\s+(\w+)\s*=',  # var declaration
        ],
        EntityType.FUNCTION_TYPE: [
            r'def\s+(\w+)\s*\(',  # Python function
            r'async\s+def\s+(\w+)\s*\(',  # Python async function
            r'function\s+(\w+)\s*\(',  # JavaScript function
            r'const\s+(\w+)\s*=\s*\([^)]*\)\s*=>',  # Arrow function
        ],
        EntityType.INTERFACE: [
            r'interface\s+(\w+)',  # TypeScript/Java interface
            r'protocol\s+(\w+)',  # Python protocol
        ]
    }
    
    def __init__(self, convention_id: str = "default"):
        """
        초기화
        
        Args:
            convention_id: 사용할 명명 규칙 ID
        """
        config_service = get_naming_config_service()
        convention = config_service.get_convention(convention_id)
        if not convention:
            raise ValueError(f"Convention '{convention_id}' not found")
        
        self.engine = NamingConventionEngine(convention)
        self.convention_id = convention_id
    
    def validate_file(self, file_path: Path) -> List[Dict]:
        """
        파일 내 엔티티 검증
        
        Args:
            file_path: 검증할 파일 경로
            
        Returns:
            검증 결과 목록
        """
        results = []
        
        if not file_path.exists() or not file_path.is_file():
            return results
        
        try:
            content = file_path.read_text(encoding='utf-8')
            lines = content.splitlines()
            
            # 파일 확장자에 따른 처리
            if file_path.suffix in ['.py', '.pyi']:
                results.extend(self._validate_python_file(file_path, content, lines))
            elif file_path.suffix in ['.ts', '.tsx', '.js', '.jsx']:
                results.extend(self._validate_typescript_file(file_path, content, lines))
            elif file_path.suffix in ['.java']:
                results.extend(self._validate_java_file(file_path, content, lines))
                
        except Exception as e:
            results.append({
                "file": str(file_path),
                "error": f"Failed to parse file: {e}",
                "valid": False
            })
        
        return results
    
    def _validate_python_file(self, file_path: Path, content: str, lines: List[str]) -> List[Dict]:
        """Python 파일 검증"""
        results = []
        
        # AST를 사용한 정확한 파싱
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # 클래스 이름 검증
                    result = self._validate_entity(
                        file_path, EntityType.OBJECT_TYPE, node.name,
                        node.lineno, node.col_offset
                    )
                    results.append(result)
                    
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    # 함수 이름 검증
                    if not self._is_method(node):
                        result = self._validate_entity(
                            file_path, EntityType.FUNCTION_TYPE, node.name,
                            node.lineno, node.col_offset
                        )
                        results.append(result)
                        
                elif isinstance(node, ast.Assign):
                    # 변수/속성 할당 검증
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            result = self._validate_entity(
                                file_path, EntityType.PROPERTY, target.id,
                                target.lineno, target.col_offset
                            )
                            results.append(result)
                            
        except SyntaxError as e:
            # 구문 오류가 있어도 정규식으로 fallback
            results.extend(self._validate_with_regex(file_path, content, lines))
        
        return results
    
    def _validate_typescript_file(self, file_path: Path, content: str, lines: List[str]) -> List[Dict]:
        """TypeScript/JavaScript 파일 검증"""
        # TypeScript는 AST 파싱이 복잡하므로 정규식 사용
        return self._validate_with_regex(file_path, content, lines)
    
    def _validate_java_file(self, file_path: Path, content: str, lines: List[str]) -> List[Dict]:
        """Java 파일 검증"""
        return self._validate_with_regex(file_path, content, lines)
    
    def _validate_with_regex(self, file_path: Path, content: str, lines: List[str]) -> List[Dict]:
        """정규식 기반 검증"""
        results = []
        
        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                regex = re.compile(pattern, re.MULTILINE)
                
                for match in regex.finditer(content):
                    entity_name = match.group(1)
                    line_no = content[:match.start()].count('\n') + 1
                    col_offset = match.start() - content.rfind('\n', 0, match.start()) - 1
                    
                    result = self._validate_entity(
                        file_path, entity_type, entity_name,
                        line_no, col_offset
                    )
                    results.append(result)
        
        return results
    
    def _validate_entity(self, file_path: Path, entity_type: EntityType, 
                        entity_name: str, line: int, column: int) -> Dict:
        """개별 엔티티 검증"""
        validation_result = self.engine.validate(entity_type, entity_name)
        
        result = {
            "file": str(file_path),
            "entity_type": entity_type.value,
            "entity_name": entity_name,
            "line": line,
            "column": column,
            "valid": validation_result.is_valid
        }
        
        if not validation_result.is_valid:
            result["issues"] = [
                {
                    "rule": issue.rule_violated,
                    "severity": issue.severity,
                    "message": issue.message,
                    "suggestion": issue.suggestion
                }
                for issue in validation_result.issues
            ]
            
            if validation_result.suggestions:
                result["suggestions"] = validation_result.suggestions
        
        return result
    
    def _is_method(self, node: ast.FunctionDef) -> bool:
        """메소드인지 확인 (클래스 내부 함수)"""
        # 부모 노드 확인은 복잡하므로 간단히 self 파라미터로 판단
        if node.args.args and len(node.args.args) > 0:
            first_arg = node.args.args[0]
            if hasattr(first_arg, 'arg') and first_arg.arg == 'self':
                return True
        return False
    
    def validate_directory(self, directory: Path, 
                          include_patterns: Optional[List[str]] = None,
                          exclude_patterns: Optional[List[str]] = None) -> List[Dict]:
        """
        디렉토리 내 모든 파일 검증
        
        Args:
            directory: 검증할 디렉토리
            include_patterns: 포함할 파일 패턴
            exclude_patterns: 제외할 파일 패턴
            
        Returns:
            검증 결과 목록
        """
        results = []
        
        # 기본 패턴
        if not include_patterns:
            include_patterns = ["*.py", "*.pyi", "*.js", "*.jsx", "*.ts", "*.tsx", "*.java"]
        
        if not exclude_patterns:
            exclude_patterns = [
                "*test*", "*spec*", "*mock*",
                "node_modules/*", "venv/*", ".venv/*",
                "dist/*", "build/*", "target/*",
                "__pycache__/*", "*.pyc",
                ".git/*", ".pytest_cache/*"
            ]
        
        # 파일 검색 및 검증
        for pattern in include_patterns:
            for file_path in directory.rglob(pattern):
                # 제외 패턴 확인
                if any(file_path.match(exc) for exc in exclude_patterns):
                    continue
                
                # 숨김 파일 제외
                if any(part.startswith('.') for part in file_path.parts[len(directory.parts):]):
                    continue
                
                results.extend(self.validate_file(file_path))
        
        return results
    
    def validate_git_diff(self, base_branch: str = "main") -> List[Dict]:
        """
        Git diff 기반 변경된 파일만 검증
        
        Args:
            base_branch: 비교 기준 브랜치
            
        Returns:
            검증 결과 목록
        """
        results = []
        
        try:
            # 변경된 파일 목록 가져오기
            cmd = f"git diff --name-only {base_branch}...HEAD"
            output = subprocess.check_output(cmd, shell=True, text=True)
            changed_files = output.strip().split('\n') if output.strip() else []
            
            # 각 파일 검증
            for file_path_str in changed_files:
                file_path = Path(file_path_str)
                
                # 지원하는 파일 형식만 검증
                if file_path.suffix in ['.py', '.pyi', '.js', '.jsx', '.ts', '.tsx', '.java']:
                    results.extend(self.validate_file(file_path))
                    
        except subprocess.CalledProcessError as e:
            results.append({
                "error": f"Git command failed: {e}",
                "valid": False
            })
        
        return results
    
    def get_formatter(self, format_type: str):
        """출력 포맷터 반환"""
        formatters = {
            "text": TextFormatter(),
            "json": JSONFormatter(),
            "junit": JUnitFormatter(),
            "github": GitHubFormatter()
        }
        return formatters.get(format_type, TextFormatter())


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="Validate naming conventions in codebase",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate a single file
  %(prog)s path/to/file.py
  
  # Validate a directory with JSON output
  %(prog)s src/ --format json --output report.json
  
  # Validate only changed files in git
  %(prog)s --git-diff --base-branch main
  
  # Use custom convention
  %(prog)s src/ --convention my-convention --fail-on-error

"""
    )
    
    parser.add_argument(
        "path",
        type=str,
        nargs="?",
        default=".",
        help="File or directory path to validate (default: current directory)"
    )
    
    parser.add_argument(
        "--convention",
        "-c",
        default="default",
        help="Naming convention ID to use (default: 'default')"
    )
    
    parser.add_argument(
        "--format",
        "-f",
        choices=["text", "json", "junit", "github"],
        default="text",
        help="Output format"
    )
    
    parser.add_argument(
        "--output",
        "-o",
        help="Output file path (default: stdout)"
    )
    
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit with non-zero code on validation errors"
    )
    
    parser.add_argument(
        "--include",
        nargs="+",
        help="File patterns to include"
    )
    
    parser.add_argument(
        "--exclude",
        nargs="+",
        help="File patterns to exclude"
    )
    
    parser.add_argument(
        "--git-diff",
        action="store_true",
        help="Only validate files changed in git"
    )
    
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch for git diff (default: main)"
    )
    
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Show auto-fix suggestions"
    )
    
    args = parser.parse_args()
    
    # 검증기 생성
    try:
        validator = CINamingValidator(args.convention)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    # Git diff 모드
    if args.git_diff:
        results = validator.validate_git_diff(args.base_branch)
    else:
        # 경로 검증
        path = Path(args.path)
        
        if path.is_file():
            results = validator.validate_file(path)
        elif path.is_dir():
            results = validator.validate_directory(
                path, args.include, args.exclude
            )
        else:
            print(f"Error: Path '{path}' not found", file=sys.stderr)
            return 1
    
    # 결과 요약
    if args.verbose:
        total = len(results)
        valid = sum(1 for r in results if r.get("valid", True))
        invalid = total - valid
        print(f"\nValidation Summary:", file=sys.stderr)
        print(f"  Total entities: {total}", file=sys.stderr)
        print(f"  Valid: {valid}", file=sys.stderr)
        print(f"  Invalid: {invalid}", file=sys.stderr)
        print(f"  Convention: {args.convention}\n", file=sys.stderr)
    
    # 포맷터로 출력
    formatter = validator.get_formatter(args.format)
    
    # Auto-fix 제안 추가
    if args.auto_fix:
        for result in results:
            if not result.get("valid") and "suggestions" in result:
                result["auto_fix_available"] = True
    
    output = formatter.format(results)
    
    # 출력
    if args.output:
        Path(args.output).write_text(output)
        if args.verbose:
            print(f"Results written to: {args.output}", file=sys.stderr)
    else:
        print(output)
    
    # 종료 코드
    if args.fail_on_error:
        error_count = sum(1 for r in results if not r.get("valid", True))
        return 1 if error_count > 0 else 0
    
    return 0


if __name__ == '__main__':
    main()