# Core branch module exports
from .service import BranchService
from .diff_engine import DiffEngine
from .conflict_resolver import ConflictResolver
from .merge_strategies import MergeStrategyImplementor

__all__ = [
    "BranchService",
    "DiffEngine",
    "ConflictResolver",
    "MergeStrategyImplementor"
]