"""
Health dependency graph management
"""
from typing import Dict, Set, List, Optional
from collections import defaultdict


class DependencyGraph:
    """Manage component health dependencies"""
    
    def __init__(self):
        # component -> set of components it depends on
        self._dependencies: Dict[str, Set[str]] = defaultdict(set)
        # component -> set of components that depend on it
        self._dependents: Dict[str, Set[str]] = defaultdict(set)
    
    def add_dependency(self, component: str, depends_on: str):
        """Add a dependency relationship"""
        self._dependencies[component].add(depends_on)
        self._dependents[depends_on].add(component)
    
    def remove_dependency(self, component: str, depends_on: str):
        """Remove a dependency relationship"""
        self._dependencies[component].discard(depends_on)
        self._dependents[depends_on].discard(component)
    
    def get_dependencies(self, component: str) -> List[str]:
        """Get direct dependencies of a component"""
        return list(self._dependencies.get(component, set()))
    
    def get_dependents(self, component: str) -> List[str]:
        """Get components that depend on this component"""
        return list(self._dependents.get(component, set()))
    
    def get_all_dependencies(self, component: str) -> Set[str]:
        """Get all dependencies (including transitive) of a component"""
        visited = set()
        to_visit = [component]
        all_deps = set()
        
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            
            visited.add(current)
            deps = self._dependencies.get(current, set())
            all_deps.update(deps)
            to_visit.extend(deps)
        
        return all_deps
    
    def get_all_dependents(self, component: str) -> Set[str]:
        """Get all dependents (including transitive) of a component"""
        visited = set()
        to_visit = [component]
        all_deps = set()
        
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            
            visited.add(current)
            deps = self._dependents.get(current, set())
            all_deps.update(deps)
            to_visit.extend(deps)
        
        return all_deps
    
    def has_cycle(self) -> bool:
        """Check if dependency graph has cycles"""
        visited = set()
        rec_stack = set()
        
        def visit(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in self._dependencies.get(node, set()):
                if neighbor not in visited:
                    if visit(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in self._dependencies:
            if node not in visited:
                if visit(node):
                    return True
        
        return False
    
    def topological_sort(self) -> Optional[List[str]]:
        """Get topological ordering of components"""
        if self.has_cycle():
            return None
        
        in_degree = defaultdict(int)
        all_nodes = set(self._dependencies.keys()) | set(self._dependents.keys())
        
        for node in all_nodes:
            for dep in self._dependencies.get(node, set()):
                in_degree[dep] += 1
        
        queue = [node for node in all_nodes if in_degree[node] == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            for dependent in self._dependents.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        return result if len(result) == len(all_nodes) else None