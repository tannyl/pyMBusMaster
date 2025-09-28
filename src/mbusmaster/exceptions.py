"""M-Bus exception classes."""

from __future__ import annotations


class MBusError(Exception):
    """Base exception for all M-Bus errors."""


class MBusConnectionError(MBusError):
    """Connection-related errors."""


class MBusTimeoutError(MBusError):
    """Timeout waiting for data or response."""


class MBusProtocolError(MBusError):
    """Protocol-level errors (frame validation, checksums, etc)."""
