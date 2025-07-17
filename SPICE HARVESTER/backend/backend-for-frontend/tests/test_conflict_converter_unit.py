"""
Unit Tests for Conflict Converter
충돌 변환기 단위 테스트
"""

import pytest
import asyncio
from typing import Dict, List, Any

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from utils.conflict_converter import (
    ConflictConverter, 
    ConflictSeverity, 
    PathType,
    JsonLdPath,
    ConflictAnalysis
)


class TestConflictConverter:
    """ConflictConverter 단위 테스트"""

    @pytest.fixture
    def converter(self):
        """ConflictConverter 인스턴스"""
        return ConflictConverter()

    @pytest.fixture
    def sample_terminus_conflict(self):
        """샘플 TerminusDB 충돌"""
        return {
            "path": "http://www.w3.org/2000/01/rdf-schema#label",
            "type": "content_conflict",
            "source_change": {
                "type": "modify",
                "old_value": "Original Label",
                "new_value": "Source Branch Label"
            },
            "target_change": {
                "type": "modify",
                "old_value": "Original Label", 
                "new_value": "Target Branch Label"
            }
        }

    @pytest.mark.asyncio
    async def test_namespace_splitting(self, converter):
        """네임스페이스 분리 테스트"""
        
        test_cases = [
            ("http://www.w3.org/2000/01/rdf-schema#label", 
             ("http://www.w3.org/2000/01/rdf-schema#", "label")),
            ("rdfs:comment", ("rdfs:", "comment")),
            ("owl:Class", ("owl:", "Class")),
            ("simple_property", (None, "simple_property")),
            ("http://schema.org/description",
             ("http://schema.org/", "description"))
        ]
        
        for path, expected in test_cases:
            namespace, property_name = converter._split_namespace_and_property(path)
            assert (namespace, property_name) == expected, f"Failed for {path}"

    @pytest.mark.asyncio
    async def test_path_type_determination(self, converter):
        """경로 타입 결정 테스트"""
        
        test_cases = [
            ("type", PathType.CLASS_PROPERTY),
            ("Class", PathType.CLASS_PROPERTY),
            ("ObjectProperty", PathType.CLASS_PROPERTY),
            ("subClassOf", PathType.RELATIONSHIP),
            ("equivalentClass", PathType.RELATIONSHIP),
            ("label", PathType.ANNOTATION),
            ("comment", PathType.ANNOTATION),
            ("http://schema.org/name", PathType.SCHEMA_REFERENCE),
            ("custom_property", PathType.UNKNOWN)
        ]
        
        for property_name, expected_type in test_cases:
            path_type = converter._determine_path_type(f"test#{property_name}", property_name)
            assert path_type == expected_type, f"Failed for {property_name}"

    @pytest.mark.asyncio 
    async def test_human_readable_conversion(self, converter):
        """사람이 읽기 쉬운 형태 변환 테스트"""
        
        test_cases = [
            ("http://www.w3.org/2000/01/rdf-schema#", "label", "이름"),
            ("http://www.w3.org/2000/01/rdf-schema#", "comment", "설명"),
            ("rdfs:", "label", "rdfs:label"),
            (None, "customProperty", "custom Property"),
            ("owl:", "Class", "owl:Class")
        ]
        
        for namespace, property_name, expected in test_cases:
            result = converter._convert_to_human_readable(namespace, property_name)
            assert expected in result or result == expected, f"Failed for {namespace}{property_name}"

    @pytest.mark.asyncio
    async def test_jsonld_path_analysis(self, converter):
        """JSON-LD 경로 분석 테스트"""
        
        path = "http://www.w3.org/2000/01/rdf-schema#label"
        path_info = await converter._analyze_jsonld_path(path)
        
        assert isinstance(path_info, JsonLdPath)
        assert path_info.full_path == path
        assert path_info.namespace == "http://www.w3.org/2000/01/rdf-schema#"
        assert path_info.property_name == "label"
        assert path_info.path_type == PathType.ANNOTATION
        assert "이름" in path_info.human_readable or path_info.human_readable == "이름"
        assert isinstance(path_info.context, dict)

    @pytest.mark.asyncio
    async def test_conflict_type_determination(self, converter):
        """충돌 타입 결정 테스트"""
        
        test_cases = [
            ({"type": "add"}, {"type": "add"}, "add_add_conflict"),
            ({"type": "modify"}, {"type": "modify"}, "modify_modify_conflict"),
            ({"type": "delete"}, {"type": "modify"}, "delete_modify_conflict"),
            ({"type": "modify"}, {"type": "delete"}, "modify_delete_conflict"),
            ({"type": "delete"}, {"type": "delete"}, "delete_delete_conflict"),
            ({"type": "unknown"}, {"type": "unknown"}, "unknown_conflict")
        ]
        
        path_info = JsonLdPath(
            full_path="test", namespace=None, property_name="test",
            path_type=PathType.UNKNOWN, human_readable="test", context={}
        )
        
        for source_change, target_change, expected_type in test_cases:
            conflict_type = converter._determine_conflict_type(source_change, target_change, path_info)
            assert conflict_type == expected_type

    @pytest.mark.asyncio
    async def test_severity_assessment(self, converter):
        """충돌 심각도 평가 테스트"""
        
        # 높은 심각도 - 클래스 속성
        class_property_path = JsonLdPath(
            full_path="test", namespace=None, property_name="test",
            path_type=PathType.CLASS_PROPERTY, human_readable="test", context={}
        )
        severity = converter._assess_severity("modify_modify_conflict", class_property_path, {}, {})
        assert severity == ConflictSeverity.HIGH
        
        # 낮은 심각도 - 어노테이션
        annotation_path = JsonLdPath(
            full_path="test", namespace=None, property_name="test",
            path_type=PathType.ANNOTATION, human_readable="test", context={}
        )
        severity = converter._assess_severity("modify_modify_conflict", annotation_path, {}, {})
        assert severity == ConflictSeverity.LOW
        
        # 높은 심각도 - 삭제 충돌
        severity = converter._assess_severity("delete_modify_conflict", annotation_path, {}, {})
        assert severity == ConflictSeverity.HIGH

    @pytest.mark.asyncio
    async def test_auto_resolvability_assessment(self, converter):
        """자동 해결 가능성 평가 테스트"""
        
        # 동일한 값으로의 변경 - 자동 해결 가능
        same_value_changes = (
            {"new_value": "same_value"}, 
            {"new_value": "same_value"}
        )
        auto_resolvable = converter._assess_auto_resolvability("modify_modify_conflict", *same_value_changes)
        assert auto_resolvable == True
        
        # 다른 값으로의 변경 - 수동 해결 필요
        different_value_changes = (
            {"new_value": "value_1"}, 
            {"new_value": "value_2"}
        )
        auto_resolvable = converter._assess_auto_resolvability("modify_modify_conflict", *different_value_changes)
        assert auto_resolvable == False

    @pytest.mark.asyncio
    async def test_value_extraction_and_typing(self, converter):
        """값 추출 및 타입 지정 테스트"""
        
        test_cases = [
            ({"new_value": "string_value"}, ("string_value", "string")),
            ({"new_value": 42}, (42, "number")),
            ({"new_value": True}, (True, "boolean")),
            ({"new_value": {"key": "value"}}, ({"key": "value"}, "object")),
            ({"new_value": [1, 2, 3]}, ([1, 2, 3], "array")),
            ({"value": "fallback_value"}, ("fallback_value", "string"))
        ]
        
        for change, expected in test_cases:
            value, value_type = converter._extract_value_and_type(change)
            assert (value, value_type) == expected

    @pytest.mark.asyncio
    async def test_value_preview_generation(self, converter):
        """값 미리보기 생성 테스트"""
        
        # 짧은 문자열
        preview = converter._generate_value_preview("short", "string")
        assert preview == "short"
        
        # 긴 문자열
        long_string = "a" * 150
        preview = converter._generate_value_preview(long_string, "string")
        assert len(preview) <= 103  # 100 + "..."
        assert preview.endswith("...")
        
        # 배열
        preview = converter._generate_value_preview([1, 2, 3], "array")
        assert "배열" in preview and "3개" in preview
        
        # 객체
        obj = {"key": "value"}
        preview = converter._generate_value_preview(obj, "object")
        assert "key" in preview

    @pytest.mark.asyncio
    async def test_resolution_options_generation(self, converter):
        """해결 옵션 생성 테스트"""
        
        analysis = ConflictAnalysis(
            conflict_type="modify_modify_conflict",
            severity=ConflictSeverity.MEDIUM,
            auto_resolvable=False,
            suggested_resolution="choose_side_or_merge",
            impact_analysis={}
        )
        
        options = converter._generate_resolution_options("source_value", "target_value", analysis)
        
        assert len(options) >= 2
        assert any(opt["id"] == "use_source" for opt in options)
        assert any(opt["id"] == "use_target" for opt in options)
        
        # 수동 병합 옵션 테스트
        analysis.suggested_resolution = "manual_merge_required"
        options = converter._generate_resolution_options("source_value", "target_value", analysis)
        
        assert any(opt["id"] == "manual_merge" for opt in options)

    @pytest.mark.asyncio
    async def test_complete_conflict_conversion(self, converter, sample_terminus_conflict):
        """완전한 충돌 변환 테스트"""
        
        foundry_conflicts = await converter.convert_conflicts_to_foundry_format(
            [sample_terminus_conflict], "test-db", "feature-branch", "main"
        )
        
        assert len(foundry_conflicts) == 1
        
        conflict = foundry_conflicts[0]
        
        # 기본 구조 검증
        required_fields = ["id", "type", "severity", "path", "description", "sides", "resolution", "metadata"]
        for field in required_fields:
            assert field in conflict, f"Missing field: {field}"
        
        # 경로 정보 검증
        assert conflict["path"]["raw"] == sample_terminus_conflict["path"]
        assert conflict["path"]["human_readable"] is not None
        assert conflict["path"]["type"] == "annotation"
        
        # 충돌 양측 정보 검증
        assert "source" in conflict["sides"]
        assert "target" in conflict["sides"]
        assert conflict["sides"]["source"]["value"] == "Source Branch Label"
        assert conflict["sides"]["target"]["value"] == "Target Branch Label"
        
        # 해결 정보 검증
        assert isinstance(conflict["resolution"]["auto_resolvable"], bool)
        assert conflict["resolution"]["suggested_strategy"] is not None
        assert isinstance(conflict["resolution"]["options"], list)

    @pytest.mark.asyncio
    async def test_fallback_conflict_creation(self, converter):
        """폴백 충돌 생성 테스트"""
        
        invalid_conflict = {
            "path": "malformed_path",
            "source_change": {"new_value": "source"},
            "target_change": {"new_value": "target"}
        }
        
        fallback_conflict = converter._create_fallback_conflict(invalid_conflict, 1)
        
        assert fallback_conflict["id"] == "conflict_1"
        assert fallback_conflict["type"] == "unknown_conflict"
        assert fallback_conflict["metadata"]["conversion_error"] == True
        assert "original_conflict" in fallback_conflict["metadata"]

    @pytest.mark.asyncio
    async def test_korean_property_mappings(self, converter):
        """한국어 속성 매핑 테스트"""
        
        korean_mappings = {
            "rdfs:label": "이름",
            "rdfs:comment": "설명",
            "owl:Class": "클래스",
            "rdf:type": "타입"
        }
        
        for path, expected_korean in korean_mappings.items():
            path_info = await converter._analyze_jsonld_path(path)
            assert expected_korean in path_info.context.get("korean_name", "")

    @pytest.mark.asyncio
    async def test_impact_analysis(self, converter):
        """영향 분석 테스트"""
        
        # 스키마 파괴적 변경
        class_property_path = JsonLdPath(
            full_path="test", namespace=None, property_name="test",
            path_type=PathType.CLASS_PROPERTY, human_readable="test", context={}
        )
        
        impact = converter._analyze_impact("modify_modify_conflict", class_property_path, {}, {})
        assert impact["schema_breaking"] == True
        assert impact["backward_compatibility"] == True
        
        # 삭제 충돌 - 데이터 손실 위험
        impact = converter._analyze_impact("delete_modify_conflict", class_property_path, {}, {})
        assert impact["data_loss_risk"] == True
        assert impact["backward_compatibility"] == False

    @pytest.mark.asyncio
    async def test_multiple_conflicts_conversion(self, converter):
        """여러 충돌 변환 테스트"""
        
        multiple_conflicts = [
            {
                "path": "rdfs:label",
                "type": "content_conflict",
                "source_change": {"type": "modify", "new_value": "Source Label"},
                "target_change": {"type": "modify", "new_value": "Target Label"}
            },
            {
                "path": "rdfs:comment",
                "type": "content_conflict", 
                "source_change": {"type": "add", "new_value": "Source Comment"},
                "target_change": {"type": "add", "new_value": "Target Comment"}
            }
        ]
        
        foundry_conflicts = await converter.convert_conflicts_to_foundry_format(
            multiple_conflicts, "test-db", "feature", "main"
        )
        
        assert len(foundry_conflicts) == 2
        
        # ID 유니크성 확인
        ids = [conflict["id"] for conflict in foundry_conflicts]
        assert len(set(ids)) == len(ids)
        
        # 다른 충돌 타입 확인
        types = [conflict["type"] for conflict in foundry_conflicts]
        assert "modify_modify_conflict" in types
        assert "add_add_conflict" in types


if __name__ == "__main__":
    pytest.main([__file__, "-v"])