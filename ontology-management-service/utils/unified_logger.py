"""
Unified Logger Factory
Centralizes logger initialization and configuration
"""

import logging
import os
from typing import Optional, Dict, Any
from enum import Enum
import json
from datetime import datetime


class LogLevel(Enum):
    """Standard log levels"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class LoggerConfig:
    """Configuration for unified logger"""
    
    def __init__(
        self,
        level: LogLevel = LogLevel.INFO,
        format: str = None,
        enable_json: bool = False,
        enable_file: bool = False,
        file_path: str = "logs/app.log",
        enable_rotation: bool = True,
        max_bytes: int = 10485760,  # 10MB
        backup_count: int = 5,
        enable_context: bool = True,
        context_fields: Optional[Dict[str, Any]] = None
    ):
        self.level = level
        self.format = format or self._get_default_format(enable_json)
        self.enable_json = enable_json
        self.enable_file = enable_file
        self.file_path = file_path
        self.enable_rotation = enable_rotation
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.enable_context = enable_context
        self.context_fields = context_fields or {}
    
    def _get_default_format(self, json_format: bool) -> str:
        """Get default format based on output type"""
        if json_format:
            return ""  # JSON formatter handles this
        else:
            return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    @classmethod
    def from_env(cls) -> "LoggerConfig":
        """Create config from environment variables"""
        level_str = os.getenv("LOG_LEVEL", "INFO").upper()
        level = LogLevel[level_str] if level_str in LogLevel.__members__ else LogLevel.INFO
        
        return cls(
            level=level,
            enable_json=os.getenv("LOG_JSON", "false").lower() == "true",
            enable_file=os.getenv("LOG_TO_FILE", "false").lower() == "true",
            file_path=os.getenv("LOG_FILE_PATH", "logs/app.log"),
            enable_rotation=os.getenv("LOG_ROTATION", "true").lower() == "true",
            enable_context=os.getenv("LOG_CONTEXT", "true").lower() == "true"
        )


class JSONFormatter(logging.Formatter):
    """JSON log formatter"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", 
                          "funcName", "levelname", "levelno", "lineno", 
                          "module", "msecs", "pathname", "process", 
                          "processName", "relativeCreated", "thread", 
                          "threadName", "exc_info", "exc_text", "stack_info"]:
                log_obj[key] = value
        
        return json.dumps(log_obj)


class ContextFilter(logging.Filter):
    """Add context fields to log records"""
    
    def __init__(self, context_fields: Dict[str, Any]):
        super().__init__()
        self.context_fields = context_fields
    
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in self.context_fields.items():
            setattr(record, key, value)
        return True


class UnifiedLoggerFactory:
    """Factory for creating configured loggers"""
    
    _loggers: Dict[str, logging.Logger] = {}
    _config: Optional[LoggerConfig] = None
    _initialized: bool = False
    
    @classmethod
    def initialize(cls, config: Optional[LoggerConfig] = None):
        """Initialize the logger factory with configuration"""
        if cls._initialized:
            return
        
        cls._config = config or LoggerConfig.from_env()
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(cls._config.level.value)
        
        # Remove existing handlers
        root_logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(cls._config.level.value)
        
        if cls._config.enable_json:
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(logging.Formatter(cls._config.format))
        
        root_logger.addHandler(console_handler)
        
        # File handler
        if cls._config.enable_file:
            cls._setup_file_handler(root_logger)
        
        # Context filter
        if cls._config.enable_context and cls._config.context_fields:
            context_filter = ContextFilter(cls._config.context_fields)
            root_logger.addFilter(context_filter)
        
        cls._initialized = True
    
    @classmethod
    def _setup_file_handler(cls, logger: logging.Logger):
        """Setup file handler with optional rotation"""
        # Create log directory if needed
        log_dir = os.path.dirname(cls._config.file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        if cls._config.enable_rotation:
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                cls._config.file_path,
                maxBytes=cls._config.max_bytes,
                backupCount=cls._config.backup_count
            )
        else:
            file_handler = logging.FileHandler(cls._config.file_path)
        
        file_handler.setLevel(cls._config.level.value)
        
        if cls._config.enable_json:
            file_handler.setFormatter(JSONFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(cls._config.format))
        
        logger.addHandler(file_handler)
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """Get or create a logger with the given name"""
        # Initialize if not already done
        if not cls._initialized:
            cls.initialize()
        
        # Return cached logger if exists
        if name in cls._loggers:
            return cls._loggers[name]
        
        # Create new logger
        logger = logging.getLogger(name)
        cls._loggers[name] = logger
        
        return logger
    
    @classmethod
    def add_context(cls, **kwargs):
        """Add context fields to all loggers"""
        if not cls._config:
            cls.initialize()
        
        cls._config.context_fields.update(kwargs)
        
        # Update existing loggers
        context_filter = ContextFilter(cls._config.context_fields)
        for logger in cls._loggers.values():
            # Remove old context filters
            logger.filters = [f for f in logger.filters if not isinstance(f, ContextFilter)]
            # Add new context filter
            logger.addFilter(context_filter)
    
    @classmethod
    def set_level(cls, level: LogLevel):
        """Change log level for all loggers"""
        if not cls._config:
            cls.initialize()
        
        cls._config.level = level
        
        # Update root logger
        logging.getLogger().setLevel(level.value)
        
        # Update all handlers
        for handler in logging.getLogger().handlers:
            handler.setLevel(level.value)
    
    @classmethod
    def get_config(cls) -> LoggerConfig:
        """Get current configuration"""
        if not cls._config:
            cls.initialize()
        return cls._config


