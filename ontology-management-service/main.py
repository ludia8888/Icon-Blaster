"""Refactored main entry point using dependency injection"""

import uvicorn
import logging
import sys
from bootstrap.app import create_app
from bootstrap.config import get_config
from common_logging.setup import get_logger

# Configure root logger for detailed debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = get_logger(__name__)
logger.info("Starting OMS application...")

try:
    app = create_app()
    logger.info("Application created successfully")
except Exception as e:
    logger.exception("Failed to create application")
    raise

if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=config.service.debug,
        log_level=config.service.log_level.lower()
    )