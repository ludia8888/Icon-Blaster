"""
JSON to JSON-LD 변환 유틸리티
Pydantic 모델을 TerminusDB가 이해할 수 있는 JSON-LD 형식으로 변환합니다.
"""

from typing import Dict, List, Any, Union, Optional
from datetime import datetime
import json

from models.ontology import (
    OntologyCreateInput,
    OntologyUpdateInput,
    MultiLingualText,
    PropertyDefinition,
    RelationshipDefinition,
    DataType
)


class JSONToJSONLDConverter:
    """JSON을 JSON-LD로 변환하는 컨버터"""
    
    # JSON-LD 컨텍스트 정의
    DEFAULT_CONTEXT = {
        "@base": "http://example.org/ontology/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "sys": "http://terminusdb.com/schema/sys#",
        "label": "rdfs:label",
        "comment": "rdfs:comment",
        "description": "rdfs:comment"
    }
    
    def __init__(self, base_uri: str = "http://example.org/ontology/"):
        """
        초기화
        
        Args:
            base_uri: 온톨로지의 기본 URI
        """
        self.base_uri = base_uri
        self.context = self.DEFAULT_CONTEXT.copy()
        self.context["@base"] = base_uri
    
    def convert(self, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 데이터를 JSON-LD로 변환
        
        Args:
            ontology_data: OntologyCreateInput의 dict 형태
            
        Returns:
            JSON-LD 형식의 데이터
        """
        # 기본 구조 생성
        jsonld = {
            "@context": self.context,
            "@type": "owl:Class",
            "@id": ontology_data["id"]
        }
        
        # 레이블 처리
        if "label" in ontology_data:
            jsonld["rdfs:label"] = self._convert_multilingual_text(ontology_data["label"])
        
        # 설명 처리
        if "description" in ontology_data:
            jsonld["rdfs:comment"] = self._convert_multilingual_text(ontology_data["description"])
        
        # 부모 클래스 처리
        if ontology_data.get("parent_class"):
            jsonld["rdfs:subClassOf"] = {"@id": ontology_data["parent_class"]}
        
        # 추상 클래스 처리
        if ontology_data.get("abstract"):
            jsonld["sys:abstract"] = True
        
        # 속성 처리
        if "properties" in ontology_data:
            jsonld["@property"] = self._convert_properties(ontology_data["properties"])
        
        # 관계 처리
        if "relationships" in ontology_data:
            self._add_relationships(jsonld, ontology_data["relationships"])
        
        # 메타데이터 처리
        if ontology_data.get("metadata"):
            jsonld["sys:metadata"] = ontology_data["metadata"]
        
        return jsonld
    
    def convert_with_labels(self, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        레이블 정보를 포함한 JSON-LD 변환
        
        Args:
            ontology_data: 온톨로지 데이터
            
        Returns:
            레이블이 포함된 JSON-LD
        """
        jsonld = self.convert(ontology_data)
        
        # 각 속성과 관계에 레이블 정보 보존
        if "@property" in jsonld:
            for prop in jsonld["@property"]:
                # 원본 레이블 정보를 메타데이터로 보존
                if "label" in prop:
                    prop["sys:ui_label"] = prop["label"]
        
        return jsonld
    
    def _convert_multilingual_text(self, text: Union[str, Dict[str, str]]) -> Union[str, Dict[str, Any]]:
        """
        다국어 텍스트 변환
        
        Args:
            text: 문자열 또는 다국어 텍스트 딕셔너리
            
        Returns:
            JSON-LD 형식의 텍스트
        """
        if isinstance(text, str):
            return text
        
        if isinstance(text, dict):
            # 다국어 텍스트를 JSON-LD 형식으로 변환
            result = []
            for lang, value in text.items():
                if value:  # 값이 있는 경우만 추가
                    result.append({
                        "@value": value,
                        "@language": lang
                    })
            
            # 단일 언어인 경우 간소화
            if len(result) == 1:
                return result[0]
            
            return result
        
        return str(text)
    
    def _convert_properties(self, properties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        속성 목록을 JSON-LD 형식으로 변환
        
        Args:
            properties: 속성 정의 목록
            
        Returns:
            JSON-LD 형식의 속성 목록
        """
        jsonld_properties = []
        
        for prop in properties:
            jsonld_prop = {
                "@id": prop["name"],
                "@type": "owl:DatatypeProperty",
                "rdfs:range": {"@id": prop["type"]}
            }
            
            # 레이블 처리
            if "label" in prop:
                jsonld_prop["rdfs:label"] = self._convert_multilingual_text(prop["label"])
            
            # 설명 처리
            if prop.get("description"):
                jsonld_prop["rdfs:comment"] = self._convert_multilingual_text(prop["description"])
            
            # 필수 여부
            if prop.get("required"):
                jsonld_prop["sys:required"] = True
            
            # 기본값
            if prop.get("default") is not None:
                jsonld_prop["sys:default"] = self._convert_value(prop["default"], prop["type"])
            
            # 제약조건
            if prop.get("constraints"):
                jsonld_prop["sys:constraints"] = prop["constraints"]
            
            jsonld_properties.append(jsonld_prop)
        
        return jsonld_properties
    
    def _add_relationships(self, jsonld: Dict[str, Any], relationships: List[Dict[str, Any]]) -> None:
        """
        관계를 JSON-LD에 추가
        
        Args:
            jsonld: JSON-LD 객체
            relationships: 관계 정의 목록
        """
        for rel in relationships:
            rel_jsonld = {
                "@id": rel["predicate"],
                "@type": "owl:ObjectProperty",
                "rdfs:domain": {"@id": jsonld["@id"]},
                "rdfs:range": {"@id": rel["target"]}
            }
            
            # 레이블 처리
            if "label" in rel:
                rel_jsonld["rdfs:label"] = self._convert_multilingual_text(rel["label"])
            
            # 설명 처리
            if rel.get("description"):
                rel_jsonld["rdfs:comment"] = self._convert_multilingual_text(rel["description"])
            
            # 카디널리티
            if rel.get("cardinality"):
                rel_jsonld["sys:cardinality"] = rel["cardinality"]
            
            # 역관계
            if rel.get("inverse_predicate"):
                rel_jsonld["owl:inverseOf"] = {"@id": rel["inverse_predicate"]}
                
                # 역관계 레이블
                if rel.get("inverse_label"):
                    rel_jsonld["sys:inverse_label"] = self._convert_multilingual_text(rel["inverse_label"])
            
            # 관계를 별도의 속성으로 추가
            if "@relationship" not in jsonld:
                jsonld["@relationship"] = []
            jsonld["@relationship"].append(rel_jsonld)
    
    def _convert_value(self, value: Any, datatype: str) -> Dict[str, Any]:
        """
        값을 JSON-LD 형식으로 변환
        
        Args:
            value: 변환할 값
            datatype: 데이터 타입
            
        Returns:
            JSON-LD 형식의 값
        """
        if value is None:
            return None
        
        # 날짜/시간 처리
        if datatype in [DataType.DATE, DataType.DATETIME]:
            if isinstance(value, datetime):
                value = value.isoformat()
        
        return {
            "@value": value,
            "@type": datatype
        }
    
    def convert_query_to_woql(self, query_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        레이블 기반 쿼리를 WOQL 쿼리로 변환
        
        Args:
            query_dict: 레이블 기반 쿼리
            
        Returns:
            WOQL 쿼리를 위한 내부 ID 기반 딕셔너리
        """
        # 기본적인 WOQL 쿼리 구조로 변환
        woql_query = {
            "@type": "woql:And",
            "woql:query_list": []
        }
        
        # 클래스 타입 필터
        if "class" in query_dict:
            woql_query["woql:query_list"].append({
                "@type": "woql:Triple",
                "woql:subject": {"@type": "woql:Variable", "woql:variable_name": "v:Subject"},
                "woql:predicate": "rdf:type",
                "woql:object": query_dict["class"]
            })
        
        # 속성 필터
        if "properties" in query_dict:
            for prop_name, prop_value in query_dict["properties"].items():
                woql_query["woql:query_list"].append({
                    "@type": "woql:Triple",
                    "woql:subject": {"@type": "woql:Variable", "woql:variable_name": "v:Subject"},
                    "woql:predicate": prop_name,
                    "woql:object": self._convert_value_to_literal(prop_value, "xsd:string")
                })
        
        # 쿼리가 비어있으면 모든 문서 조회
        if not woql_query["woql:query_list"]:
            woql_query = {
                "@type": "woql:Triple",
                "woql:subject": {"@type": "woql:Variable", "woql:variable_name": "v:Subject"},
                "woql:predicate": {"@type": "woql:Variable", "woql:variable_name": "v:Predicate"},
                "woql:object": {"@type": "woql:Variable", "woql:variable_name": "v:Object"}
            }
        
        return woql_query
    
    def extract_from_jsonld(self, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        JSON-LD를 일반 JSON으로 역변환
        
        Args:
            jsonld_data: JSON-LD 데이터
            
        Returns:
            일반 JSON 형식의 데이터
        """
        result = {
            "id": jsonld_data.get("@id"),
            "type": jsonld_data.get("@type")
        }
        
        # 레이블 추출
        if "rdfs:label" in jsonld_data:
            result["label"] = self._extract_multilingual_text(jsonld_data["rdfs:label"])
        
        # 설명 추출
        if "rdfs:comment" in jsonld_data:
            result["description"] = self._extract_multilingual_text(jsonld_data["rdfs:comment"])
        
        # 부모 클래스
        if "rdfs:subClassOf" in jsonld_data:
            result["parent_class"] = jsonld_data["rdfs:subClassOf"].get("@id")
        
        # 추상 클래스
        if "sys:abstract" in jsonld_data:
            result["abstract"] = jsonld_data["sys:abstract"]
        
        # 속성 추출
        if "@property" in jsonld_data:
            result["properties"] = self._extract_properties(jsonld_data["@property"])
        
        # 관계 추출
        if "@relationship" in jsonld_data:
            result["relationships"] = self._extract_relationships(jsonld_data["@relationship"])
        
        # 메타데이터
        if "sys:metadata" in jsonld_data:
            result["metadata"] = jsonld_data["sys:metadata"]
        
        return result
    
    def _extract_multilingual_text(self, jsonld_text: Union[str, Dict, List]) -> Union[str, Dict[str, str]]:
        """
        JSON-LD 텍스트를 일반 형식으로 추출
        
        Args:
            jsonld_text: JSON-LD 형식의 텍스트
            
        Returns:
            문자열 또는 다국어 딕셔너리
        """
        if isinstance(jsonld_text, str):
            return jsonld_text
        
        if isinstance(jsonld_text, dict):
            if "@value" in jsonld_text:
                return jsonld_text["@value"]
        
        if isinstance(jsonld_text, list):
            # 다국어 텍스트 복원
            result = {}
            for item in jsonld_text:
                if "@language" in item and "@value" in item:
                    result[item["@language"]] = item["@value"]
            return result if result else ""
        
        return str(jsonld_text)
    
    def _extract_properties(self, jsonld_properties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        JSON-LD 속성을 일반 형식으로 추출
        
        Args:
            jsonld_properties: JSON-LD 속성 목록
            
        Returns:
            일반 속성 목록
        """
        properties = []
        
        for prop in jsonld_properties:
            extracted = {
                "name": prop.get("@id"),
                "type": prop.get("rdfs:range", {}).get("@id")
            }
            
            if "rdfs:label" in prop:
                extracted["label"] = self._extract_multilingual_text(prop["rdfs:label"])
            
            if "rdfs:comment" in prop:
                extracted["description"] = self._extract_multilingual_text(prop["rdfs:comment"])
            
            if "sys:required" in prop:
                extracted["required"] = prop["sys:required"]
            
            if "sys:default" in prop:
                extracted["default"] = self._extract_value(prop["sys:default"])
            
            if "sys:constraints" in prop:
                extracted["constraints"] = prop["sys:constraints"]
            
            properties.append(extracted)
        
        return properties
    
    def _extract_relationships(self, jsonld_relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        JSON-LD 관계를 일반 형식으로 추출
        
        Args:
            jsonld_relationships: JSON-LD 관계 목록
            
        Returns:
            일반 관계 목록
        """
        relationships = []
        
        for rel in jsonld_relationships:
            extracted = {
                "predicate": rel.get("@id"),
                "target": rel.get("rdfs:range", {}).get("@id")
            }
            
            if "rdfs:label" in rel:
                extracted["label"] = self._extract_multilingual_text(rel["rdfs:label"])
            
            if "rdfs:comment" in rel:
                extracted["description"] = self._extract_multilingual_text(rel["rdfs:comment"])
            
            if "sys:cardinality" in rel:
                extracted["cardinality"] = rel["sys:cardinality"]
            
            if "owl:inverseOf" in rel:
                extracted["inverse_predicate"] = rel["owl:inverseOf"].get("@id")
            
            if "sys:inverse_label" in rel:
                extracted["inverse_label"] = self._extract_multilingual_text(rel["sys:inverse_label"])
            
            relationships.append(extracted)
        
        return relationships
    
    def _extract_value(self, jsonld_value: Union[Dict[str, Any], Any]) -> Any:
        """
        JSON-LD 값을 일반 값으로 추출
        
        Args:
            jsonld_value: JSON-LD 형식의 값
            
        Returns:
            추출된 값
        """
        if isinstance(jsonld_value, dict) and "@value" in jsonld_value:
            return jsonld_value["@value"]
        return jsonld_value