# Convenience function for backward compatibility
def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance
    
    This is the primary function to use throughout the codebase:
    
    from utils.unified_logger import get_logger
    logger = get_logger(__name__)
    """
    return UnifiedLoggerFactory.get_logger(name)


# Additional convenience functions
def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    log_file: Optional[str] = None,
    **context_fields
):
    """
    Quick setup for logging configuration
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Enable JSON formatting
        log_file: Optional log file path
        **context_fields: Additional context fields to add to all logs
    """
    config = LoggerConfig(
        level=LogLevel[level.upper()],
        enable_json=json_format,
        enable_file=log_file is not None,
        file_path=log_file or "logs/app.log",
        context_fields=context_fields
    )
    
    UnifiedLoggerFactory.initialize(config)


def add_log_context(**kwargs):
    """Add context fields to all future log messages"""
    UnifiedLoggerFactory.add_context(**kwargs)


def set_log_level(level: str):
    """Change the log level dynamically"""
    UnifiedLoggerFactory.set_level(LogLevel[level.upper()])


# Structured logging helpers
class StructuredLogger:
    """Wrapper for structured logging with consistent fields"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def debug(self, message: str, **fields):
        self.logger.debug(message, extra=fields)
    
    def info(self, message: str, **fields):
        self.logger.info(message, extra=fields)
    
    def warning(self, message: str, **fields):
        self.logger.warning(message, extra=fields)
    
    def error(self, message: str, error: Optional[Exception] = None, **fields):
        if error:
            fields["error_type"] = type(error).__name__
            fields["error_message"] = str(error)
        self.logger.error(message, extra=fields, exc_info=error)
    
    def critical(self, message: str, **fields):
        self.logger.critical(message, extra=fields)
    
    def audit(self, action: str, user: str, resource: str, **fields):
        """Special method for audit logging"""
        self.logger.info(
            f"AUDIT: {action}",
            extra={
                "audit": True,
                "action": action,
                "user": user,
                "resource": resource,
                **fields
            }
        )
    
    def performance(self, operation: str, duration_ms: float, **fields):
        """Special method for performance logging"""
        self.logger.info(
            f"PERFORMANCE: {operation}",
            extra={
                "performance": True,
                "operation": operation,
                "duration_ms": duration_ms,
                **fields
            }
        )


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance"""
    return StructuredLogger(get_logger(name))


# Export main components
__all__ = [
    "get_logger",
    "get_structured_logger",
    "setup_logging",
    "add_log_context",
    "set_log_level",
    "LogLevel",
    "LoggerConfig",
    "UnifiedLoggerFactory",
    "StructuredLogger"
]