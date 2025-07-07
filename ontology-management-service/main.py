"""Refactored main entry point using dependency injection"""

import uvicorn
from bootstrap.app import create_app
from bootstrap.config import get_config

app = create_app()

if __name__ == "__main__":
    config = get_config()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=config.service.debug,
        log_level=config.service.log_level.lower()
    )