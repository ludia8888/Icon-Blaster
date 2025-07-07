"""
Workers Package
Handles background task processing for long-running operations
"""
from .celery_app import app as celery_app

__all__ = ['celery_app']