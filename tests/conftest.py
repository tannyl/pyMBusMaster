"""Shared test fixtures for pyMBusMaster tests."""

from __future__ import annotations

import asyncio
import os
import pty
import threading
import time
from collections.abc import AsyncGenerator, Generator
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


# Integration test fixtures

class IntegrationMockServer:
    """Base class for integration test mock servers."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self._running = True

    async def start(self) -> None:
        """Start the mock server."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        if self.port == 0:
            self.port = self.server.sockets[0].getsockname()[1]
        self._running = True

    async def stop(self) -> None:
        """Stop the mock server."""
        self._running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle client connection - to be overridden by subclasses."""
        try:
            while self._running:
                data = await reader.read(1024)
                if not data:
                    break

                response = self._generate_response(data)
                if response:
                    writer.write(response)
                    await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _generate_response(self, request: bytes) -> bytes:
        """Generate M-Bus response - to be overridden by subclasses."""
        if len(request) == 5 and request[0] == 0x10:
            return b"\xE5"  # ACK for SND_NKE
        return b""


class VirtualSerialPort:
    """Virtual serial port using pty for integration testing."""

    def __init__(self) -> None:
        self.master_fd: int = -1
        self.slave_fd: int = -1
        self.slave_name: str = ""
        self.server_thread: threading.Thread | None = None
        self.running = False

    def start(self) -> None:
        """Start the virtual serial port."""
        if os.name == "nt":
            pytest.skip("pty not available on Windows")

        self.master_fd, self.slave_fd = pty.openpty()
        self.slave_name = os.ttyname(self.slave_fd)
        self.running = True

        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()

    def stop(self) -> None:
        """Stop the virtual serial port."""
        self.running = False
        if self.server_thread:
            self.server_thread.join(timeout=1.0)

        if self.master_fd >= 0:
            os.close(self.master_fd)
        if self.slave_fd >= 0:
            os.close(self.slave_fd)

    def _server_loop(self) -> None:
        """Server loop handling serial communication."""
        try:
            while self.running:
                import select
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if not ready:
                    continue

                try:
                    data = os.read(self.master_fd, 1024)
                    if not data:
                        continue

                    response = self._generate_response(data)
                    if response and self.running:
                        os.write(self.master_fd, response)

                except (OSError, BlockingIOError):
                    if self.running:
                        time.sleep(0.01)
                    continue
        except Exception:
            pass

    def _generate_response(self, request: bytes) -> bytes:
        """Generate M-Bus response."""
        if len(request) == 5 and request[0] == 0x10:
            return b"\xE5"  # ACK for SND_NKE
        return b""


@pytest.fixture
async def integration_mock_server() -> AsyncGenerator[IntegrationMockServer]:
    """Create basic integration mock server."""
    server = IntegrationMockServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def virtual_serial_port() -> Generator[VirtualSerialPort]:
    """Create virtual serial port for testing."""
    port = VirtualSerialPort()
    port.start()
    yield port
    port.stop()


@pytest.fixture
def extended_mbus_frames() -> dict[str, bytes]:
    """Extended M-Bus frame data for integration testing."""
    return {
        'snd_nke': bytes([0x10, 0x40, 0x05, 0x45, 0x16]),  # SND_NKE to address 5
        'req_ud2': bytes([0x10, 0x5B, 0x05, 0x60, 0x16]),  # REQ_UD2 to address 5
        'ack': b'\xE5',  # ACK response
        'nack': b'\x00',  # NACK response
        'short_data_frame': bytes([
            0x68, 0x03, 0x03, 0x68,  # Start, L, L, Start
            0x08, 0x05,  # C-Field, A-Field
            0x72,  # Sample data
            0x7F,  # Checksum
            0x16   # Stop
        ]),
        'long_data_frame': bytes([
            0x68, 0x1F, 0x1F, 0x68,  # Start, L, L, Start
            0x08, 0x05,  # C-Field, A-Field
            0x72, 0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE,  # Sample data
            0x02, 0xFD, 0x1B, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0xAB,  # Checksum
            0x16   # Stop
        ]),
        'control_frame': bytes([
            0x68, 0x05, 0x05, 0x68,  # Start, L, L, Start
            0x08, 0x05,  # C-Field, A-Field
            0x72, 0x12, 0x34,  # Sample data
            0xC0,  # Checksum
            0x16   # Stop
        ])
    }


@pytest.fixture
def timing_precision_ms() -> float:
    """Timing precision tolerance for integration tests (in milliseconds)."""
    return 50.0  # 50ms tolerance for timing tests


# Test markers for different test types
def pytest_configure(config: Any) -> None:
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test (fast, uses mocks)"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test (slower, uses real I/O)"
    )
    config.addinivalue_line(
        "markers", "timing: mark test as timing-sensitive (may be flaky on slow systems)"
    )
    config.addinivalue_line(
        "markers", "serial: mark test as requiring serial port simulation"
    )
    config.addinivalue_line(
        "markers", "network: mark test as requiring network simulation"
    )
