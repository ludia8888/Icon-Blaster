"""
Merge Validators - 의미론적 병합 검증을 위한 도메인 규칙 엔진

병합된 결과가 비즈니스 규칙을 준수하는지 검증합니다.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """검증 오류 정보"""
    field: str
    message: str
    severity: str  # "error", "warning"
    context: Optional[Dict[str, Any]] = None


class SemanticConflictError(Exception):
    """의미론적 충돌 예외"""
    def __init__(self, message: str, errors: List[ValidationError]):
        super().__init__(message)
        self.errors = errors


class MergeValidator(ABC):
    """병합 검증 기본 클래스"""
    
    @abstractmethod
    def validate(self, merged_data: Dict[str, Any], 
                base_data: Dict[str, Any],
                source_data: Dict[str, Any], 
                target_data: Dict[str, Any]) -> List[ValidationError]:
        """
        병합 결과를 검증합니다.
        
        Args:
            merged_data: 병합된 최종 데이터
            base_data: 공통 조상 데이터
            source_data: 소스 브랜치 데이터
            target_data: 타겟 브랜치 데이터
            
        Returns:
            검증 오류 목록
        """
        pass


class TaxMergeValidator(MergeValidator):
    """세금 관련 필드 검증"""
    
    def validate(self, merged_data: Dict[str, Any], 
                base_data: Dict[str, Any],
                source_data: Dict[str, Any], 
                target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        
        is_taxable = merged_data.get("isTaxable", False)
        tax_rate = merged_data.get("taxRate", 0)
        tax_exemption_reason = merged_data.get("taxExemptionReason")
        
        # 규칙 1: 세금 면제 상품은 세율이 0이어야 함
        if not is_taxable and tax_rate > 0:
            errors.append(ValidationError(
                field="taxRate",
                message=f"Non-taxable items cannot have tax rate > 0 (current: {tax_rate})",
                severity="error",
                context={"isTaxable": is_taxable, "taxRate": tax_rate}
            ))
        
        # 규칙 2: 세금 면제 상품은 면제 사유가 있어야 함
        if not is_taxable and not tax_exemption_reason:
            errors.append(ValidationError(
                field="taxExemptionReason",
                message="Tax-exempt items must have an exemption reason",
                severity="warning",
                context={"isTaxable": is_taxable}
            ))
        
        # 규칙 3: 과세 상품은 면제 사유가 없어야 함
        if is_taxable and tax_exemption_reason:
            errors.append(ValidationError(
                field="taxExemptionReason",
                message="Taxable items should not have exemption reason",
                severity="warning",
                context={"isTaxable": is_taxable, "taxExemptionReason": tax_exemption_reason}
            ))
        
        return errors


class ProductTypeMergeValidator(MergeValidator):
    """제품 타입 관련 필드 검증"""
    
    def validate(self, merged_data: Dict[str, Any], 
                base_data: Dict[str, Any],
                source_data: Dict[str, Any], 
                target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        
        product_type = merged_data.get("type")
        weight = merged_data.get("weight")
        dimensions = merged_data.get("dimensions")
        digital_url = merged_data.get("digital_url")
        file_size = merged_data.get("fileSize")
        
        if product_type == "digital_product":
            # 디지털 제품 검증
            if weight is not None:
                errors.append(ValidationError(
                    field="weight",
                    message="Digital products cannot have weight",
                    severity="error",
                    context={"type": product_type, "weight": weight}
                ))
            
            if dimensions is not None:
                errors.append(ValidationError(
                    field="dimensions",
                    message="Digital products cannot have physical dimensions",
                    severity="error",
                    context={"type": product_type, "dimensions": dimensions}
                ))
            
            if not digital_url:
                errors.append(ValidationError(
                    field="digital_url",
                    message="Digital products must have a download URL",
                    severity="error",
                    context={"type": product_type}
                ))
        
        elif product_type == "physical_product":
            # 실물 제품 검증
            if digital_url is not None:
                errors.append(ValidationError(
                    field="digital_url",
                    message="Physical products should not have digital URL",
                    severity="warning",
                    context={"type": product_type, "digital_url": digital_url}
                ))
            
            if file_size is not None:
                errors.append(ValidationError(
                    field="fileSize",
                    message="Physical products should not have file size",
                    severity="error",
                    context={"type": product_type, "fileSize": file_size}
                ))
        
        return errors


class StateTransitionValidator(MergeValidator):
    """상태 전이 규칙 검증"""
    
    def __init__(self, schema_definition: Optional[Dict[str, Any]] = None):
        """
        Args:
            schema_definition: 상태 전이 규칙이 포함된 스키마 정의
        """
        self.schema = schema_definition or {}
        self.transition_rules = self._extract_transition_rules()
    
    def _extract_transition_rules(self) -> Dict[str, Dict[str, Any]]:
        """스키마에서 상태 전이 규칙 추출"""
        # TODO: 실제 스키마에서 규칙 추출 로직 구현
        # 임시로 하드코딩된 규칙 반환
        return {
            "published": {
                "from": ["review", "draft"],
                "requiredFields": ["reviewed_by", "published_at"]
            },
            "archived": {
                "from": ["published"],
                "requiredFields": ["archived_by", "archived_at", "archive_reason"]
            }
        }
    
    def validate(self, merged_data: Dict[str, Any], 
                base_data: Dict[str, Any],
                source_data: Dict[str, Any], 
                target_data: Dict[str, Any]) -> List[ValidationError]:
        errors = []
        
        base_status = base_data.get("status")
        merged_status = merged_data.get("status")
        
        # 상태가 변경되지 않았으면 검증 불필요
        if base_status == merged_status:
            return errors
        
        # 새로운 상태에 대한 전이 규칙 확인
        if merged_status in self.transition_rules:
            rule = self.transition_rules[merged_status]
            
            # 허용된 전이인지 확인
            allowed_from = rule.get("from", [])
            if base_status not in allowed_from:
                errors.append(ValidationError(
                    field="status",
                    message=f"Invalid state transition: {base_status} -> {merged_status}. Allowed from: {allowed_from}",
                    severity="error",
                    context={"from": base_status, "to": merged_status}
                ))
            
            # 필수 필드 확인
            required_fields = rule.get("requiredFields", [])
            for field in required_fields:
                if not merged_data.get(field):
                    errors.append(ValidationError(
                        field=field,
                        message=f"Field '{field}' is required for status '{merged_status}'",
                        severity="error",
                        context={"status": merged_status}
                    ))
        
        return errors


class MergeValidatorRegistry:
    """병합 검증기 레지스트리"""
    
    def __init__(self):
        self.validators: List[MergeValidator] = []
        self._register_default_validators()
    
    def _register_default_validators(self):
        """기본 검증기 등록"""
        self.register(TaxMergeValidator())
        self.register(ProductTypeMergeValidator())
        self.register(StateTransitionValidator())
    
    def register(self, validator: MergeValidator):
        """검증기 등록"""
        self.validators.append(validator)
        logger.info(f"Registered merge validator: {validator.__class__.__name__}")
    
    def validate_all(self, merged_data: Dict[str, Any], 
                    base_data: Dict[str, Any],
                    source_data: Dict[str, Any], 
                    target_data: Dict[str, Any]) -> List[ValidationError]:
        """
        모든 등록된 검증기로 병합 결과 검증
        
        Returns:
            모든 검증 오류 목록
        """
        all_errors = []
        
        for validator in self.validators:
            try:
                errors = validator.validate(merged_data, base_data, source_data, target_data)
                all_errors.extend(errors)
            except Exception as e:
                logger.error(f"Validator {validator.__class__.__name__} failed: {e}")
                all_errors.append(ValidationError(
                    field="__validator__",
                    message=f"Validator {validator.__class__.__name__} failed: {str(e)}",
                    severity="error"
                ))
        
        return all_errors
    
    def validate_and_raise(self, merged_data: Dict[str, Any], 
                          base_data: Dict[str, Any],
                          source_data: Dict[str, Any], 
                          target_data: Dict[str, Any]):
        """
        검증 실패 시 예외 발생
        
        Raises:
            SemanticConflictError: 심각한 검증 오류가 있을 때
        """
        errors = self.validate_all(merged_data, base_data, source_data, target_data)
        
        # 심각한 오류만 필터링
        critical_errors = [e for e in errors if e.severity == "error"]
        
        if critical_errors:
            error_messages = [f"{e.field}: {e.message}" for e in critical_errors]
            raise SemanticConflictError(
                f"Semantic conflicts detected: {'; '.join(error_messages)}",
                errors=critical_errors
            )


# 전역 레지스트리 인스턴스
merge_validator_registry = MergeValidatorRegistry()