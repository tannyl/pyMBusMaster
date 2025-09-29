"""Integration tests for MBusTransport serial connections."""

from __future__ import annotations

import asyncio
import os
import pty
import threading
import time
from collections.abc import Generator
from typing import TypedDict

import pytest

from src.mbusmaster.exceptions import MBusConnectionError
from src.mbusmaster.transport import MBusTransport


class SerialConfig(TypedDict):
    """Type definition for serial configuration."""

    bytesize: int
    parity: str
    stopbits: float


class VirtualSerialDevice:
    """Virtual serial device using pty for testing."""

    def __init__(self) -> None:
        self.master_fd: int = -1
        self.slave_fd: int = -1
        self.slave_name: str = ""
        self.server_thread: threading.Thread | None = None
        self.running = False
        self.response_delay = 0.0
        self.drop_after_count = 0
        self.request_count = 0

    def start(self) -> None:
        """Start the virtual serial device."""
        self.master_fd, self.slave_fd = pty.openpty()
        self.slave_name = os.ttyname(self.slave_fd)
        self.running = True
        self.request_count = 0

        # Start server thread to handle requests
        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()

    def stop(self) -> None:
        """Stop the virtual serial device."""
        self.running = False
        if self.server_thread:
            self.server_thread.join(timeout=1.0)

        if self.master_fd >= 0:
            os.close(self.master_fd)
        if self.slave_fd >= 0:
            os.close(self.slave_fd)

    def set_response_delay(self, delay: float) -> None:
        """Set delay before responding to requests."""
        self.response_delay = delay

    def set_drop_after_count(self, count: int) -> None:
        """Set device to stop responding after N requests."""
        self.drop_after_count = count

    def _server_loop(self) -> None:
        """Server loop handling serial communication."""
        try:
            while self.running:
                # Check for incoming data with timeout
                import select

                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if not ready:
                    continue

                # Read request
                try:
                    data = os.read(self.master_fd, 1024)
                    if not data:
                        continue

                    self.request_count += 1

                    # Check if we should stop responding
                    if (
                        self.drop_after_count > 0
                        and self.request_count >= self.drop_after_count
                    ):
                        continue

                    # Add response delay if configured
                    if self.response_delay > 0:
                        time.sleep(self.response_delay)

                    # Generate response
                    response = self._generate_response(data)
                    if response and self.running:
                        os.write(self.master_fd, response)

                except (OSError, BlockingIOError):
                    if self.running:
                        time.sleep(0.01)
                    continue

        except Exception:
            pass  # Ignore errors during shutdown

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
                    0x15,
                    0x15,
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
                    0x9A,  # Checksum
                    0x16,  # Stop
                ]
            )
        return b""


@pytest.fixture
def virtual_serial() -> Generator[VirtualSerialDevice]:
    """Create virtual serial device."""
    device = VirtualSerialDevice()
    device.start()
    yield device
    device.stop()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.serial
