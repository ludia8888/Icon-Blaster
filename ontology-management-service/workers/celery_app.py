"""
Celery Application Configuration
Handles asynchronous task processing with Redis as message broker
"""
import os
from celery import Celery
from celery.signals import task_prerun, task_postrun, task_failure, task_retry
from kombu import Exchange, Queue
from datetime import timedelta
import structlog

from bootstrap.config import get_config
from common_logging.setup import get_logger

logger = get_logger(__name__)

# Get configuration
config = get_config()

# Initialize Celery app
app = Celery('ontology_management_service')

# Redis connection settings
REDIS_URL = os.getenv('REDIS_URL', f'redis://{config.redis.host}:{config.redis.port}/{config.redis.db}')

# Celery configuration
app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    
    # Task execution settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Task routing
    task_default_queue='default',
    task_default_exchange='tasks',
    task_default_exchange_type='topic',
    task_default_routing_key='task.default',
    
    # Queue definitions
    task_queues=(
        Queue('default', Exchange('tasks'), routing_key='task.#'),
        Queue('merge', Exchange('tasks'), routing_key='task.merge.#', priority=10),
        Queue('validation', Exchange('tasks'), routing_key='task.validation.#', priority=5),
        Queue('import', Exchange('tasks'), routing_key='task.import.#', priority=3),
        Queue('low_priority', Exchange('tasks'), routing_key='task.low.#', priority=1),
    ),
    
    # Task routing rules
    task_routes={
        'workers.tasks.merge.*': {'queue': 'merge'},
        'workers.tasks.validation.*': {'queue': 'validation'},
        'workers.tasks.import.*': {'queue': 'import'},
    },
    
    # Retry configuration
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
    
    # Result backend settings
    result_expires=3600,  # 1 hour
    result_persistent=True,
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    
    # Beat schedule (if needed for periodic tasks)
    beat_schedule={
        'cleanup-expired-jobs': {
            'task': 'workers.tasks.maintenance.cleanup_expired_jobs',
            'schedule': timedelta(hours=1),
        },
        'check-stuck-jobs': {
            'task': 'workers.tasks.maintenance.check_stuck_jobs',
            'schedule': timedelta(minutes=15),
        },
    },
    
    # Task time limits
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3000,  # 50 minutes soft limit
    
    # Dead letter queue settings
    task_dead_letter_queue='dlq',
    task_dead_letter_routing_key='dlq',
)

# Import task modules
app.autodiscover_tasks(['workers.tasks'])

# Signal handlers for monitoring
@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kw):
    """Log task start"""
    logger.info(
        "Task starting",
        task_id=task_id,
        task_name=task.name,
        args=args,
        kwargs=kwargs
    )

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, 
                        retval=None, state=None, **kw):
    """Log task completion"""
    logger.info(
        "Task completed",
        task_id=task_id,
        task_name=task.name,
        state=state,
        retval=retval
    )

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, args=None, 
                        kwargs=None, traceback=None, einfo=None, **kw):
    """Log task failure"""
    logger.error(
        "Task failed",
        task_id=task_id,
        task_name=sender.name,
        exception=str(exception),
        args=args,
        kwargs=kwargs,
        exc_info=einfo
    )

@task_retry.connect
def task_retry_handler(sender=None, task_id=None, reason=None, **kw):
    """Log task retry"""
    logger.warning(
        "Task retrying",
        task_id=task_id,
        task_name=sender.name,
        reason=str(reason)
    )

if __name__ == '__main__':
    app.start()