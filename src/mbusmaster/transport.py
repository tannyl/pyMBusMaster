"""M-Bus transport layer for handling connections and raw I/O."""

from __future__ import annotations

import asyncio
from typing import Any

import serial_asyncio_fast

from .exceptions import MBusConnectionError


class MBusTransport:
    """Handles connection and raw byte I/O for M-Bus communication.

    Supports multiple connection types:
    - Serial ports: /dev/ttyUSB0, COM3
    - TCP sockets: socket://192.168.1.100:10001
    - RFC2217: rfc2217://192.168.1.100:10001

    All connection types are handled transparently by pyserial-asyncio-fast.

    Default serial parameters follow M-Bus standard (EN 13757-2):
    - 8 data bits
    - Even parity
    - 1 stop bit (8E1 format)
    - 2400 baud (configurable)
    """

    # Public attributes
    url: str
    transmission_multiplier: float
    serial_kwargs: dict[str, Any]

    # Private attributes
    _reader: asyncio.StreamReader | None
    _writer: asyncio.StreamWriter | None
    _connected: bool

    def __init__(
        self,
        url: str,
        baudrate: int = 2400,
        bytesize: int = 8,
        parity: str = "E",
        stopbits: float = 1,
        transmission_multiplier: float = 1.2,
        **kwargs: Any,
    ) -> None:
        """Initialize transport (does not open connection).

        Args:
            url: Connection URL (serial port or socket://host:port or rfc2217://host:port)
            baudrate: Baud rate for serial connections (default 2400 bps, common for M-Bus)
            bytesize: Number of data bits (default 8, M-Bus standard)
            parity: Parity checking - 'N'=None, 'E'=Even, 'O'=Odd (default 'E', M-Bus standard)
            stopbits: Number of stop bits - 1, 1.5, or 2 (default 1, M-Bus standard)
            transmission_multiplier: Multiplier for transmission time calculation
                                   for slow/problematic devices (default 1.2 = 20% extra time)
            **kwargs: Additional serial parameters (xonxoff, rtscts, dsrdtr, etc.)

        Note:
            Default serial parameters follow M-Bus standard (EN 13757-2) which requires
            8E1 format (8 data bits, Even parity, 1 stop bit). These can be overridden
            for non-standard devices, but changing them may cause communication issues
            with standard M-Bus devices.
        """
        self.url = url
        self.transmission_multiplier = transmission_multiplier

        # Build serial parameters dictionary
        self.serial_kwargs = {
            "baudrate": baudrate,
            "bytesize": bytesize,
            "parity": parity,
            "stopbits": stopbits,
            **kwargs,  # Additional parameters like flow control
        }

        # Initialize connection state
        self._reader = None
        self._writer = None
        self._connected = False

    def _calculate_timeout(self, size: int, protocol_timeout: float = 0.0) -> float:
        """Calculate total timeout for reading data.

        Args:
            size: Number of bytes to read
            protocol_timeout: Base timeout from protocol layer (for network delays, etc.)

        Returns:
            Total timeout in seconds including protocol timeout and transmission time

        Note:
            Calculates based on actual serial configuration:
            - Start bit: Always 1
            - Data bits: From bytesize setting (usually 8 for M-Bus)
            - Parity bit: 1 if parity enabled, 0 if disabled
            - Stop bits: From stopbits setting (usually 1 for M-Bus)
            - Applies transmission_multiplier to account for device variations
        """
        # Calculate bits per byte based on serial configuration
        bits_per_byte = (
            1 +  # start bit
            int(self.serial_kwargs["bytesize"]) +  # data bits
            (1 if self.serial_kwargs["parity"] != "N" else 0) +  # parity bit
            float(self.serial_kwargs["stopbits"])  # stop bits
        )

        # Calculate base transmission time
        base_transmission_time = (size * bits_per_byte) / int(self.serial_kwargs["baudrate"])

        # Return total timeout with multiplier applied
        return protocol_timeout + base_transmission_time * self.transmission_multiplier

    async def open(self) -> None:
        """Open connection to M-Bus device or gateway.

        Raises:
            MBusConnectionError: If connection fails
        """
        if self._connected:
            return  # Already connected

        try:
            # pyserial-asyncio-fast handles all connection types transparently
            (
                self._reader,
                self._writer,
            ) = await serial_asyncio_fast.open_serial_connection(
                url=self.url, **self.serial_kwargs
            )
            self._connected = True
        except Exception as e:
            raise MBusConnectionError(
                f"Failed to open connection to {self.url}: {e}"
            ) from e

    async def close(self) -> None:
        """Close connection (idempotent - safe to call multiple times)."""
        if not self._connected:
            return  # Already closed

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass  # Ignore errors during close

        self._reader = None
        self._writer = None
        self._connected = False

    def is_connected(self) -> bool:
        """Check if transport is connected.

        Returns:
            True if connected, False otherwise
        """
        return self._connected

    async def write(self, data: bytes) -> None:
        """Write raw bytes to transport.

        Args:
            data: Bytes to send

        Raises:
            MBusConnectionError: If not connected
        """
        if not self._connected or not self._writer:
            raise MBusConnectionError("Transport is not connected")

        try:
            self._writer.write(data)
            await self._writer.drain()
        except Exception as e:
            self._connected = False  # Mark as disconnected on error
            raise MBusConnectionError(f"Failed to write data: {e}") from e

    async def read(self, size: int, protocol_timeout: float = 0.0) -> bytes:
        """Read exactly size bytes with protocol-provided base timeout.

        Timeout is calculated as:
        - Protocol-provided base timeout (includes network delays for first byte)
        - Plus transmission time: (size * 10 bits / baudrate) * transmission_multiplier

        The transmission_multiplier accounts for device variations:
        - 1.0 = exact theoretical transmission time
        - 1.2 = 20% extra time for typical devices (default)
        - 1.5+ = for slow or problematic devices

        Args:
            size: Number of bytes to read
            protocol_timeout: Base timeout provided by protocol layer
                            (0.0 means no extra response time needed)

        Returns:
            Exactly size bytes, or empty bytes on timeout

        Note: Protocol layer handles M-Bus timing logic, retries, and network delays.
        """
        if not self._connected or not self._reader:
            raise MBusConnectionError("Transport is not connected")

        try:
            # Read exactly the requested number of bytes with calculated timeout
            data = await asyncio.wait_for(
                self._reader.readexactly(size),
                timeout=self._calculate_timeout(size, protocol_timeout)
            )
            return data
        except TimeoutError:
            # Return empty bytes on timeout (protocol layer handles retries)
            return b""
        except asyncio.IncompleteReadError as e:
            # Return what we got if connection was closed
            return e.partial
        except Exception as e:
            self._connected = False  # Mark as disconnected on error
            raise MBusConnectionError(f"Failed to read data: {e}") from e

    async def __aenter__(self) -> MBusTransport:
        """Async context manager entry."""
        await self.open()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
