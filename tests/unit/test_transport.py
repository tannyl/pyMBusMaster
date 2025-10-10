"""Unit tests for MBusTransport class."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from src.mbusmaster.exceptions import MBusConnectionError
from src.mbusmaster.transport import Transport


@pytest.mark.unit
class TestMBusTransportInit:
    """Test MBusTransport initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default parameters."""
        transport = Transport("/dev/ttyUSB0")

        assert transport.url == "/dev/ttyUSB0"
        assert transport.transmission_multiplier == 1.2
        assert transport.serial_kwargs["baudrate"] == 2400
        assert transport.serial_kwargs["bytesize"] == 8
        assert transport.serial_kwargs["parity"] == "E"
        assert transport.serial_kwargs["stopbits"] == 1
        assert not transport.is_connected()

    def test_init_with_custom_parameters(self) -> None:
        """Test initialization with custom parameters."""
        transport = Transport(
            "socket://localhost:5000",
            baudrate=9600,
            transmission_multiplier=1.5,
            parity="N",
            stopbits=2,
        )

        assert transport.url == "socket://localhost:5000"
        assert transport.transmission_multiplier == 1.5
        assert transport.serial_kwargs["baudrate"] == 9600
        assert transport.serial_kwargs["parity"] == "N"
        assert transport.serial_kwargs["stopbits"] == 2

    def test_init_with_kwargs(self) -> None:
        """Test initialization with additional kwargs."""
        transport = Transport("/dev/ttyUSB0", rtscts=True, dsrdtr=False, xonxoff=True)

        assert transport.serial_kwargs["rtscts"] is True
        assert transport.serial_kwargs["dsrdtr"] is False
        assert transport.serial_kwargs["xonxoff"] is True


@pytest.mark.unit
class TestMBusTransportConnection:
    """Test connection lifecycle management."""

    @pytest.mark.asyncio
    async def test_open_connection_success(
        self, mock_open_serial_connection: object
    ) -> None:
        """Test successful connection opening."""
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection",
            mock_open_serial_connection,
        ):
            await transport.open()

            assert transport.is_connected()

    @pytest.mark.asyncio
    async def test_open_connection_failure(self) -> None:
        """Test connection opening failure."""
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.side_effect = OSError("Device not found")

            with pytest.raises(MBusConnectionError) as exc_info:
                await transport.open()

            assert "Failed to open connection" in str(exc_info.value)
            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_open_already_connected(
        self, mock_open_serial_connection: object
    ) -> None:
        """Test opening when already connected."""
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.side_effect = mock_open_serial_connection
            await transport.open()
            await transport.open()  # Second call should be idempotent

            # Should only call open once
            assert mock_open.call_count == 1
            assert transport.is_connected()

    @pytest.mark.asyncio
    async def test_close_connection(self, mock_open_serial_connection: object) -> None:
        """Test connection closing."""
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection",
            mock_open_serial_connection,
        ):
            await transport.open()
            assert transport.is_connected()

            await transport.close()
            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        """Test closing when not connected."""
        transport = Transport("/dev/ttyUSB0")

        # Should not raise error
        await transport.close()
        assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, mock_open_serial_connection: object) -> None:
        """Test that close is idempotent."""
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection",
            mock_open_serial_connection,
        ):
            await transport.open()
            await transport.close()
            await transport.close()  # Second close should be safe

            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_open_serial_connection: object) -> None:
        """Test async context manager usage."""
        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection",
            mock_open_serial_connection,
        ):
            async with Transport("/dev/ttyUSB0") as transport:
                assert transport.is_connected()

            assert not transport.is_connected()


@pytest.mark.unit
class TestMBusTransportTimeouts:
    """Test timeout calculation logic."""

    def test_timeout_calculation_mbus_standard(self) -> None:
        """Test timeout calculation for M-Bus standard 8E1 configuration."""
        transport = Transport(
            "/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2
        )

        # M-Bus uses 8E1: 1 start + 8 data + 1 parity + 1 stop = 11 bits per byte
        # At 2400 baud: 11/2400 = 0.004583s per byte
        # With 1.2 multiplier: 0.0055s per byte

        # Test single byte
        assert abs(transport._calculate_timeout(1, 0.0) - 0.0055) < 0.0001

        # Test with protocol timeout
        assert abs(transport._calculate_timeout(1, 0.5) - 0.5055) < 0.0001

        # Test multiple bytes
        assert abs(transport._calculate_timeout(10, 0.5) - 0.555) < 0.001

    def test_timeout_calculation_different_serial_configs(self) -> None:
        """Test timeout varies correctly with different serial configurations."""
        # 8N1: 10 bits per byte
        transport_8n1 = Transport("/dev/ttyUSB0", baudrate=2400, parity="N")
        timeout_8n1 = transport_8n1._calculate_timeout(1, 0.0)
        assert abs(timeout_8n1 - (10 / 2400 * 1.2)) < 0.0001

        # 8E1: 11 bits per byte (M-Bus standard)
        transport_8e1 = Transport("/dev/ttyUSB0", baudrate=2400, parity="E")
        timeout_8e1 = transport_8e1._calculate_timeout(1, 0.0)
        assert abs(timeout_8e1 - (11 / 2400 * 1.2)) < 0.0001

        # 8E1 should take longer than 8N1
        assert timeout_8e1 > timeout_8n1

        # 7E2: 11 bits per byte (7 data + 1 parity + 2 stop + 1 start)
        transport_7e2 = Transport("/dev/ttyUSB0", bytesize=7, parity="E", stopbits=2)
        timeout_7e2 = transport_7e2._calculate_timeout(1, 0.0)
        assert abs(timeout_7e2 - (11 / 2400 * 1.2)) < 0.0001

    def test_timeout_multiplier_effect(self) -> None:
        """Test that transmission multiplier scales timeout correctly."""
        transport_1x = Transport("/dev/ttyUSB0", transmission_multiplier=1.0)
        transport_15x = Transport("/dev/ttyUSB0", transmission_multiplier=1.5)
        transport_2x = Transport("/dev/ttyUSB0", transmission_multiplier=2.0)

        # All should scale proportionally
        base = transport_1x._calculate_timeout(10, 0.0)
        assert abs(transport_15x._calculate_timeout(10, 0.0) - base * 1.5) < 0.0001
        assert abs(transport_2x._calculate_timeout(10, 0.0) - base * 2.0) < 0.0001

    def test_timeout_with_different_baudrates(self) -> None:
        """Test timeout scales inversely with baudrate."""
        transport_2400 = Transport("/dev/ttyUSB0", baudrate=2400)
        transport_9600 = Transport("/dev/ttyUSB0", baudrate=9600)

        # 9600 baud should be 4x faster than 2400
        timeout_2400 = transport_2400._calculate_timeout(100, 0.0)
        timeout_9600 = transport_9600._calculate_timeout(100, 0.0)
        assert abs(timeout_2400 / timeout_9600 - 4.0) < 0.01

    def test_protocol_timeout_additive(self) -> None:
        """Test that protocol timeout is additive to transmission timeout."""
        transport = Transport("/dev/ttyUSB0")

        base = transport._calculate_timeout(10, 0.0)
        with_protocol = transport._calculate_timeout(10, 0.5)

        assert abs((with_protocol - base) - 0.5) < 0.0001


@pytest.mark.unit
class TestMBusTransportErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_write_when_not_connected(self) -> None:
        """Test write raises error when not connected."""
        transport = Transport("/dev/ttyUSB0")

        with pytest.raises(MBusConnectionError) as exc_info:
            await transport.write(b"test")

        assert "not connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_read_when_not_connected(self) -> None:
        """Test read raises error when not connected."""
        transport = Transport("/dev/ttyUSB0")

        with pytest.raises(MBusConnectionError) as exc_info:
            await transport.read(1)

        assert "not connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_write_failure_marks_disconnected(
        self, mock_serial_connection: Any
    ) -> None:
        """Test that write failure marks transport as disconnected."""
        mock_reader, mock_writer = mock_serial_connection
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock write failure
            mock_writer.write.side_effect = OSError("Connection lost")

            with pytest.raises(MBusConnectionError):
                await transport.write(b"test")

            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_read_failure_marks_disconnected(
        self, mock_serial_connection: Any
    ) -> None:
        """Test that read failure marks transport as disconnected."""
        mock_reader, mock_writer = mock_serial_connection
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock read failure
            mock_reader.readexactly.side_effect = OSError("Connection lost")

            with pytest.raises(MBusConnectionError):
                await transport.read(1)

            assert not transport.is_connected()


@pytest.mark.unit
class TestMBusTransportIO:
    """Test I/O operations with mocked connections."""

    @pytest.mark.asyncio
    async def test_write_success(self, mock_serial_connection: Any) -> None:
        """Test successful write operation."""
        mock_reader, mock_writer = mock_serial_connection
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            test_data = b"test frame"
            await transport.write(test_data)

            mock_writer.write.assert_called_once_with(test_data)
            mock_writer.drain.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_success(self, mock_serial_connection: Any) -> None:
        """Test successful read operation."""
        mock_reader, mock_writer = mock_serial_connection
        transport = Transport(
            "/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2
        )

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock read response
            expected_data = b"\xe5"
            mock_reader.readexactly.return_value = expected_data

            result = await transport.read(1, protocol_timeout=0.5)

            assert result == expected_data
            mock_reader.readexactly.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_read_timeout(self, mock_serial_connection: Any) -> None:
        """Test read timeout handling."""
        mock_reader, mock_writer = mock_serial_connection
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock timeout
            mock_reader.readexactly.side_effect = TimeoutError()

            result = await transport.read(1, protocol_timeout=0.1)

            assert result == b""  # Should return empty bytes on timeout

    @pytest.mark.asyncio
    async def test_read_incomplete(self, mock_serial_connection: Any) -> None:
        """Test handling of incomplete reads."""
        mock_reader, mock_writer = mock_serial_connection
        transport = Transport("/dev/ttyUSB0")

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock incomplete read
            partial_data = b"\xe5"
            mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(
                partial_data, 5
            )

            result = await transport.read(5)

            assert result == partial_data  # Should return partial data

    @pytest.mark.asyncio
    async def test_read_with_actual_timeout_calculation(
        self, mock_serial_connection: Any
    ) -> None:
        """Test read uses correct timeout calculation."""
        mock_reader, mock_writer = mock_serial_connection
        transport = Transport(
            "/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2
        )

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            mock_reader.readexactly.return_value = b"test"

            with patch("asyncio.wait_for") as mock_wait_for:
                mock_wait_for.return_value = b"test"

                await transport.read(4, protocol_timeout=0.5)

                # Verify timeout calculation: protocol_timeout + (transmission_time * multiplier)
                # For 4 bytes at 2400 baud with 8E1: (4 * 11 bits / 2400) * 1.2 + 0.5
                expected_timeout = 0.5 + (4 * 11 / 2400) * 1.2
                mock_wait_for.assert_called_once()
                actual_timeout = mock_wait_for.call_args[1]["timeout"]
                assert abs(actual_timeout - expected_timeout) < 0.000001


@pytest.mark.unit
class TestMBusTransportEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_size_read_calculation(self) -> None:
        """Test timeout calculation with zero size."""
        transport = Transport(
            "/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2
        )

        size = 0
        protocol_timeout = 0.5
        # Zero size should result in zero transmission time
        calculated = transport._calculate_timeout(size, protocol_timeout)

        assert calculated == protocol_timeout  # Should equal protocol timeout only

    def test_large_size_read_calculation(self) -> None:
        """Test timeout calculation with large size."""
        transport = Transport(
            "/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2
        )

        size = 255  # Maximum M-Bus frame size
        protocol_timeout = 0.0
        # For 255 bytes at 2400 baud with 8E1: (255 * 11 bits / 2400) * 1.2
        expected = (255 * 11 / 2400) * 1.2

        calculated = transport._calculate_timeout(size, protocol_timeout)

        assert abs(calculated - expected) < 0.000001

    def test_high_baudrate_calculation(self) -> None:
        """Test timeout calculation with high baudrate."""
        transport = Transport(
            "/dev/ttyUSB0", baudrate=115200, transmission_multiplier=1.0
        )

        size = 10
        protocol_timeout = 0.0
        # For 10 bytes at 115200 baud with 8E1: (10 * 11 bits / 115200) * 1.0
        expected = (10 * 11 / 115200) * 1.0  # Should be less than 1ms

        calculated = transport._calculate_timeout(size, protocol_timeout)

        assert calculated < 0.001  # Less than 1ms
        assert abs(calculated - expected) < 0.000001

    @pytest.mark.asyncio
    async def test_context_manager_exception_handling(
        self, mock_serial_connection: Any
    ) -> None:
        """Test context manager handles exceptions properly."""
        mock_reader, mock_writer = mock_serial_connection
        transport: Transport | None = None

        with patch(
            "src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection"
        ) as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)

            try:
                async with Transport("/dev/ttyUSB0") as transport:
                    assert transport.is_connected()
                    raise ValueError("Test exception")
            except ValueError:
                pass  # Expected

            # Should still be closed after exception
            assert transport is not None
            assert not transport.is_connected()
