"""
Validation Service Core Interfaces
REQ-OMS-F3: Schema validation and migration support
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# REQ-OMS-F3: Severity levels for breaking changes
class Severity(str, Enum):
    """Breaking change severity levels"""
    CRITICAL = "critical"  # Requires immediate attention, data loss risk
    HIGH = "high"         # Significant impact, migration required
    MEDIUM = "medium"     # Moderate impact, can be handled gracefully
    LOW = "low"          # Minor impact, backwards compatible


# REQ-OMS-F3: Migration strategies
class MigrationStrategy(str, Enum):
    """Pre-defined migration strategies"""
    COPY_THEN_DROP = "copy_then_drop"
    BACKFILL_NULLABLE = "backfill_nullable"
    SET_DEFAULT_VALUES = "set_default_values"
    MAKE_NULLABLE_FIRST = "make_nullable_first"
    TYPE_CONVERSION = "type_conversion"
    NO_ACTION = "no_action"
    CUSTOM = "custom"


@dataclass
class BreakingChange:
    """
    REQ-OMS-F3: Breaking change detection result

    Represents a detected breaking change with all necessary information
    for impact analysis and migration planning.
    """
    rule_id: str
    severity: Severity
    object_type: str
    field_name: Optional[str]
    description: str
    old_value: Any
    new_value: Any
    impact: Dict[str, Any]
    suggested_strategies: List[MigrationStrategy]
    detected_at: datetime = None

    def __post_init__(self):
        if self.detected_at is None:
            self.detected_at = datetime.utcnow()


@dataclass
class ValidationResult:
    """
    REQ-OMS-F3: Complete validation result

    Contains all breaking changes found and migration recommendations.
    """
    branch: str
    request_id: str
    breaking_changes: List[BreakingChange]
    is_valid: bool
    can_auto_migrate: bool
    requires_downtime: bool
    estimated_duration: str
    validation_duration_ms: int
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

    @property
    def has_critical_changes(self) -> bool:
        """Check if any critical breaking changes exist"""
        return any(bc.severity == Severity.CRITICAL for bc in self.breaking_changes)


class BreakingChangeRule(ABC):
    """
    REQ-OMS-F3: Base interface for breaking change detection rules

    All validation rules must implement this interface to ensure
    consistent behavior and integration with the validation framework.
    """

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique identifier for this rule"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this rule checks"""
        pass

    @abstractmethod
    def check(self, old_schema: Dict, new_schema: Dict) -> List[BreakingChange]:
        """
        REQ-OMS-F3-AC1: Check for breaking changes

        Args:
            old_schema: Previous schema version
            new_schema: New schema version

        Returns:
            List of detected breaking changes
        """
        pass

    @abstractmethod
    async def estimate_impact(self, breaking_change: BreakingChange,
                            data_source: Any) -> Dict[str, Any]:
        """
        REQ-OMS-F3: Estimate impact on actual data

        Args:
            breaking_change: The detected breaking change
            data_source: Connection to data source for impact analysis

        Returns:
            Detailed impact analysis including affected records
        """
        pass


@dataclass
class MigrationStep:
    """
    REQ-OMS-F3-AC2: Individual migration step
    """
    order: int
    action: str
    description: str
    target: str
    parameters: Dict[str, Any]
    estimated_duration: str
    can_rollback: bool = True
    requires_verification: bool = True


@dataclass
class MigrationPlan:
    """
    REQ-OMS-F3-AC2: Complete migration plan

    Groups migration steps by phase and provides execution order.
    """
    plan_id: str
    breaking_changes: List[BreakingChange]
    phases: List[Dict[str, Any]]
    total_steps: int
    estimated_total_duration: str
    requires_downtime: bool
    rollback_strategy: str
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def add_phase(self, name: str, steps: List[MigrationStep]):
        """Add a migration phase with steps"""
        self.phases.append({
            "name": name,
            "steps": steps,
            "order": len(self.phases) + 1
        })
        self.total_steps = sum(len(p["steps"]) for p in self.phases)


class ValidationService(ABC):
    """
    REQ-OMS-F3: Main validation service interface
    """

    @abstractmethod
    async def validate_schema_change(self, branch: str, old_version: str,
                                   new_version: str) -> ValidationResult:
        """
        REQ-OMS-F3: Validate schema changes for breaking changes

        Must complete within 30 seconds for 90% of cases.
        """
        pass

    @abstractmethod
    async def generate_migration_plan(self, validation_result: ValidationResult) -> MigrationPlan:
        """
        REQ-OMS-F3-AC2: Generate migration plan for breaking changes
        """
        pass

    @abstractmethod
    def register_custom_rule(self, rule: BreakingChangeRule) -> None:
        """
        REQ-OMS-F3: Register custom validation rules
        """
        pass
