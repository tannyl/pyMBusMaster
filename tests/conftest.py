"""Shared test fixtures for pyMBusMaster tests."""

from __future__ import annotations

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_serial_connection() -> tuple[AsyncMock, AsyncMock]:
    """Create mock reader and writer for serial connections."""
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()

    # Mock common methods
    mock_writer.write = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()

    mock_reader.readexactly = AsyncMock()

    return mock_reader, mock_writer


@pytest.fixture
def mock_open_serial_connection(mock_serial_connection: tuple[AsyncMock, AsyncMock]) -> Any:
    """Mock serial_asyncio_fast.open_serial_connection."""
    mock_reader, mock_writer = mock_serial_connection

    async def mock_open(*_args: Any, **_kwargs: Any) -> tuple[AsyncMock, AsyncMock]:
        return mock_reader, mock_writer

    return mock_open


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop]:
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def sample_mbus_frame() -> dict[str, bytes]:
    """Sample M-Bus frame data for testing."""
    return {
        'snd_nke': bytes([0x10, 0x40, 0x05, 0x45, 0x16]),  # SND_NKE to address 5
        'ack': b'\xE5',  # ACK response
        'long_frame': bytes([
            0x68, 0x65, 0x65, 0x68,  # Start, L, L, Start
            0x08, 0x05,  # C-Field, A-Field
            0x72, 0x35, 0x37, 0x15, 0x90, 0x36, 0x1c, 0xc7,  # Sample data
            0x02, 0xe0, 0x00, 0x00, 0x00, 0x04,
            # ... more data would follow in real frame
            0x16  # Stop
        ])
    }
