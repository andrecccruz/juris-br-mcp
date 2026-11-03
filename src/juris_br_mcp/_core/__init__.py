"""Core publico do juris-br-mcp."""

from .config import Settings, settings
from .errors import (
    JuridicoAPIError,
    JuridicoError,
    JuridicoNotFoundError,
    JuridicoSigiloError,
    JuridicoValidationError,
)
from .http import HTTPClient
from .logging import configure_logging, get_logger

__all__ = [
    "HTTPClient",
    "JuridicoAPIError",
    "JuridicoError",
    "JuridicoNotFoundError",
    "JuridicoSigiloError",
    "JuridicoValidationError",
    "Settings",
    "configure_logging",
    "get_logger",
    "settings",
]
