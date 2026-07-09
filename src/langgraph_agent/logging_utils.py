import logging
import os
from datetime import datetime


def configure_logging(level: str | None = None) -> None:
    """Configure root logging"""
    level = level or os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )

def log_node(name: str, event: str, **kwargs):
    """Log node entry/exit with timestamp and state values."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"[{ts}] [NODE:{name}] [{event}] {details}")

def log_router(name: str, decision: str, **kwargs):
    """Log routing decisions with timestamp and relevant state values."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"[{ts}] [ROUTER:{name}] {details} -> {decision}")


logger = logging.getLogger("sra_agent")

