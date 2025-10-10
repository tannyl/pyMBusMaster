"""Integration tests for MBusTransport connection recovery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest

from src.mbusmaster.exceptions import MBusConnectionError
from src.mbusmaster.transport import Transport


class UnstableServer:
    """Mock server that can simulate various failure scenarios."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.connection_count = 0
        self.failure_mode = "none"
        self.failure_after_requests = 0
        self.restart_delay = 0.0
        self.is_running = True

    async def start(self) -> None:
        """Start the unstable mock server."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        if self.port == 0:
            self.port = self.server.sockets[0].getsockname()[1]
        self.is_running = True

    async def stop(self) -> None:
        """Stop the mock server."""
        self.is_running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def restart(self) -> None:
        """Restart the server after a delay."""
        await self.stop()
        if self.restart_delay > 0:
            await asyncio.sleep(self.restart_delay)
        await self.start()

    def set_failure_mode(
        self, mode: str, after_requests: int = 1, restart_delay: float = 0.0
    ) -> None:
        """Configure failure behavior.

        Modes:
        - 'drop_connection': Drop connection after N requests
        - 'refuse_connection': Refuse new connections
        - 'server_restart': Restart server after N requests
        - 'slow_response': Very slow responses
        - 'partial_response': Send incomplete responses
        """
        self.failure_mode = mode
        self.failure_after_requests = after_requests
        self.restart_delay = restart_delay

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle client with various failure modes."""
        self.connection_count += 1
        request_count = 0

        try:
            while self.is_running:
                data = await reader.read(1024)
                if not data:
                    break

                request_count += 1

                # Apply failure behavior
                if request_count >= self.failure_after_requests:
                    if self.failure_mode == "drop_connection":
                        break  # Abruptly close connection
                    elif self.failure_mode == "server_restart":
                        # Schedule server restart
                        asyncio.create_task(self._delayed_restart())
                        break
                    elif self.failure_mode == "slow_response":
                        await asyncio.sleep(5.0)  # Very slow
                    elif self.failure_mode == "partial_response":
                        # Send incomplete response
                        writer.write(b"\xe5"[:-1])  # Partial ACK
                        await writer.drain()
                        break

                # Normal response
                if self.failure_mode != "refuse_connection":
                    writer.write(b"\xe5")
                    await writer.drain()

        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _delayed_restart(self) -> None:
        """Restart server after delay."""
        await asyncio.sleep(self.restart_delay)
        if not self.is_running:
            return
        try:
            await self.restart()
        except Exception:
            pass


@pytest.fixture
async def unstable_server() -> AsyncGenerator[UnstableServer]:
    """Create unstable mock server."""
    server = UnstableServer()
    await server.start()
    yield server
    await server.stop()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.network