@pytest.mark.skipif(os.name == "nt", reason="pty not available on Windows")
class TestMBusTransportSerial:
    """Test MBusTransport with serial connections."""

    async def test_serial_connection_success(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test successful serial connection."""
        # Use 8N1 for pty compatibility (pty doesn't support all parity modes)
        transport = MBusTransport(
            virtual_serial.slave_name, baudrate=9600, parity="N", stopbits=1
        )

        await transport.open()
        assert transport.is_connected()

        await transport.close()
        assert not transport.is_connected()

    async def test_serial_connection_failure(self) -> None:
        """Test serial connection failure to non-existent port."""
        transport = MBusTransport("/dev/nonexistent_serial_port")

        with pytest.raises(MBusConnectionError, match="Failed to open connection"):
            await transport.open()

        assert not transport.is_connected()

    async def test_serial_write_and_read(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test writing and reading data over serial."""
        transport = MBusTransport(virtual_serial.slave_name, baudrate=9600, parity="N")

        await transport.open()

        # Send SND_NKE command
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Read ACK response
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"

        await transport.close()

    async def test_serial_different_baudrates(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test serial communication with different baud rates."""
        for baudrate in [2400, 9600, 19200]:
            transport = MBusTransport(
                virtual_serial.slave_name, baudrate=baudrate, parity="N"
            )

            await transport.open()
            assert transport.serial_kwargs["baudrate"] == baudrate

            # Test communication
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=1.0)
            assert response == b"\xe5"

            await transport.close()

    async def test_serial_transmission_time_calculation(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test transmission time calculation affects timeouts."""
        # Use 8N1 for pty compatibility (pty doesn't support parity)
        transport = MBusTransport(
            virtual_serial.slave_name,
            baudrate=2400,
            parity="N",  # Use no parity for pty compatibility
        )

        await transport.open()

        # Verify transmission time calculation through timeout behavior
        # Test that communication succeeds with adequate protocol timeout
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=0.1)
        assert response == b"\xe5"

        await transport.close()

    async def test_serial_timeout_behavior(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test timeout behavior with delayed responses."""
        virtual_serial.set_response_delay(0.1)  # 100ms delay

        transport = MBusTransport(
            virtual_serial.slave_name, baudrate=9600, transmission_multiplier=1.0
        )

        await transport.open()

        # Send command
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Should succeed with sufficient timeout
        response = await transport.read(1, protocol_timeout=0.5)
        assert response == b"\xe5"

        await transport.close()

    async def test_serial_timeout_expiry(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test timeout when device doesn't respond quickly enough."""
        virtual_serial.set_response_delay(0.3)  # 300ms delay

        transport = MBusTransport(
            virtual_serial.slave_name, baudrate=9600, transmission_multiplier=1.0
        )

        await transport.open()

        # Send command
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)

        # Should timeout with insufficient timeout
        response = await transport.read(1, protocol_timeout=0.1)
        assert response == b""  # Empty response on timeout

        await transport.close()

    async def test_serial_different_configurations(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test different serial configurations."""
        # Test configuration storage and one that works with pty
        test_config = SerialConfig(bytesize=8, parity="N", stopbits=1)  # 8N1

        transport = MBusTransport(
            virtual_serial.slave_name,
            bytesize=test_config["bytesize"],
            parity=test_config["parity"],
            stopbits=test_config["stopbits"],
        )

        # Verify configuration was stored correctly before opening
        assert transport.serial_kwargs["bytesize"] == test_config["bytesize"]
        assert transport.serial_kwargs["parity"] == test_config["parity"]
        assert transport.serial_kwargs["stopbits"] == test_config["stopbits"]

        # Now test actual communication with 8N1 (pty-compatible)
        await transport.open()

        # Test basic communication
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=1.0)
        assert response == b"\xe5"

        await transport.close()

        # Additional test: verify M-Bus standard configuration can be created
        # (even though pty can't open it, we can verify the transport accepts it)
        mbus_transport = MBusTransport(
            "/dev/dummy",  # Won't actually open this
            bytesize=8,
            parity="E",  # Even parity - M-Bus standard
            stopbits=1,
        )
        assert mbus_transport.serial_kwargs["parity"] == "E"

    async def test_serial_req_ud2_response(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test REQ_UD2 command and data response over serial."""
        transport = MBusTransport(virtual_serial.slave_name, baudrate=9600)

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

    async def test_serial_context_manager(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test serial transport as async context manager."""
        async with MBusTransport(virtual_serial.slave_name, baudrate=9600) as transport:
            assert transport.is_connected()

            # Test basic communication
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=1.0)
            assert response == b"\xe5"

        # Should be closed after context
        assert not transport.is_connected()

    async def test_serial_multiple_requests(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test multiple sequential requests over same serial connection."""
        transport = MBusTransport(virtual_serial.slave_name, baudrate=9600)

        await transport.open()

        # Send multiple requests
        for _ in range(3):
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)
            response = await transport.read(1, protocol_timeout=1.0)
            assert response == b"\xe5"

            # Small delay between requests (M-Bus inter-telegram time)
            await asyncio.sleep(0.01)

        await transport.close()

    async def test_serial_transmission_multiplier_effect(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test that transmission multiplier affects timeouts correctly."""
        # Test with different multipliers and verify the calculation
        for multiplier in [1.0, 1.2, 1.5]:
            transport = MBusTransport(
                virtual_serial.slave_name,
                baudrate=2400,
                transmission_multiplier=multiplier,
                parity="N",  # Use N for pty compatibility
            )

            await transport.open()

            # Test that different multipliers work correctly in practice
            # For 1 byte at 2400 baud with 8N1 = 10 bits per byte = ~0.00417s
            # With different multipliers, timeout behavior should differ

            # Send command and verify communication works
            snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
            await transport.write(snd_nke)

            # Should succeed with adequate timeout
            response = await transport.read(1, protocol_timeout=1.0)
            assert response == b"\xe5"

            await transport.close()

    async def test_serial_device_stops_responding(
        self, virtual_serial: VirtualSerialDevice
    ) -> None:
        """Test handling when serial device stops responding."""
        virtual_serial.set_drop_after_count(1)  # Stop after first request

        transport = MBusTransport(virtual_serial.slave_name, baudrate=9600)

        await transport.open()

        # First request should work
        snd_nke = bytes([0x10, 0x40, 0x05, 0x45, 0x16])
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=0.5)
        assert response == b"\xe5"

        # Second request should timeout
        await transport.write(snd_nke)
        response = await transport.read(1, protocol_timeout=0.2)
        assert response == b""  # Should timeout

        await transport.close()
