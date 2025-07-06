"""
Commit Hook Pipeline - Central coordination of validators and sinks
"""
import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base import BaseValidator, BaseSink, BaseHook, DiffContext, CommitMeta, ValidationError
from .validators import RuleValidator, TamperValidator, SchemaValidator, PIIValidator
from .sinks import NATSSink, AuditSink, WebhookSink, MetricsSink

logger = logging.getLogger(__name__)


class CommitHookPipeline:
    """
    Central pipeline for processing TerminusDB commits.
    Runs validators first (sync), then sinks (async).
    """
    
    # Class-level registries
    _validators: List[BaseValidator] = []
    _sinks: List[BaseSink] = []
    _pre_hooks: List[BaseHook] = []
    _post_hooks: List[BaseHook] = []
    _async_hooks: List[BaseHook] = []
    
    # Configuration
    _async_validation = os.getenv("VALIDATION_ASYNC", "false").lower() == "true"
    _max_diff_size = int(os.getenv("MAX_DIFF_SIZE_MB", "10")) * 1024 * 1024
    _initialized = False
    
    @classmethod
    async def initialize(cls):
        """Initialize all pipeline components"""
        if cls._initialized:
            return
        
        logger.info("Initializing CommitHookPipeline")
        
        # Default validators
        cls._validators = [
            TamperValidator(),
            SchemaValidator(),
            PIIValidator(),
            # RuleValidator() - Disabled until ValidationService is fixed
        ]
        
        # Default sinks
        cls._sinks = [
            NATSSink(),
            AuditSink(),
            MetricsSink(),
            WebhookSink()
        ]
        
        # Initialize all components
        all_components = cls._validators + cls._sinks + cls._pre_hooks + cls._post_hooks + cls._async_hooks
        
        for component in all_components:
            if component.enabled:
                try:
                    await component.initialize()
                    logger.info(f"Initialized {component.name}")
                except Exception as e:
                    logger.error(f"Failed to initialize {component.name}: {e}")
        
        cls._initialized = True
    
    @classmethod
    async def run(cls, meta: CommitMeta, diff: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main pipeline execution.
        Returns a summary of what was executed.
        """
        if not cls._initialized:
            await cls.initialize()
        
        # Build context
        context = cls._build_context(meta, diff)
        
        # Check diff size
        if cls._should_skip_validation(context):
            logger.warning(f"Skipping validation for large diff: {len(str(diff))} bytes")
            # Still run sinks for large diffs
            await cls._run_sinks_async(context)
            return {"status": "skipped", "reason": "diff_too_large"}
        
        # Run pre-commit hooks
        try:
            await cls._run_hooks(cls._pre_hooks, context, "pre-commit")
        except Exception as e:
            logger.error(f"Pre-commit hook failed: {e}")
            raise
        
        # Run validators
        validation_errors = []
        if cls._async_validation:
            # Fire and forget validation
            asyncio.create_task(cls._run_validators_async(context))
        else:
            # Synchronous validation (blocks commit on failure)
            validation_errors = await cls._run_validators(context)
            if validation_errors:
                raise ValidationError(
                    f"Validation failed with {len(validation_errors)} errors",
                    errors=validation_errors
                )
        
        # Run post-commit hooks
        try:
            await cls._run_hooks(cls._post_hooks, context, "post-commit")
        except Exception as e:
            logger.error(f"Post-commit hook failed: {e}")
            # Don't fail the commit for post-hooks
        
        # Run sinks asynchronously (never block commit)
        asyncio.create_task(cls._run_sinks_async(context))
        
        # Run async hooks
        asyncio.create_task(cls._run_hooks(cls._async_hooks, context, "async"))
        
        return {
            "status": "success",
            "validators_run": len([v for v in cls._validators if v.enabled]),
            "sinks_run": len([s for s in cls._sinks if s.enabled]),
            "validation_errors": validation_errors
        }
    
    @classmethod
    def _build_context(cls, meta: CommitMeta, diff: Dict[str, Any]) -> DiffContext:
        """Build diff context from commit metadata and diff"""
        # Extract before/after if available
        before = diff.get("before")
        after = diff.get("after")
        
        # Extract affected types and IDs
        affected_types = set()
        affected_ids = set()
        
        def extract_info(obj):
            if isinstance(obj, dict):
                if "@type" in obj:
                    affected_types.add(obj["@type"])
                if "@id" in obj:
                    affected_ids.add(obj["@id"])
                for value in obj.values():
                    extract_info(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_info(item)
        
        extract_info(diff)
        
        return DiffContext(
            meta=meta,
            diff=diff,
            before=before,
            after=after,
            affected_types=list(affected_types),
            affected_ids=list(affected_ids)
        )
    
    @classmethod
    def _should_skip_validation(cls, context: DiffContext) -> bool:
        """Check if validation should be skipped"""
        diff_size = len(str(context.diff))
        return diff_size > cls._max_diff_size
    
    @classmethod
    async def _run_validators(cls, context: DiffContext) -> List[Dict[str, Any]]:
        """Run all validators synchronously"""
        errors = []
        
        for validator in cls._validators:
            if not validator.enabled:
                continue
            
            try:
                await validator.validate(context)
                logger.debug(f"Validator {validator.name} passed")
            except ValidationError as e:
                logger.warning(f"Validator {validator.name} failed: {e}")
                errors.extend(e.errors or [{"validator": validator.name, "error": str(e)}])
            except Exception as e:
                logger.error(f"Validator {validator.name} error: {e}")
                if os.getenv("STRICT_VALIDATION", "false").lower() == "true":
                    errors.append({"validator": validator.name, "error": str(e)})
        
        return errors
    
    @classmethod
    async def _run_validators_async(cls, context: DiffContext):
        """Run validators asynchronously (fire and forget)"""
        try:
            errors = await cls._run_validators(context)
            if errors:
                logger.warning(f"Async validation found {len(errors)} errors (non-blocking)")
                # Could send to monitoring system here
        except Exception as e:
            logger.error(f"Async validation failed: {e}")
    
    @classmethod
    async def _run_sinks_async(cls, context: DiffContext):
        """Run all sinks asynchronously"""
        tasks = []
        
        for sink in cls._sinks:
            if not sink.enabled:
                continue
            
            async def run_sink(s):
                try:
                    await s.publish(context)
                    logger.debug(f"Sink {s.name} completed")
                except Exception as e:
                    logger.error(f"Sink {s.name} failed: {e}")
            
            tasks.append(run_sink(sink))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    @classmethod
    async def _run_hooks(cls, hooks: List[BaseHook], context: DiffContext, phase: str):
        """Run hooks for a specific phase"""
        for hook in hooks:
            if not hook.enabled or hook.phase != phase:
                continue
            
            try:
                await hook.execute(context)
                logger.debug(f"Hook {hook.name} completed")
            except Exception as e:
                logger.error(f"Hook {hook.name} failed: {e}")
                if phase == "pre-commit":
                    raise
    
    @classmethod
    def register_validator(cls, validator: BaseValidator):
        """Register a custom validator"""
        cls._validators.append(validator)
        logger.info(f"Registered validator: {validator.name}")
    
    @classmethod
    def register_sink(cls, sink: BaseSink):
        """Register a custom sink"""
        cls._sinks.append(sink)
        logger.info(f"Registered sink: {sink.name}")
    
    @classmethod
    def register_hook(cls, hook: BaseHook):
        """Register a custom hook"""
        if hook.phase == "pre-commit":
            cls._pre_hooks.append(hook)
        elif hook.phase == "post-commit":
            cls._post_hooks.append(hook)
        elif hook.phase == "async":
            cls._async_hooks.append(hook)
        logger.info(f"Registered {hook.phase} hook: {hook.name}")
    
    @classmethod
    async def cleanup(cls):
        """Cleanup all pipeline components"""
        logger.info("Cleaning up CommitHookPipeline")
        
        all_components = cls._validators + cls._sinks + cls._pre_hooks + cls._post_hooks + cls._async_hooks
        
        for component in all_components:
            try:
                await component.cleanup()
            except Exception as e:
                logger.error(f"Failed to cleanup {component.name}: {e}")
        
        cls._initialized = False