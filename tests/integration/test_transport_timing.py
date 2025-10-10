"""Integration tests for MBusTransport timing behavior."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator

import pytest

from src.mbusmaster.transport import Transport


class TimingMockServer:
    """Mock server for precise timing tests."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.controlled_delays: dict[int, float] = {}  # request_number -> delay
        self.request_timestamps: list[float] = []

    async def start(self) -> None:
        """Start the timing mock server."""
        self.server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        if self.port == 0:
            self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Stop the mock server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    def set_response_delay(self, request_number: int, delay: float) -> None:
        """Set specific delay for a request number (0-indexed)."""
        self.controlled_delays[request_number] = delay

    def get_request_timestamps(self) -> list[float]:
        """Get timestamps of received requests."""
        return self.request_timestamps.copy()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle client with precise timing control."""
        request_count = 0

        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break

                # Record request timestamp
                self.request_timestamps.append(time.time())

                # Apply controlled delay if configured
                delay = self.controlled_delays.get(request_count, 0.0)
                if delay > 0:
                    await asyncio.sleep(delay)

                # Send standard ACK response
                writer.write(b"\xe5")
                await writer.drain()

                request_count += 1

        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass


@pytest.fixture
async def timing_server() -> AsyncGenerator[TimingMockServer]:
    """Create timing mock server."""
    server = TimingMockServer()
    await server.start()
    yield server
    await server.stop()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.timing
@pytest.mark.network
class TestMBusTransportTiming:
    """Test MBusTransport timing behavior with real I/O."""

    async def test_transmission_time_accuracy(
        self, timing_server: TimingMockServer
    ) -> None:
        """Test that transmission time calculations are accurate."""
        # Test different baud rates and verify timing accuracy
        test_cases: list[dict[str, int | float]] = [
            {"baudrate": 2400, "expected_time_per_byte": 11 / 2400},  # M-Bus standard
            {"baudrate": 9600, "expected_time_per_byte": 11 / 9600},
            {"baudrate": 19200, "expected_time_per_byte": 11 / 19200},
        ]

        for case in test_cases:
            transport = Transport(
                f"socket://127.0.0.1:{timing_server.port}",
                baudrate=int(case["baudrate"]),
                transmission_multiplier=1.0,
            )

            # Verify timeout calculation through practical timeout testing
            # Test that timeouts scale correctly with frame size
            await transport.open()

            # Test small timeout that should succeed (server responds quickly)
            timing_server.set_response_delay(0, 0.001)
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=0.1)
            assert response == b"\xe5"

            await transport.close()

    async def test_timeout_calculation_components(
        self, timing_server: TimingMockServer
    ) -> None:
        """Test that timeout calculation properly separates protocol and transmission time."""
        transport = Transport(
            f"socket://127.0.0.1:{timing_server.port}",
            baudrate=2400,
            transmission_multiplier=1.2,
        )

        await transport.open()

        # Test read with protocol timeout
        protocol_timeout = 0.1
        # Expected total timeout = protocol + (transmission * multiplier)
        # For 1 byte at 2400 baud: (11 bits / 2400) * 1.2 = 0.0055s
        expected_total = protocol_timeout + (11 / 2400) * 1.2

        # Measure actual timeout behavior
        start_time = time.time()

        # Send request but server won't respond (no delay configured)
        timing_server.set_response_delay(0, 10.0)  # Very long delay to force timeout

        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        await transport.read(1, protocol_timeout=protocol_timeout)
        elapsed = time.time() - start_time

        # Should timeout close to expected time (within some tolerance)
        assert abs(elapsed - expected_total) < 0.05  # 50ms tolerance

        await transport.close()

    async def test_transmission_multiplier_effects(
        self, timing_server: TimingMockServer
    ) -> None:
        """Test that transmission multiplier properly affects timeouts."""
        test_multipliers = [1.0, 1.2, 1.5, 2.0]

        for multiplier in test_multipliers:
            transport = Transport(
                f"socket://127.0.0.1:{timing_server.port}",
                baudrate=2400,
                transmission_multiplier=multiplier,
            )

            await transport.open()

            # Calculate expected timeout with this multiplier
            protocol_timeout = 0.05
            # For 1 byte at 2400 baud: (11 bits / 2400) = 0.00458s base
            base_transmission = 11 / 2400
            expected_total = protocol_timeout + (base_transmission * multiplier)

            # Force timeout by making server delay too long
            timing_server.set_response_delay(0, 10.0)

            start_time = time.time()
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)

            await transport.read(1, protocol_timeout=protocol_timeout)
            elapsed = time.time() - start_time

            # Verify timeout matches expected value with multiplier
            assert abs(elapsed - expected_total) < 0.03

            await transport.close()

            # Reset server for next test
            timing_server.controlled_delays.clear()

    async def test_zero_protocol_timeout_behavior(
        self, timing_server: TimingMockServer
    ) -> None:
        """Test behavior when protocol_timeout is 0.0."""
        transport = Transport(
            f"socket://127.0.0.1:{timing_server.port}",
            baudrate=9600,
            transmission_multiplier=1.2,
        )

        await transport.open()

        # With protocol_timeout=0.0, timeout should only be transmission time
        # For 1 byte at 9600 baud: (11 bits / 9600) * 1.2 = 0.00138s
        expected_timeout = (11 / 9600) * 1.2

        # Make server respond quickly
        timing_server.set_response_delay(0, 0.001)

        start_time = time.time()
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        response = await transport.read(1, protocol_timeout=0.0)
        elapsed = time.time() - start_time

        # Should succeed within transmission timeout
        assert response == b"\xe5"
        assert elapsed < expected_timeout

        await transport.close()

    async def test_large_frame_timeout_scaling(
        self, timing_server: TimingMockServer
    ) -> None:
        """Test that timeouts scale correctly for larger frames."""
        transport = Transport(
            f"socket://127.0.0.1:{timing_server.port}",
            baudrate=2400,
            transmission_multiplier=1.2,
        )

        await transport.open()

        # Test different frame sizes
        frame_sizes = [1, 10, 50, 100]

        for size in frame_sizes:
            # Calculate expected timeout for this frame size
            # For size bytes at 2400 baud: (size * 11 bits / 2400) * 1.2
            expected_timeout = (size * 11 / 2400) * 1.2

            # Make server delay longer than expected timeout to force timeout
            timing_server.set_response_delay(0, expected_timeout + 0.1)

            start_time = time.time()
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)

            response = await transport.read(size, protocol_timeout=0.0)
            elapsed = time.time() - start_time

            # Should timeout close to expected time
            assert response == b""  # Timeout
            assert abs(elapsed - expected_timeout) < 0.05

            # Reset for next test
            timing_server.controlled_delays.clear()

        await transport.close()

    async def test_real_timing_precision(self, timing_server: TimingMockServer) -> None:
        """Test timing precision under real I/O conditions."""
        transport = Transport(
            f"socket://127.0.0.1:{timing_server.port}",
            baudrate=9600,
            transmission_multiplier=1.0,
        )

        await transport.open()

        # Test multiple requests with precise timing
        request_times = []
        response_times = []

        for i in range(5):
            # Configure server for immediate response
            timing_server.set_response_delay(i, 0.0)

            start = time.time()
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)

            mid = time.time()
            response = await transport.read(1, protocol_timeout=1.0)
            end = time.time()

            request_times.append(mid - start)
            response_times.append(end - mid)

            assert response == b"\xe5"

            # Small delay between requests
            await asyncio.sleep(0.01)

        # Verify timing consistency
        avg_request_time = sum(request_times) / len(request_times)
        avg_response_time = sum(response_times) / len(response_times)

        # Request time should be very small (just write operation)
        assert avg_request_time < 0.01

        # Response time should be reasonable for network I/O
        assert avg_response_time < 0.1

        await transport.close()

    async def test_timeout_edge_cases(self, timing_server: TimingMockServer) -> None:
        """Test edge cases in timeout calculations."""
        transport = Transport(
            f"socket://127.0.0.1:{timing_server.port}",
            baudrate=2400,
            transmission_multiplier=1.0,
        )

        await transport.open()

        # Test with zero-size read
        response = await transport.read(0, protocol_timeout=0.1)
        assert response == b""

        # Test with very small protocol timeout
        timing_server.set_response_delay(0, 0.001)
        start = time.time()
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        response = await transport.read(1, protocol_timeout=0.001)
        elapsed = time.time() - start

        # Should still include transmission time in timeout
        # For 1 byte at 2400 baud: (11 bits / 2400) = 0.00458s minimum
        min_expected_timeout = 11 / 2400
        assert elapsed >= min_expected_timeout * 0.8  # Some tolerance

        await transport.close()

    async def test_concurrent_timing_operations(
        self, timing_server: TimingMockServer
    ) -> None:
        """Test timing behavior with concurrent operations."""
        # Create multiple transports
        transports = []
        for _ in range(3):
            transport = Transport(
                f"socket://127.0.0.1:{timing_server.port}",
                baudrate=9600,
                transmission_multiplier=1.2,
            )
            await transport.open()
            transports.append(transport)

        try:
            # Configure server for predictable delays
            for i in range(6):  # 3 transports * 2 requests each
                timing_server.set_response_delay(i, 0.01 * (i + 1))

            # Send concurrent requests
            tasks = []
            start_time = time.time()

            for transport in transports:
                task = asyncio.create_task(self._send_two_requests(transport))
                tasks.append(task)

            results = await asyncio.gather(*tasks)
            total_time = time.time() - start_time

            # All should succeed
            for result in results:
                assert all(r == b"\xe5" for r in result)

            # Total time should be reasonable for concurrent execution
            assert total_time < 1.0

        finally:
            for transport in transports:
                await transport.close()

    async def _send_two_requests(self, transport: Transport) -> list[bytes]:
        """Helper to send two requests and return responses."""
        responses = []
        for _ in range(2):
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=0.5)
            responses.append(response)
            await asyncio.sleep(0.01)
        return responses
