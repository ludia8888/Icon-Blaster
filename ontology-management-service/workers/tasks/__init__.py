"""
Worker Tasks Package
Contains all Celery tasks for background processing
"""
from .merge import branch_merge_task

__all__ = ['branch_merge_task']