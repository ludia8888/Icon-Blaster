"""
Integration Tests for Foundry-style Merge Conflict Resolution
실제 OMS와 TerminusDB 연동 테스트
"""

import pytest
import asyncio
import httpx
from typing import Dict, List, Any
from unittest.mock import AsyncMock, patch
import json

from fastapi.testclient import TestClient
from fastapi import status

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app
from dependencies import get_oms_client, OMSClient


class TestMergeConflictIntegration:
    """병합 충돌 해결 통합 테스트"""

    @pytest.fixture
    def client(self):
        """FastAPI 테스트 클라이언트"""
        return TestClient(app)

    @pytest.fixture
    def mock_oms_client(self):
        """Mock OMS Client"""
        mock_client = AsyncMock(spec=OMSClient)
        mock_client.client = AsyncMock(spec=httpx.AsyncClient)
        return mock_client

    @pytest.fixture
    def sample_conflict_data(self):
        """샘플 충돌 데이터"""
        return {
            "source_changes": [
                {
                    "path": "http://www.w3.org/2000/01/rdf-schema#label",
                    "type": "modify",
                    "old_value": "Original Label",
                    "new_value": "Source Branch Label"
                },
                {
                    "path": "http://schema.org/description",
                    "type": "add",
                    "new_value": "Added description from source"
                }
            ],
            "target_changes": [
                {
                    "path": "http://www.w3.org/2000/01/rdf-schema#label",
                    "type": "modify",
                    "old_value": "Original Label",
                    "new_value": "Target Branch Label"
                },
                {
                    "path": "http://www.w3.org/2000/01/rdf-schema#comment",
                    "type": "add",
                    "new_value": "Added comment from target"
                }
            ]
        }

    @pytest.fixture
    def expected_foundry_conflict(self):
        """예상되는 Foundry 스타일 충돌"""
        return {
            "id": "conflict_1",
            "type": "modify_modify_conflict",
            "severity": "low",
            "path": {
                "raw": "http://www.w3.org/2000/01/rdf-schema#label",
                "human_readable": "이름",
                "namespace": "http://www.w3.org/2000/01/rdf-schema#",
                "property": "label",
                "type": "annotation"
            },
            "sides": {
                "source": {
                    "branch": "feature-branch",
                    "value": "Source Branch Label",
                    "value_type": "string"
                },
                "target": {
                    "branch": "main",
                    "value": "Target Branch Label",
                    "value_type": "string"
                }
            },
            "resolution": {
                "auto_resolvable": False,
                "suggested_strategy": "choose_side_or_merge"
            }
        }

    @pytest.mark.asyncio
    async def test_merge_simulation_success(self, client, mock_oms_client, sample_conflict_data):
        """병합 시뮬레이션 성공 테스트"""
        
        # Mock OMS responses
        branch_info_response = AsyncMock()
        branch_info_response.raise_for_status = AsyncMock()
        branch_info_response.json.return_value = {"status": "success", "data": {"branch": "feature-branch"}}
        
        diff_response = AsyncMock()
        diff_response.raise_for_status = AsyncMock()
        diff_response.json.return_value = {
            "status": "success",
            "data": {
                "changes": sample_conflict_data["source_changes"]
            }
        }
        
        reverse_diff_response = AsyncMock()
        reverse_diff_response.raise_for_status = AsyncMock()
        reverse_diff_response.json.return_value = {
            "status": "success",
            "data": {
                "changes": sample_conflict_data["target_changes"]
            }
        }
        
        mock_oms_client.client.get.side_effect = [
            branch_info_response,  # source branch info
            branch_info_response,  # target branch info
            diff_response,         # diff request
            reverse_diff_response  # reverse diff request
        ]
        
        # Override dependency
        app.dependency_overrides[get_oms_client] = lambda: mock_oms_client
        
        try:
            # Request payload
            merge_request = {
                "source_branch": "feature-branch",
                "target_branch": "main",
                "strategy": "merge"
            }
            
            # API 호출
            response = client.post(
                "/api/v1/database/test-db/merge/simulate",
                json=merge_request
            )
            
            # 응답 검증
            assert response.status_code == status.HTTP_200_OK
            
            response_data = response.json()
            assert response_data["status"] == "success"
            assert "merge_preview" in response_data["data"]
            
            merge_preview = response_data["data"]["merge_preview"]
            assert merge_preview["source_branch"] == "feature-branch"
            assert merge_preview["target_branch"] == "main"
            assert "conflicts" in merge_preview
            assert "statistics" in merge_preview
            
            # 충돌 통계 검증
            stats = merge_preview["statistics"]
            assert "conflicts_detected" in stats
            assert "mergeable" in stats
            assert stats["requires_manual_resolution"] == (stats["conflicts_detected"] > 0)
            
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_merge_simulation_with_conflicts(self, client, mock_oms_client, sample_conflict_data):
        """충돌이 있는 병합 시뮬레이션 테스트"""
        
        # Mock responses with conflicts
        branch_info_response = AsyncMock()
        branch_info_response.raise_for_status = AsyncMock()
        branch_info_response.json.return_value = {"status": "success"}
        
        # Same path conflicts
        conflicting_diff = AsyncMock()
        conflicting_diff.raise_for_status = AsyncMock()
        conflicting_diff.json.return_value = {
            "status": "success",
            "data": {
                "changes": [
                    {
                        "path": "rdfs:label",
                        "type": "modify",
                        "new_value": "Source Label"
                    }
                ]
            }
        }
        
        conflicting_reverse_diff = AsyncMock()
        conflicting_reverse_diff.raise_for_status = AsyncMock()
        conflicting_reverse_diff.json.return_value = {
            "status": "success",
            "data": {
                "changes": [
                    {
                        "path": "rdfs:label",
                        "type": "modify",
                        "new_value": "Target Label"
                    }
                ]
            }
        }
        
        mock_oms_client.client.get.side_effect = [
            branch_info_response,
            branch_info_response,
            conflicting_diff,
            conflicting_reverse_diff
        ]
        
        app.dependency_overrides[get_oms_client] = lambda: mock_oms_client
        
        try:
            merge_request = {
                "source_branch": "feature-branch",
                "target_branch": "main",
                "strategy": "merge"
            }
            
            response = client.post(
                "/api/v1/database/test-db/merge/simulate",
                json=merge_request
            )
            
            assert response.status_code == status.HTTP_200_OK
            
            response_data = response.json()
            merge_preview = response_data["data"]["merge_preview"]
            
            # 충돌 감지 검증
            assert len(merge_preview["conflicts"]) > 0
            assert merge_preview["statistics"]["mergeable"] == False
            assert merge_preview["statistics"]["requires_manual_resolution"] == True
            
            # 충돌 구조 검증
            conflict = merge_preview["conflicts"][0]
            assert "id" in conflict
            assert "type" in conflict
            assert "path" in conflict
            assert "sides" in conflict
            assert "source" in conflict["sides"]
            assert "target" in conflict["sides"]
            
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_conflict_resolution_success(self, client, mock_oms_client):
        """충돌 해결 성공 테스트"""
        
        # Mock merge response
        merge_response = AsyncMock()
        merge_response.raise_for_status = AsyncMock()
        merge_response.json.return_value = {
            "status": "success",
            "data": {
                "merge_id": "merge_123",
                "commit_id": "commit_456",
                "merged": True
            }
        }
        
        mock_oms_client.client.post.return_value = merge_response
        
        app.dependency_overrides[get_oms_client] = lambda: mock_oms_client
        
        try:
            # 해결책 데이터
            resolution_request = {
                "source_branch": "feature-branch",
                "target_branch": "main",
                "strategy": "merge",
                "message": "Resolve conflicts manually",
                "author": "test@example.com",
                "resolutions": [
                    {
                        "path": "rdfs:label",
                        "resolution_type": "use_value",
                        "resolved_value": "Manually Resolved Label",
                        "metadata": {
                            "resolution_strategy": "manual_merge"
                        }
                    }
                ]
            }
            
            response = client.post(
                "/api/v1/database/test-db/merge/resolve",
                json=resolution_request
            )
            
            assert response.status_code == status.HTTP_200_OK
            
            response_data = response.json()
            assert response_data["status"] == "success"
            assert "merge_result" in response_data["data"]
            assert "resolved_conflicts" in response_data["data"]
            assert response_data["data"]["resolved_conflicts"] == 1
            
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_conflict_converter_integration(self):
        """충돌 변환기 통합 테스트"""
        from utils.conflict_converter import ConflictConverter
        
        converter = ConflictConverter()
        
        # 샘플 TerminusDB 충돌
        terminus_conflicts = [
            {
                "path": "http://www.w3.org/2000/01/rdf-schema#label",
                "type": "content_conflict",
                "source_change": {
                    "type": "modify",
                    "new_value": "Source Label"
                },
                "target_change": {
                    "type": "modify", 
                    "new_value": "Target Label"
                }
            }
        ]
        
        # Foundry 형식으로 변환
        foundry_conflicts = await converter.convert_conflicts_to_foundry_format(
            terminus_conflicts, "test-db", "feature-branch", "main"
        )
        
        assert len(foundry_conflicts) == 1
        
        conflict = foundry_conflicts[0]
        assert conflict["id"] == "conflict_1"
        assert conflict["type"] == "modify_modify_conflict"
        assert conflict["path"]["human_readable"] == "이름"
        assert conflict["sides"]["source"]["value"] == "Source Label"
        assert conflict["sides"]["target"]["value"] == "Target Label"

    @pytest.mark.asyncio
    async def test_path_mapping_system(self):
        """JSON-LD 경로 매핑 시스템 테스트"""
        from utils.conflict_converter import ConflictConverter
        
        converter = ConflictConverter()
        
        # 다양한 경로 테스트
        test_paths = [
            "http://www.w3.org/2000/01/rdf-schema#label",
            "http://www.w3.org/2002/07/owl#Class",
            "http://schema.org/description",
            "rdfs:comment",
            "owl:subClassOf"
        ]
        
        for path in test_paths:
            path_info = await converter._analyze_jsonld_path(path)
            
            assert path_info.full_path == path
            assert path_info.property_name is not None
            assert path_info.human_readable is not None
            assert path_info.path_type is not None
            
            # 한국어 매핑 확인
            if path == "http://www.w3.org/2000/01/rdf-schema#label":
                assert "이름" in path_info.context["korean_name"]

    @pytest.mark.asyncio
    async def test_error_handling(self, client, mock_oms_client):
        """에러 처리 테스트"""
        
        # Mock network error
        mock_oms_client.client.get.side_effect = httpx.HTTPError("Network error")
        
        app.dependency_overrides[get_oms_client] = lambda: mock_oms_client
        
        try:
            merge_request = {
                "source_branch": "feature-branch",
                "target_branch": "main",
                "strategy": "merge"
            }
            
            response = client.post(
                "/api/v1/database/test-db/merge/simulate",
                json=merge_request
            )
            
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio 
    async def test_invalid_input_validation(self, client, mock_oms_client):
        """입력 검증 테스트"""
        
        app.dependency_overrides[get_oms_client] = lambda: mock_oms_client
        
        try:
            # 잘못된 브랜치 이름
            invalid_request = {
                "source_branch": "../malicious-path",
                "target_branch": "main",
                "strategy": "merge"
            }
            
            response = client.post(
                "/api/v1/database/test-db/merge/simulate",
                json=invalid_request
            )
            
            assert response.status_code == status.HTTP_400_BAD_REQUEST
            
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_bff_dependencies_integration(self):
        """BFF Dependencies 통합 테스트"""
        from dependencies import TerminusService
        
        # Mock OMS Client
        mock_oms = AsyncMock(spec=OMSClient)
        mock_oms.client = AsyncMock(spec=httpx.AsyncClient)
        
        # Mock simulation response
        simulation_response = AsyncMock()
        simulation_response.raise_for_status = AsyncMock()
        simulation_response.json.return_value = {
            "status": "success",
            "data": {
                "merge_preview": {
                    "conflicts": [],
                    "statistics": {"mergeable": True, "conflicts_detected": 0}
                }
            }
        }
        
        mock_oms.client.post.return_value = simulation_response
        
        with patch('dependencies.get_oms_client', return_value=mock_oms):
            terminus_service = TerminusService()
            
            # 시뮬레이션 테스트
            result = await terminus_service.simulate_merge("test-db", "feature", "main")
            
            assert result["status"] == "success"
            assert "merge_preview" in result["data"]
            
            # Mock calls 검증
            mock_oms.client.post.assert_called_once()
            call_args = mock_oms.client.post.call_args
            assert "/database/test-db/merge/simulate" in call_args[0][0]

    def test_api_documentation_completeness(self, client):
        """API 문서화 완성도 테스트"""
        
        # OpenAPI 스키마 확인
        response = client.get("/openapi.json")
        assert response.status_code == status.HTTP_200_OK
        
        openapi_schema = response.json()
        
        # 새로운 엔드포인트들이 문서에 포함되었는지 확인
        paths = openapi_schema.get("paths", {})
        
        expected_endpoints = [
            "/api/v1/database/{db_name}/merge/simulate",
            "/api/v1/database/{db_name}/merge/resolve"
        ]
        
        for endpoint in expected_endpoints:
            # 경로 패턴 확인
            pattern_found = any(
                endpoint.replace("{db_name}", "{db_name}") in path 
                for path in paths.keys()
            )
            assert pattern_found, f"Endpoint {endpoint} not found in OpenAPI schema"


@pytest.mark.integration
class TestFullStackMergeConflictFlow:
    """전체 스택 병합 충돌 플로우 테스트"""
    
    @pytest.mark.asyncio
    async def test_complete_conflict_resolution_workflow(self):
        """완전한 충돌 해결 워크플로우 테스트"""
        
        # 이 테스트는 실제 환경에서 실행되어야 함
        # 1. 데이터베이스 생성
        # 2. 브랜치 생성 
        # 3. 충돌하는 변경사항 추가
        # 4. 병합 시뮬레이션
        # 5. 충돌 해결
        # 6. 실제 병합
        
        pytest.skip("Requires live TerminusDB instance")