"""Integration tests for MBusTransport TCP connections."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from src.mbusmaster.exceptions import MBusConnectionError
from src.mbusmaster.transport import Transport


class MockMBusServer:
    """Mock M-Bus TCP server for testing."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.response_delay = 0.0
        self.drop_connection_after = 0  # 0 = never drop
        self.connection_count = 0

    async def start(self) -> None:
        """Start the mock server."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        # Get the actual port if we used 0
        if self.port == 0:
            self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop the mock server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    def set_response_delay(self, delay: float) -> None:
        """Set delay before responding to requests."""
        self.response_delay = delay

    def set_connection_drop(self, after_count: int) -> None:
        """Set server to drop connection after N requests."""
        self.drop_connection_after = after_count

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle client connection."""
        self.connection_count += 1
        request_count = 0

        try:
            while True:
                # Read M-Bus frame
                data = await reader.read(1024)
                if not data:
                    break

                request_count += 1

                # Check if we should drop connection
                if (
                    self.drop_connection_after > 0
                    and request_count >= self.drop_connection_after
                ):
                    break

                # Add response delay if configured
                if self.response_delay > 0:
                    await asyncio.sleep(self.response_delay)

                # Respond based on the request
                response = self._generate_response(data)
                if response:
                    writer.write(response)
                    await writer.drain()

        except Exception:
            pass  # Ignore connection errors
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _generate_response(self, request: bytes) -> bytes:
        """Generate appropriate M-Bus response."""
        if len(request) == 5 and request[0] == 0x10:
            # Short frame (SND_NKE) - respond with ACK
            return b"\xe5"
        elif len(request) == 5 and request[1] == 0x5B:
            # REQ_UD2 - respond with sample data frame
            return bytes(
                [
                    0x68,
                    0x1F,
                    0x1F,
                    0x68,  # Start, L, L, Start
                    0x08,
                    0x05,  # C-Field, A-Field
                    0x72,
                    0x12,
                    0x34,
                    0x56,
                    0x78,
                    0x9A,
                    0xBC,
                    0xDE,  # Sample data
                    0x02,
                    0xFD,
                    0x1B,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0x00,
                    0xAB,  # Checksum
                    0x16,  # Stop
                ]
            )
        return b""  # No response for unknown frames


@pytest.fixture
async def mock_server() -> AsyncGenerator[MockMBusServer]:
    """Create and start mock M-Bus server."""
    server = MockMBusServer()
    await server.start()
    yield server
    await server.stop()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.network
class TestMBusTransportTCP:
    """Test MBusTransport with TCP connections."""

    async def test_tcp_connection_success(self, mock_server: MockMBusServer) -> None:
        """Test successful TCP connection."""
        transport = Transport(f"socket://127.0.0.1:{mock_server.port}")

        await transport.open()
        assert transport.is_connected()

        await transport.close()
        assert not transport.is_connected()

    async def test_tcp_connection_failure(self) -> None:
        """Test TCP connection failure to non-existent server."""
        # Use a port that's definitely not in use
        transport = Transport("socket://127.0.0.1:9999")

        with pytest.raises(MBusConnectionError, match="Failed to open connection"):
            await transport.open()

        assert not transport.is_connected()

    async def test_tcp_write_and_read(self, mock_server: MockMBusServer) -> None:
        """Test writing and reading data over TCP."""
        transport = Transport(f"socket://127.0.0.1:{mock_server.port}")

        await transport.open()

        # Send SND_NKE command
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Read ACK response
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"

        await transport.close()

    async def test_tcp_req_ud2_response(self, mock_server: MockMBusServer) -> None:
        """Test REQ_UD2 command and data response."""
        transport = Transport(f"socket://127.0.0.1:{mock_server.port}")

        await transport.open()

        # Send REQ_UD2 command
        req_ud2 = bytes([0x10, 0x5B, 0x05, 0x60, 0x16])
        await transport.write(req_ud2)

        # Read first byte (should be 0x68 for long frame)
        first_byte = await transport.read(1, protocol_timeout=1.0)
        assert first_byte == b"\x68"

        # Read length fields
        length_data = await transport.read(3, protocol_timeout=0.0)
        assert len(length_data) == 3
        assert length_data[0] == length_data[1]  # L fields should match

        frame_length = length_data[0]

        # Read rest of frame
        rest = await transport.read(frame_length + 2, protocol_timeout=0.0)
        assert len(rest) == frame_length + 2
        assert rest[-1] == 0x16  # Should end with stop byte

        await transport.close()

    async def test_tcp_timeout_behavior(self, mock_server: MockMBusServer) -> None:
        """Test timeout behavior with delayed server responses."""
        mock_server.set_response_delay(0.2)  # 200ms delay

        transport = Transport(
            f"socket://127.0.0.1:{mock_server.port}", transmission_multiplier=1.0
        )

        await transport.open()

        # Send command
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Should succeed with sufficient timeout
        response = await transport.read(1, protocol_timeout=0.5)
        assert response == b"\xe5"

        await transport.close()

    async def test_tcp_timeout_expiry(self, mock_server: MockMBusServer) -> None:
        """Test timeout when server doesn't respond quickly enough."""
        mock_server.set_response_delay(0.5)  # 500ms delay

        transport = Transport(
            f"socket://127.0.0.1:{mock_server.port}", transmission_multiplier=1.0
        )

        await transport.open()

        # Send command
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Should timeout with insufficient timeout
        response = await transport.read(1, protocol_timeout=0.1)
        assert response == b""  # Empty response on timeout

        await transport.close()

    async def test_tcp_connection_drop_during_read(
        self, mock_server: MockMBusServer
    ) -> None:
        """Test handling of connection drop during read operation."""
        mock_server.set_connection_drop(1)  # Drop after first request

        transport = Transport(f"socket://127.0.0.1:{mock_server.port}")

        await transport.open()

        # Send command
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Connection will be dropped, should get partial or empty response
        response = await transport.read(1, protocol_timeout=1.0)
        # Could be empty or partial depending on timing
        assert len(response) <= 1

        # Transport should detect disconnection
        assert not transport.is_connected()

    async def test_tcp_context_manager(self, mock_server: MockMBusServer) -> None:
        """Test TCP transport as async context manager."""
        async with Transport(f"socket://127.0.0.1:{mock_server.port}") as transport:
            assert transport.is_connected()

            # Test basic communication
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=1.0)
            assert response == b"\xe5"

        # Should be closed after context
        assert not transport.is_connected()

    async def test_tcp_multiple_requests(self, mock_server: MockMBusServer) -> None:
        """Test multiple sequential requests over same TCP connection."""
        transport = Transport(f"socket://127.0.0.1:{mock_server.port}")

        await transport.open()

        # Send multiple requests
        for _ in range(3):
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=1.0)
            assert response == b"\xe5"

            # Small delay between requests
            await asyncio.sleep(0.01)

        await transport.close()

    async def test_tcp_reconnection_after_failure(
        self, mock_server: MockMBusServer
    ) -> None:
        """Test reconnection capability after connection failure."""
        transport = Transport(f"socket://127.0.0.1:{mock_server.port}")

        # First connection
        await transport.open()
        assert transport.is_connected()

        # Force close the connection
        await transport.close()
        assert not transport.is_connected()

        # Reconnect
        await transport.open()
        assert transport.is_connected()

        # Test communication still works
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"

        await transport.close()

    async def test_tcp_invalid_url_format(self) -> None:
        """Test error handling for invalid TCP URL format."""
        with pytest.raises(MBusConnectionError):
            transport = Transport("socket://invalid-host:not-a-port")
            await transport.open()