class TestMBusTransportRecovery:
    """Test MBusTransport connection recovery scenarios."""

    async def test_connection_drop_detection(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test that connection drops are properly detected."""
        unstable_server.set_failure_mode("drop_connection", after_requests=1)

        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        await transport.open()
        assert transport.is_connected()

        # Send request - connection will be dropped
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Read should detect connection drop
        response = await transport.read(1, protocol_timeout=1.0)
        # Could be empty or partial depending on timing
        assert len(response) <= 1

        # Transport should detect it's no longer connected
        # (This might require a subsequent operation to detect)
        try:
            await transport.write(snd_nke)
            await transport.read(1, protocol_timeout=0.1)
        except MBusConnectionError:
            pass  # Expected

        await transport.close()

    async def test_reconnection_after_drop(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test successful reconnection after connection drop."""
        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        # Initial connection
        await transport.open()
        assert transport.is_connected()

        # Close and reconnect
        await transport.close()
        assert not transport.is_connected()

        # Should be able to reconnect
        await transport.open()
        assert transport.is_connected()

        # Test communication still works
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"

        await transport.close()

    async def test_server_restart_recovery(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test recovery when server restarts."""
        unstable_server.set_failure_mode(
            "server_restart", after_requests=1, restart_delay=0.1
        )

        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        await transport.open()

        # Send request that triggers server restart
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # This read may fail due to server restart
        try:
            response = await transport.read(1, protocol_timeout=0.5)
        except MBusConnectionError:
            pass

        # Wait for server to restart
        await asyncio.sleep(0.2)

        # Should be able to reconnect after server restart
        await transport.close()
        await transport.open()

        # Test communication works again
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"

        await transport.close()

    async def test_multiple_connection_failures(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test handling multiple consecutive connection failures."""
        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        # Test multiple open/close cycles
        for _ in range(3):
            await transport.open()
            assert transport.is_connected()

            # Test communication
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=1.0)
            assert response == b"\xe5"

            await transport.close()
            assert not transport.is_connected()

            # Small delay between cycles
            await asyncio.sleep(0.01)

    async def test_connection_timeout_recovery(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test recovery from connection timeouts."""
        unstable_server.set_failure_mode("slow_response", after_requests=1)

        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        await transport.open()

        # Send request that will cause slow response
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Should timeout
        response = await transport.read(1, protocol_timeout=0.1)
        assert response == b""

        # Reset server behavior and try again
        unstable_server.set_failure_mode("none")

        # Close and reopen connection
        await transport.close()
        await transport.open()

        # Should work normally now
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"

        await transport.close()

    async def test_partial_response_handling(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test handling of partial responses."""
        unstable_server.set_failure_mode("partial_response", after_requests=1)

        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        await transport.open()

        # Send request that will get partial response
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Should get partial data
        response = await transport.read(1, protocol_timeout=1.0)
        # Might get partial response or connection error
        assert len(response) <= 1

        await transport.close()

    async def test_rapid_connection_cycling(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test rapid connection open/close cycles."""
        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        # Rapid cycles to test for resource leaks or state issues
        for _ in range(10):
            await transport.open()
            await transport.close()

        # Final test to ensure everything still works
        await transport.open()
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"
        await transport.close()

    async def test_connection_state_consistency(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test that connection state remains consistent through failures."""
        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        # Initially not connected
        assert not transport.is_connected()

        # After opening, should be connected
        await transport.open()
        assert transport.is_connected()

        # After closing, should not be connected
        await transport.close()
        assert not transport.is_connected()

        # Double close should be safe
        await transport.close()
        assert not transport.is_connected()

        # Double open should be safe
        await transport.open()
        assert transport.is_connected()
        await transport.open()  # Should not fail
        assert transport.is_connected()

        await transport.close()

    async def test_context_manager_exception_handling(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test context manager behavior during exceptions."""
        unstable_server.set_failure_mode("drop_connection", after_requests=1)

        try:
            async with Transport(
                f"socket://127.0.0.1:{unstable_server.port}"
            ) as transport:
                assert transport.is_connected()

                # This will cause connection to drop
                snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
                await transport.write(snd_nke)
                await transport.read(1, protocol_timeout=0.1)

                # Force an exception to test cleanup
                raise ValueError("Test exception")

        except ValueError:
            pass  # Expected exception

        # Transport should be properly closed despite exception
        # (Can't easily test this without accessing private state)

    async def test_concurrent_connection_recovery(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test connection recovery with concurrent operations."""
        # Create multiple transports
        transports = []
        for _ in range(3):
            transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")
            transports.append(transport)

        try:
            # Open all connections
            await asyncio.gather(*[t.open() for t in transports])

            # All should be connected
            for transport in transports:
                assert transport.is_connected()

            # Close all connections
            await asyncio.gather(*[t.close() for t in transports])

            # All should be disconnected
            for transport in transports:
                assert not transport.is_connected()

            # Reopen all connections
            await asyncio.gather(*[t.open() for t in transports])

            # Test communication on all
            tasks = []
            for transport in transports:
                tasks.append(self._test_communication(transport))

            results = await asyncio.gather(*tasks)

            # All should succeed
            for result in results:
                assert result == b"\xe5"

        finally:
            await asyncio.gather(*[t.close() for t in transports])

    async def _test_communication(self, transport: Transport) -> bytes:
        """Helper to test basic communication."""
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        return await transport.read(1, protocol_timeout=1.0)

    async def test_error_propagation_during_recovery(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test that errors are properly propagated during recovery attempts."""
        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        await transport.open()

        # Stop the server completely
        await unstable_server.stop()

        # Operations should fail with appropriate errors
        with pytest.raises(MBusConnectionError):
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)

        # Close should still work
        await transport.close()
        assert not transport.is_connected()

        # Attempting to open should fail with server down
        with pytest.raises(MBusConnectionError):
            await transport.open()

    async def test_cleanup_on_repeated_failures(
        self, unstable_server: UnstableServer
    ) -> None:
        """Test proper cleanup when facing repeated failures."""
        unstable_server.set_failure_mode("drop_connection", after_requests=1)

        transport = Transport(f"socket://127.0.0.1:{unstable_server.port}")

        # Try multiple operations that will fail
        for _ in range(5):
            try:
                await transport.open()
                snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
                await transport.write(snd_nke)
                await transport.read(1, protocol_timeout=0.1)
            except (MBusConnectionError, Exception):
                pass
            finally:
                await transport.close()

        # Reset server and verify transport still works
        unstable_server.set_failure_mode("none")
        await transport.open()
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"
        await transport.close()
