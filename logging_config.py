"""
Structured JSON logging for Railway.

Provides JSON-formatted logs for better observability in Railway's log aggregator.
Includes user_id, chat_id, and other context fields when available.

Usage:
    from logging_config import setup_logging, get_logger
    
    setup_logging()  # Call once at startup
    logger = get_logger(__name__)
    logger.info("Order created", extra={"user_id": 123, "order_id": 456})
"""
import logging
import json
import sys
import os
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for Railway."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add context fields if present
        for key in ("user_id", "chat_id", "order_id", "request_id", "service"):
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        
        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(json_format: bool | None = None, level: int = logging.INFO):
    """
    Configure root logger.
    
    Args:
        json_format: Use JSON format (default: auto-detect based on RAILWAY_ENVIRONMENT)
        level: Logging level
    """
    # Auto-detect: use JSON in production (Railway), plain text locally
    if json_format is None:
        json_format = bool(os.getenv("RAILWAY_ENVIRONMENT"))
    
    handler = logging.StreamHandler(sys.stdout)
    
    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ))
    
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    
    # Reduce noise from libraries
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
