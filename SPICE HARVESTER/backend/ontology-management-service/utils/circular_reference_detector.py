"""
🔥 THINK ULTRA! CircularReferenceDetector
순환 참조 탐지 및 관계 사이클 방지
"""

from typing import List, Dict, Set, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
import logging
from collections import defaultdict, deque

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.ontology import Relationship, OntologyBase

logger = logging.getLogger(__name__)


class CycleType(Enum):
    """순환 참조 유형"""
    DIRECT_CYCLE = "direct"           # A -> B -> A
    INDIRECT_CYCLE = "indirect"       # A -> B -> C -> A
    SELF_REFERENCE = "self"           # A -> A
    COMPLEX_CYCLE = "complex"         # 복잡한 다중 경로 순환


@dataclass
class CycleInfo:
    """순환 참조 정보"""
    cycle_type: CycleType
    path: List[str]
    predicates: List[str]
    length: int
    severity: str  # "critical", "warning", "info"
    message: str
    can_break: bool = True  # 순환을 끊을 수 있는지 여부


@dataclass
class RelationshipEdge:
    """관계 그래프의 엣지"""
    source: str
    target: str
    predicate: str
    cardinality: str
    is_bidirectional: bool = False


class CircularReferenceDetector:
    """
    🔥 THINK ULTRA! 순환 참조 탐지기
    
    기능:
    1. 직접 순환 참조 탐지 (A -> B -> A)
    2. 간접 순환 참조 탐지 (A -> B -> C -> A) 
    3. 자기 참조 탐지 (A -> A)
    4. 복잡한 다중 경로 순환 탐지
    5. 순환 끊기 제안
    6. 허용 가능한 순환 판별
    """
    
    def __init__(self, max_cycle_depth: int = 10):
        """
        초기화
        
        Args:
            max_cycle_depth: 탐지할 최대 순환 깊이
        """
        self.max_cycle_depth = max_cycle_depth
        self.relationship_graph: Dict[str, List[RelationshipEdge]] = defaultdict(list)
        self.reverse_graph: Dict[str, List[RelationshipEdge]] = defaultdict(list)
        
        # 허용 가능한 자기 참조 패턴
        self.allowed_self_references = {
            "parentOf", "childOf", "manages", "managedBy",
            "follows", "followedBy", "friendOf", "partOf"
        }
        
        # 허용 가능한 순환 패턴 (계층 구조 등)
        self.allowed_cycle_patterns = {
            ("parentOf", "childOf"),
            ("contains", "partOf"),
            ("manages", "managedBy")
        }
    
    def build_relationship_graph(self, ontologies: List[OntologyBase]) -> None:
        """온톨로지들로부터 관계 그래프 구축"""
        
        logger.info(f"Building relationship graph from {len(ontologies)} ontologies")
        
        self.relationship_graph.clear()
        self.reverse_graph.clear()
        
        for ontology in ontologies:
            source_class = ontology.id
            
            for rel in ontology.relationships:
                target_class = rel.target
                
                # 정방향 엣지
                edge = RelationshipEdge(
                    source=source_class,
                    target=target_class,
                    predicate=rel.predicate,
                    cardinality=str(rel.cardinality.value if hasattr(rel.cardinality, 'value') else rel.cardinality),
                    is_bidirectional=bool(rel.inverse_predicate)
                )
                
                self.relationship_graph[source_class].append(edge)
                self.reverse_graph[target_class].append(edge)
                
                # 양방향 관계인 경우 역방향 엣지도 추가
                if rel.inverse_predicate:
                    inverse_edge = RelationshipEdge(
                        source=target_class,
                        target=source_class,
                        predicate=rel.inverse_predicate,
                        cardinality=self._get_inverse_cardinality(edge.cardinality),
                        is_bidirectional=True
                    )
                    
                    self.relationship_graph[target_class].append(inverse_edge)
                    self.reverse_graph[source_class].append(inverse_edge)
        
        logger.info(f"Graph built: {len(self.relationship_graph)} nodes, "
                   f"{sum(len(edges) for edges in self.relationship_graph.values())} edges")
    
    def detect_all_cycles(self) -> List[CycleInfo]:
        """모든 순환 참조 탐지"""
        
        logger.info("Starting comprehensive cycle detection")
        
        cycles = []
        
        # 1. 자기 참조 탐지
        cycles.extend(self._detect_self_references())
        
        # 2. 직접 순환 탐지 (길이 2)
        cycles.extend(self._detect_direct_cycles())
        
        # 3. 간접 순환 탐지 (길이 3+)
        cycles.extend(self._detect_indirect_cycles())
        
        # 4. 복잡한 순환 탐지
        cycles.extend(self._detect_complex_cycles())
        
        # 중복 제거 및 우선순위 정렬
        unique_cycles = self._deduplicate_cycles(cycles)
        sorted_cycles = self._sort_cycles_by_severity(unique_cycles)
        
        logger.info(f"Detected {len(sorted_cycles)} unique cycles")
        
        return sorted_cycles
    
    def detect_cycle_for_new_relationship(
        self, 
        source: str, 
        target: str, 
        predicate: str
    ) -> List[CycleInfo]:
        """새로운 관계 추가 시 발생할 수 있는 순환 참조 탐지"""
        
        logger.info(f"Checking potential cycles for new relationship: {source} -{predicate}-> {target}")
        
        cycles = []
        
        # 1. 즉시 자기 참조 체크
        if source == target:
            cycle = CycleInfo(
                cycle_type=CycleType.SELF_REFERENCE,
                path=[source],
                predicates=[predicate],
                length=1,
                severity=self._assess_self_reference_severity(predicate),
                message=f"Self-reference detected: {source} -{predicate}-> {source}",
                can_break=predicate not in self.allowed_self_references
            )
            cycles.append(cycle)
        
        # 2. 기존 그래프에 새 관계를 임시 추가하여 순환 탐지
        temp_edge = RelationshipEdge(
            source=source,
            target=target,
            predicate=predicate,
            cardinality="unknown"
        )
        
        # 임시로 그래프에 추가
        self.relationship_graph[source].append(temp_edge)
        
        try:
            # target에서 source로 돌아가는 경로 탐색
            paths = self._find_paths_between(target, source, self.max_cycle_depth)
            
            for path in paths:
                full_cycle_path = [source] + path
                cycle_predicates = [predicate] + [edge.predicate for edge in self._get_path_edges(path)]
                
                cycle = CycleInfo(
                    cycle_type=CycleType.INDIRECT_CYCLE if len(full_cycle_path) > 2 else CycleType.DIRECT_CYCLE,
                    path=full_cycle_path,
                    predicates=cycle_predicates,
                    length=len(full_cycle_path),
                    severity=self._assess_cycle_severity(full_cycle_path, cycle_predicates),
                    message=f"Potential cycle: {' -> '.join(full_cycle_path)}",
                    can_break=True
                )
                cycles.append(cycle)
        
        finally:
            # 임시 엣지 제거
            self.relationship_graph[source].remove(temp_edge)
        
        return cycles
    
    def _detect_self_references(self) -> List[CycleInfo]:
        """자기 참조 탐지"""
        
        cycles = []
        
        for source, edges in self.relationship_graph.items():
            for edge in edges:
                if edge.target == source:  # 자기 참조
                    severity = self._assess_self_reference_severity(edge.predicate)
                    
                    cycle = CycleInfo(
                        cycle_type=CycleType.SELF_REFERENCE,
                        path=[source],
                        predicates=[edge.predicate],
                        length=1,
                        severity=severity,
                        message=f"Self-reference: {source} -{edge.predicate}-> {source}",
                        can_break=edge.predicate not in self.allowed_self_references
                    )
                    cycles.append(cycle)
        
        return cycles
    
    def _detect_direct_cycles(self) -> List[CycleInfo]:
        """직접 순환 탐지 (A -> B -> A)"""
        
        cycles = []
        
        for source, edges in self.relationship_graph.items():
            for edge in edges:
                target = edge.target
                if target == source:
                    continue  # 자기 참조는 이미 처리
                
                # target에서 source로 돌아가는 직접 경로 확인
                for return_edge in self.relationship_graph.get(target, []):
                    if return_edge.target == source:
                        # 직접 순환 발견
                        cycle = CycleInfo(
                            cycle_type=CycleType.DIRECT_CYCLE,
                            path=[source, target, source],
                            predicates=[edge.predicate, return_edge.predicate],
                            length=2,
                            severity=self._assess_direct_cycle_severity(edge, return_edge),
                            message=f"Direct cycle: {source} -{edge.predicate}-> {target} -{return_edge.predicate}-> {source}",
                            can_break=self._can_break_cycle([edge.predicate, return_edge.predicate])
                        )
                        cycles.append(cycle)
        
        return cycles
    
    def _detect_indirect_cycles(self) -> List[CycleInfo]:
        """간접 순환 탐지 (A -> B -> C -> A)"""
        
        cycles = []
        
        for start_node in self.relationship_graph.keys():
            # DFS로 시작 노드에서 출발하여 다시 돌아오는 경로 탐색
            visited = set()
            path_stack = []
            predicate_stack = []
            
            cycles.extend(self._dfs_cycle_detection(
                current=start_node,
                start=start_node,
                visited=visited,
                path_stack=path_stack,
                predicate_stack=predicate_stack,
                depth=0
            ))
        
        return cycles
    
    def _detect_complex_cycles(self) -> List[CycleInfo]:
        """복잡한 다중 경로 순환 탐지"""
        
        cycles = []
        
        # Strongly Connected Components (SCC) 알고리즘 사용
        sccs = self._find_strongly_connected_components()
        
        for scc in sccs:
            if len(scc) > 1:  # 2개 이상의 노드가 강하게 연결된 경우
                # SCC 내의 대표 순환 경로 찾기
                representative_cycle = self._find_representative_cycle(scc)
                
                if representative_cycle:
                    cycle = CycleInfo(
                        cycle_type=CycleType.COMPLEX_CYCLE,
                        path=representative_cycle['path'],
                        predicates=representative_cycle['predicates'],
                        length=len(representative_cycle['path']),
                        severity="warning",
                        message=f"Complex cycle involving {len(scc)} classes: {', '.join(scc)}",
                        can_break=True
                    )
                    cycles.append(cycle)
        
        return cycles
    
    def _dfs_cycle_detection(
        self,
        current: str,
        start: str,
        visited: Set[str],
        path_stack: List[str],
        predicate_stack: List[str],
        depth: int
    ) -> List[CycleInfo]:
        """DFS를 사용한 순환 탐지"""
        
        cycles = []
        
        if depth >= self.max_cycle_depth:
            return cycles
        
        if current in visited:
            if current == start and len(path_stack) > 1:
                # 순환 발견
                full_path = path_stack + [current]
                cycle = CycleInfo(
                    cycle_type=CycleType.INDIRECT_CYCLE,
                    path=full_path,
                    predicates=predicate_stack,
                    length=len(path_stack),
                    severity=self._assess_cycle_severity(full_path, predicate_stack),
                    message=f"Indirect cycle: {' -> '.join(full_path)}",
                    can_break=self._can_break_cycle(predicate_stack)
                )
                cycles.append(cycle)
            return cycles
        
        visited.add(current)
        path_stack.append(current)
        
        for edge in self.relationship_graph.get(current, []):
            predicate_stack.append(edge.predicate)
            cycles.extend(self._dfs_cycle_detection(
                current=edge.target,
                start=start,
                visited=visited.copy(),
                path_stack=path_stack.copy(),
                predicate_stack=predicate_stack.copy(),
                depth=depth + 1
            ))
            predicate_stack.pop()
        
        path_stack.pop()
        
        return cycles
    
    def _find_strongly_connected_components(self) -> List[List[str]]:
        """Tarjan 알고리즘을 사용한 강하게 연결된 컴포넌트 탐지"""
        
        index_counter = [0]
        stack = []
        lowlinks = {}
        index = {}
        on_stack = {}
        sccs = []
        
        def strongconnect(node):
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack[node] = True
            
            for edge in self.relationship_graph.get(node, []):
                successor = edge.target
                if successor not in index:
                    strongconnect(successor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[successor])
                elif on_stack[successor]:
                    lowlinks[node] = min(lowlinks[node], index[successor])
            
            if lowlinks[node] == index[node]:
                component = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == node:
                        break
                sccs.append(component)
        
        for node in self.relationship_graph:
            if node not in index:
                strongconnect(node)
        
        return [scc for scc in sccs if len(scc) > 1]
    
    def _find_representative_cycle(self, scc: List[str]) -> Optional[Dict[str, Any]]:
        """SCC 내의 대표 순환 경로 찾기"""
        
        if len(scc) < 2:
            return None
        
        # 첫 번째 노드에서 시작하여 SCC 내에서만 이동하는 순환 찾기
        start = scc[0]
        visited = set()
        path = []
        predicates = []
        
        def dfs_in_scc(node, target_depth=len(scc)):
            if len(path) >= target_depth or node in visited:
                return node == start and len(path) > 1
            
            visited.add(node)
            path.append(node)
            
            for edge in self.relationship_graph.get(node, []):
                if edge.target in scc:
                    predicates.append(edge.predicate)
                    if dfs_in_scc(edge.target, target_depth):
                        return True
                    predicates.pop()
            
            path.pop()
            visited.remove(node)
            return False
        
        if dfs_in_scc(start):
            return {
                'path': path + [start],
                'predicates': predicates
            }
        
        return None
    
    def _find_paths_between(self, start: str, end: str, max_depth: int) -> List[List[str]]:
        """두 노드 간의 모든 경로 찾기 (최대 깊이 제한)"""
        
        paths = []
        
        def dfs_path(current, target, path, depth):
            if depth >= max_depth:
                return
            
            if current == target and len(path) > 1:
                paths.append(path[:])
                return
            
            if current in path:  # 순환 방지
                return
            
            path.append(current)
            
            for edge in self.relationship_graph.get(current, []):
                dfs_path(edge.target, target, path, depth + 1)
            
            path.pop()
        
        dfs_path(start, end, [], 0)
        return paths
    
    def _get_path_edges(self, path: List[str]) -> List[RelationshipEdge]:
        """경로의 엣지 목록 반환"""
        
        edges = []
        for i in range(len(path) - 1):
            source, target = path[i], path[i + 1]
            for edge in self.relationship_graph.get(source, []):
                if edge.target == target:
                    edges.append(edge)
                    break
        return edges
    
    def _assess_self_reference_severity(self, predicate: str) -> str:
        """자기 참조의 심각도 평가"""
        
        if predicate in self.allowed_self_references:
            return "info"
        elif predicate in ["parentOf", "childOf", "manages", "partOf"]:
            return "warning"
        else:
            return "critical"
    
    def _assess_direct_cycle_severity(self, edge1: RelationshipEdge, edge2: RelationshipEdge) -> str:
        """직접 순환의 심각도 평가"""
        
        # 양방향 관계인 경우 허용
        if (edge1.predicate, edge2.predicate) in self.allowed_cycle_patterns:
            return "info"
        elif edge1.is_bidirectional and edge2.is_bidirectional:
            return "warning"
        else:
            return "critical"
    
    def _assess_cycle_severity(self, path: List[str], predicates: List[str]) -> str:
        """순환의 심각도 평가"""
        
        # 길이가 길수록 덜 심각
        if len(path) > 5:
            return "info"
        elif len(path) > 3:
            return "warning"
        else:
            return "critical"
    
    def _can_break_cycle(self, predicates: List[str]) -> bool:
        """순환을 끊을 수 있는지 판별"""
        
        # 모든 predicate가 허용된 패턴이면 끊을 수 없음
        return not all(pred in self.allowed_self_references for pred in predicates)
    
    def _get_inverse_cardinality(self, cardinality: str) -> str:
        """카디널리티의 역관계 반환"""
        
        inverse_map = {
            "1:1": "1:1", "1:n": "n:1", "n:1": "1:n", "n:n": "n:n",
            "one": "many", "many": "one"
        }
        return inverse_map.get(cardinality, cardinality)
    
    def _deduplicate_cycles(self, cycles: List[CycleInfo]) -> List[CycleInfo]:
        """중복 순환 제거"""
        
        unique_cycles = []
        seen_cycles = set()
        
        for cycle in cycles:
            # 경로를 정규화하여 중복 체크
            normalized_path = tuple(sorted(cycle.path))
            if normalized_path not in seen_cycles:
                seen_cycles.add(normalized_path)
                unique_cycles.append(cycle)
        
        return unique_cycles
    
    def _sort_cycles_by_severity(self, cycles: List[CycleInfo]) -> List[CycleInfo]:
        """심각도별로 순환 정렬"""
        
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        
        return sorted(cycles, key=lambda c: (
            severity_order.get(c.severity, 3),
            c.length,
            len(c.path)
        ))
    
    def suggest_cycle_resolution(self, cycle: CycleInfo) -> List[str]:
        """순환 해결 방안 제안"""
        
        suggestions = []
        
        if cycle.cycle_type == CycleType.SELF_REFERENCE:
            if cycle.predicates[0] not in self.allowed_self_references:
                suggestions.append(f"Consider removing self-reference '{cycle.predicates[0]}'")
            else:
                suggestions.append(f"Self-reference '{cycle.predicates[0]}' is generally acceptable")
        
        elif cycle.cycle_type == CycleType.DIRECT_CYCLE:
            suggestions.append("Consider making one relationship unidirectional")
            suggestions.append("Add intermediate entity to break direct cycle")
            suggestions.append("Use weak reference for one direction")
        
        else:
            suggestions.append("Identify the least critical relationship in the cycle")
            suggestions.append("Consider hierarchical organization")
            suggestions.append("Use composition instead of association")
            suggestions.append("Introduce mediator entity")
        
        return suggestions
    
    def get_cycle_analysis_report(self, cycles: List[CycleInfo]) -> Dict[str, Any]:
        """순환 분석 보고서 생성"""
        
        report = {
            "total_cycles": len(cycles),
            "critical_cycles": len([c for c in cycles if c.severity == "critical"]),
            "warning_cycles": len([c for c in cycles if c.severity == "warning"]),
            "info_cycles": len([c for c in cycles if c.severity == "info"]),
            "cycle_types": {
                cycle_type.value: len([c for c in cycles if c.cycle_type == cycle_type])
                for cycle_type in CycleType
            },
            "average_cycle_length": sum(c.length for c in cycles) / len(cycles) if cycles else 0,
            "max_cycle_length": max((c.length for c in cycles), default=0),
            "breakable_cycles": len([c for c in cycles if c.can_break]),
            "recommendations": self._generate_recommendations(cycles)
        }
        
        return report
    
    def _generate_recommendations(self, cycles: List[CycleInfo]) -> List[str]:
        """전체 권장사항 생성"""
        
        recommendations = []
        
        critical_count = len([c for c in cycles if c.severity == "critical"])
        if critical_count > 0:
            recommendations.append(f"Address {critical_count} critical cycles immediately")
        
        complex_cycles = [c for c in cycles if c.cycle_type == CycleType.COMPLEX_CYCLE]
        if complex_cycles:
            recommendations.append("Review complex cycles for architectural simplification")
        
        long_cycles = [c for c in cycles if c.length > 5]
        if long_cycles:
            recommendations.append("Consider breaking long relationship chains")
        
        if len(cycles) > 10:
            recommendations.append("High number of cycles detected - consider architectural review")
        
        return recommendations