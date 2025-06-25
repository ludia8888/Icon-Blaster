# Core branch module exports
from .service import BranchService
from .diff_engine import DiffEngine
from .conflict_resolver import ConflictResolver

__all__ = ["BranchService", "DiffEngine", "ConflictResolver"]