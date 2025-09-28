"""Unit tests for MBusTransport class."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from src.mbusmaster.exceptions import MBusConnectionError
from src.mbusmaster.transport import MBusTransport


class TestMBusTransportInit:
    """Test MBusTransport initialization."""

    def test_init_with_defaults(self) -> None:
        """Test initialization with default parameters."""
        transport = MBusTransport("/dev/ttyUSB0")

        assert transport.url == "/dev/ttyUSB0"
        assert transport.transmission_multiplier == 1.2
        assert transport.baudrate == 2400
        assert transport.serial_kwargs["baudrate"] == 2400
        assert transport.serial_kwargs["bytesize"] == 8
        assert transport.serial_kwargs["parity"] == "E"
        assert transport.serial_kwargs["stopbits"] == 1
        assert not transport.is_connected()

    def test_init_with_custom_parameters(self) -> None:
        """Test initialization with custom parameters."""
        transport = MBusTransport(
            "socket://localhost:5000",
            baudrate=9600,
            transmission_multiplier=1.5,
            parity="N",
            stopbits=2
        )

        assert transport.url == "socket://localhost:5000"
        assert transport.transmission_multiplier == 1.5
        assert transport.baudrate == 9600
        assert transport.serial_kwargs["baudrate"] == 9600
        assert transport.serial_kwargs["parity"] == "N"
        assert transport.serial_kwargs["stopbits"] == 2

    def test_init_with_kwargs(self) -> None:
        """Test initialization with additional kwargs."""
        transport = MBusTransport(
            "/dev/ttyUSB0",
            rtscts=True,
            dsrdtr=False,
            xonxoff=True
        )

        assert transport.serial_kwargs["rtscts"] is True
        assert transport.serial_kwargs["dsrdtr"] is False
        assert transport.serial_kwargs["xonxoff"] is True


class TestMBusTransportConnection:
    """Test connection lifecycle management."""

    @pytest.mark.asyncio
    async def test_open_connection_success(self, mock_open_serial_connection: object) -> None:
        """Test successful connection opening."""
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection', mock_open_serial_connection):
            await transport.open()

            assert transport.is_connected()

    @pytest.mark.asyncio
    async def test_open_connection_failure(self) -> None:
        """Test connection opening failure."""
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.side_effect = OSError("Device not found")

            with pytest.raises(MBusConnectionError) as exc_info:
                await transport.open()

            assert "Failed to open connection" in str(exc_info.value)
            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_open_already_connected(self, mock_open_serial_connection: object) -> None:
        """Test opening when already connected."""
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.side_effect = mock_open_serial_connection
            await transport.open()
            await transport.open()  # Second call should be idempotent

            # Should only call open once
            assert mock_open.call_count == 1
            assert transport.is_connected()

    @pytest.mark.asyncio
    async def test_close_connection(self, mock_open_serial_connection: object) -> None:
        """Test connection closing."""
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection', mock_open_serial_connection):
            await transport.open()
            assert transport.is_connected()

            await transport.close()
            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_close_when_not_connected(self) -> None:
        """Test closing when not connected."""
        transport = MBusTransport("/dev/ttyUSB0")

        # Should not raise error
        await transport.close()
        assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, mock_open_serial_connection: object) -> None:
        """Test that close is idempotent."""
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection', mock_open_serial_connection):
            await transport.open()
            await transport.close()
            await transport.close()  # Second close should be safe

            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_open_serial_connection: object) -> None:
        """Test async context manager usage."""
        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection', mock_open_serial_connection):
            async with MBusTransport("/dev/ttyUSB0") as transport:
                assert transport.is_connected()

            assert not transport.is_connected()


class TestMBusTransportTimeouts:
    """Test timeout calculation logic."""

    def test_timeout_calculation_basic(self) -> None:
        """Test basic timeout calculation."""
        transport = MBusTransport("/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2)

        # Calculate manually
        size = 10
        protocol_timeout = 0.5
        transmission_time = (size * 10) / 2400  # 0.041667
        expected_timeout = protocol_timeout + (transmission_time * 1.2)  # 0.55

        # Test the calculation from the code
        calculated_timeout = protocol_timeout + ((size * 10) / transport.baudrate * transport.transmission_multiplier)

        assert abs(calculated_timeout - expected_timeout) < 0.000001

    def test_timeout_calculation_different_baudrates(self) -> None:
        """Test timeout calculation with different baudrates."""
        test_cases = [
            (2400, 1.0, 10, 0.5, 0.5 + (100/2400)),
            (9600, 1.2, 5, 0.0, 0.0 + (50/9600 * 1.2)),
            (19200, 1.5, 1, 1.0, 1.0 + (10/19200 * 1.5)),
        ]

        for baudrate, multiplier, size, protocol_timeout, expected in test_cases:
            transport = MBusTransport("/dev/ttyUSB0", baudrate=baudrate, transmission_multiplier=multiplier)
            calculated = protocol_timeout + ((size * 10) / transport.baudrate * transport.transmission_multiplier)
            assert abs(calculated - expected) < 0.000001

    def test_timeout_with_zero_protocol_timeout(self) -> None:
        """Test timeout calculation when protocol provides no extra time."""
        transport = MBusTransport("/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2)

        size = 4
        protocol_timeout = 0.0
        transmission_time = (4 * 10) / 2400  # 0.016667
        expected = transmission_time * 1.2  # Only transmission time with multiplier

        calculated = protocol_timeout + ((size * 10) / transport.baudrate * transport.transmission_multiplier)

        assert abs(calculated - expected) < 0.000001

    def test_transmission_multiplier_effect(self) -> None:
        """Test the effect of different transmission multipliers."""
        base_transport = MBusTransport("/dev/ttyUSB0", transmission_multiplier=1.0)
        fast_transport = MBusTransport("/dev/ttyUSB0", transmission_multiplier=1.2)
        slow_transport = MBusTransport("/dev/ttyUSB0", transmission_multiplier=2.0)

        size = 10
        protocol_timeout = 0.0

        base_timeout = protocol_timeout + ((size * 10) / base_transport.baudrate * base_transport.transmission_multiplier)
        fast_timeout = protocol_timeout + ((size * 10) / fast_transport.baudrate * fast_transport.transmission_multiplier)
        slow_timeout = protocol_timeout + ((size * 10) / slow_transport.baudrate * slow_transport.transmission_multiplier)

        assert fast_timeout > base_timeout
        assert slow_timeout > fast_timeout
        assert slow_timeout == base_timeout * 2.0


class TestMBusTransportErrorHandling:
    """Test error handling scenarios."""

    @pytest.mark.asyncio
    async def test_write_when_not_connected(self) -> None:
        """Test write raises error when not connected."""
        transport = MBusTransport("/dev/ttyUSB0")

        with pytest.raises(MBusConnectionError) as exc_info:
            await transport.write(b"test")

        assert "not connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_read_when_not_connected(self) -> None:
        """Test read raises error when not connected."""
        transport = MBusTransport("/dev/ttyUSB0")

        with pytest.raises(MBusConnectionError) as exc_info:
            await transport.read(1)

        assert "not connected" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_write_failure_marks_disconnected(self, mock_serial_connection: Any) -> None:
        """Test that write failure marks transport as disconnected."""
        mock_reader, mock_writer = mock_serial_connection
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock write failure
            mock_writer.write.side_effect = OSError("Connection lost")

            with pytest.raises(MBusConnectionError):
                await transport.write(b"test")

            assert not transport.is_connected()

    @pytest.mark.asyncio
    async def test_read_failure_marks_disconnected(self, mock_serial_connection: Any) -> None:
        """Test that read failure marks transport as disconnected."""
        mock_reader, mock_writer = mock_serial_connection
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock read failure
            mock_reader.readexactly.side_effect = OSError("Connection lost")

            with pytest.raises(MBusConnectionError):
                await transport.read(1)

            assert not transport.is_connected()


class TestMBusTransportIO:
    """Test I/O operations with mocked connections."""

    @pytest.mark.asyncio
    async def test_write_success(self, mock_serial_connection: Any) -> None:
        """Test successful write operation."""
        mock_reader, mock_writer = mock_serial_connection
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
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
        transport = MBusTransport("/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2)

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock read response
            expected_data = b"\xE5"
            mock_reader.readexactly.return_value = expected_data

            result = await transport.read(1, protocol_timeout=0.5)

            assert result == expected_data
            mock_reader.readexactly.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_read_timeout(self, mock_serial_connection: Any) -> None:
        """Test read timeout handling."""
        mock_reader, mock_writer = mock_serial_connection
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
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
        transport = MBusTransport("/dev/ttyUSB0")

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            # Mock incomplete read
            partial_data = b"\xE5"
            mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(partial_data, 5)

            result = await transport.read(5)

            assert result == partial_data  # Should return partial data

    @pytest.mark.asyncio
    async def test_read_with_actual_timeout_calculation(self, mock_serial_connection: Any) -> None:
        """Test read uses correct timeout calculation."""
        mock_reader, mock_writer = mock_serial_connection
        transport = MBusTransport("/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2)

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)
            await transport.open()

            mock_reader.readexactly.return_value = b"test"

            with patch('asyncio.wait_for') as mock_wait_for:
                mock_wait_for.return_value = b"test"

                await transport.read(4, protocol_timeout=0.5)

                # Verify timeout calculation: 0.5 + (4 * 10 / 2400 * 1.2) = 0.52
                expected_timeout = 0.5 + ((4 * 10) / 2400 * 1.2)
                mock_wait_for.assert_called_once()
                actual_timeout = mock_wait_for.call_args[1]['timeout']
                assert abs(actual_timeout - expected_timeout) < 0.000001


class TestMBusTransportEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_size_read_calculation(self) -> None:
        """Test timeout calculation with zero size."""
        transport = MBusTransport("/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2)

        size = 0
        protocol_timeout = 0.5
        calculated = protocol_timeout + ((size * 10) / transport.baudrate * transport.transmission_multiplier)

        assert calculated == protocol_timeout  # Should equal protocol timeout only

    def test_large_size_read_calculation(self) -> None:
        """Test timeout calculation with large size."""
        transport = MBusTransport("/dev/ttyUSB0", baudrate=2400, transmission_multiplier=1.2)

        size = 255  # Maximum M-Bus frame size
        protocol_timeout = 0.0
        transmission_time = (255 * 10) / 2400  # 1.0625 seconds
        expected = transmission_time * 1.2  # 1.275 seconds

        calculated = protocol_timeout + ((size * 10) / transport.baudrate * transport.transmission_multiplier)

        assert abs(calculated - expected) < 0.000001

    def test_high_baudrate_calculation(self) -> None:
        """Test timeout calculation with high baudrate."""
        transport = MBusTransport("/dev/ttyUSB0", baudrate=115200, transmission_multiplier=1.0)

        size = 10
        protocol_timeout = 0.0
        transmission_time = (10 * 10) / 115200  # Very small time
        expected = transmission_time  # Should be less than 1ms

        calculated = protocol_timeout + ((size * 10) / transport.baudrate * transport.transmission_multiplier)

        assert calculated < 0.001  # Less than 1ms
        assert abs(calculated - expected) < 0.000001

    @pytest.mark.asyncio
    async def test_context_manager_exception_handling(self, mock_serial_connection: Any) -> None:
        """Test context manager handles exceptions properly."""
        mock_reader, mock_writer = mock_serial_connection
        transport: MBusTransport | None = None

        with patch('src.mbusmaster.transport.serial_asyncio_fast.open_serial_connection') as mock_open:
            mock_open.return_value = (mock_reader, mock_writer)

            try:
                async with MBusTransport("/dev/ttyUSB0") as transport:
                    assert transport.is_connected()
                    raise ValueError("Test exception")
            except ValueError:
                pass  # Expected

            # Should still be closed after exception
            assert transport is not None
            assert not transport.is_connected()
