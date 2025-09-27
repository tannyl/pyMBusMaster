# pyMBusMaster: Modern Asynchronous M-Bus Library

## Project Vision

Create a modern, async-first Python library for M-Bus (Meter-Bus) communication. It will act as master on the M-Bus and a gateway which other applications can use to get data from M-Bus devices.

## Design Principles

### 1. Simple and Intuitive API
- **Single Entry Point**: One `MBusMaster` class handles everything
- **No Complex Chains**: Users don't pass objects between methods
- **Direct Results**: Methods return final data, not intermediate objects
- **URL-Style Connections**: Support `socket://host:port` and `/dev/ttyUSB0` formats

### 2. Async-First Architecture
- Built from the ground up with `asyncio` support
- Non-blocking serial communication using `pyserial-asyncio-fast`
- Proper async/await patterns throughout the codebase
- Background connection management

### 3. Hidden Complexity
- **Internal Architecture**: Complex protocol handling happens behind the scenes
- **Smart Defaults**: Reasonable defaults for all configuration
- **Explicit Management**: Connection lifecycle controlled by user with open()/close()
- **Clean API Surface**: Users only see what they need

### 4. Bus Safety and Concurrency
- **Single Operation Chain**: Only one M-Bus operation runs at a time using asyncio locks
- **Automatic Queuing**: Multiple concurrent calls automatically wait their turn
- **No Bus Collisions**: Prevents overlapping requests that would corrupt responses
- **Transparent to Users**: Locking happens internally - users just await their calls

### 5. Framework Agnostic
- Not tied to any specific framework (Home Assistant, Django, FastAPI, etc.)
- Easy integration with any async Python application
- Clean, simple interface for custom integrations

## API Design

### Public API - Simple and Direct

```python
from mbusmaster import MBusMaster

class MBusMaster:
    """Simple, all-in-one M-Bus master interface"""

    def __init__(self, url: str, **options):
        """
        Create M-Bus master with flexible connection options:

        - Serial: "/dev/ttyUSB0", baudrate=2400
        - TCP: "socket://192.168.1.100:10001"
        """

    async def open(self) -> None:
        """Open connection to M-Bus"""

    async def close(self) -> None:
        """Close connection to M-Bus"""

    async def ping_addresses(self, addresses: list[int]) -> dict[int, bool]:
        """Check if meters at addresses respond"""

    async def query_addresses(self, addresses: list[int]) -> dict[int, MBusSlaveData]:
        """Get current readings from meters"""

    async def scan_addresses(self, addresses: list[int]) -> dict[int, MBusSlaveInfo]:
        """Find all responding meters on the bus"""
```

### Internal Architecture (Hidden from Users)

The library internally uses a three-layer architecture but users never interact with these directly:

- **Application Layer** (`master.py`): User-facing API, orchestrates operations, manages bus locking
- **Protocol Layer** (`protocol.py`): M-Bus frame construction, parsing, validation, and data extraction
- **Transport Layer** (`transport.py`): Handles serial/TCP connections and raw byte I/O

Key architectural components:
- **Connection Manager**: Explicit connection management with open()/close() methods
- **Bus Lock Manager**: Uses `asyncio.Lock()` to ensure only one operation chain runs at a time

#### Bus Safety Implementation

```python
# Internal implementation (hidden from users)
class MBusMaster:
    def __init__(self, url: str, **options):
        self._bus_lock = asyncio.Lock()  # One operation at a time

    async def ping_addresses(self, addresses: list[int]) -> dict[int, bool]:
        async with self._bus_lock:  # Automatic queuing
            results = {}
            for address in addresses:
                # Send ping frame and wait for response
                results[address] = await self._ping_single(address)
            return results

    async def query_addresses(self, addresses: list[int]) -> dict[int, MBusSlaveData]:
        async with self._bus_lock:  # Waits for ping_addresses to finish
            results = {}
            for address in addresses:
                # Send request frame and parse response
                results[address] = await self._query_single(address)
            return results
```

This ensures that even if multiple sensors in Home Assistant call `query_addresses()` simultaneously, they execute in sequence without corrupting each other's data.

### Data Structures

```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

class MBusSlaveInfo(BaseModel):
    """Base information about an M-Bus slave device (meter)"""

    # Identification
    serial_number: str          # Unique meter serial number
    manufacturer: str           # Manufacturer code (e.g., "KAM" for Kamstrup)
    version: int                # Device version/generation
    device_type: str            # Device type description

    # Medium information
    medium: str                 # What the meter measures: "electricity", "water", "gas", "heat"

    # Status
    status: int                 # Status byte from meter
    access_number: int          # Counter incremented with each telegram

    # Optional extended info
    firmware_version: str | None = None
    hardware_version: str | None = None


class MBusRecordType(str, Enum):
    """Types of data records that can be returned by M-Bus devices"""
    ENERGY = "energy"
    POWER = "power"
    VOLUME = "volume"
    FLOW = "flow"
    TEMPERATURE = "temperature"
    VOLTAGE = "voltage"
    CURRENT = "current"
    FREQUENCY = "frequency"
    PRESSURE = "pressure"
    TIME = "time"
    DATE = "date"
    ERROR = "error"
    OTHER = "other"


class MBusRecordFunction(str, Enum):
    """Function codes for M-Bus data records"""
    INSTANTANEOUS = "instantaneous"
    MAXIMUM = "maximum"
    MINIMUM = "minimum"
    ERROR_STATE = "error"


class MBusSlaveRecord(BaseModel):
    """Individual data record from an M-Bus device

    M-Bus devices return multiple records, each containing a specific
    measurement or value with its own metadata.
    """

    # What this record represents
    type: MBusRecordType        # Type of measurement
    description: str             # Human-readable description

    # The actual data
    value: float | int | str     # The value (can be numeric or string)
    unit: str                    # Unit of measurement (kWh, m³, °C, etc.)

    # M-Bus specific metadata
    storage_number: int = 0      # Storage/tariff number (0 = current, 1-15 = historical)
    function: MBusRecordFunction = MBusRecordFunction.INSTANTANEOUS
    device_unit: int = 0         # Device unit number (for multi-channel devices)

    # Optional extended info
    timestamp: datetime | None = None  # If record has specific timestamp


class MBusSlaveData(MBusSlaveInfo):
    """Complete meter data including identification and all data records

    Inherits all identification fields from MBusSlaveInfo and adds
    the actual measurement records returned by the device.
    """

    # When the data was read
    timestamp: datetime

    # All data records from the device
    records: list[MBusSlaveRecord]

    def get_record(self, type: MBusRecordType, storage: int = 0) -> MBusSlaveRecord | None:
        """Helper to find specific record by type and storage number"""
        for record in self.records:
            if record.type == type and record.storage_number == storage:
                return record
        return None

    def get_all_records(self, type: MBusRecordType) -> list[MBusSlaveRecord]:
        """Helper to get all records of a specific type"""
        return [r for r in self.records if r.type == type]
```

#### Usage Examples

```python
# scan_addresses returns just MBusSlaveInfo
scan_results = await master.scan_addresses([1, 2, 3])
for addr, info in scan_results.items():
    if info:
        print(f"Meter {addr}: {info.manufacturer} {info.serial_number}")
        print(f"  Type: {info.medium}")

# query_addresses returns full MBusSlaveData with all records
data_results = await master.query_addresses([1, 2, 3])
for addr, data in data_results.items():
    if data:
        # Access identification (inherited from MBusSlaveInfo)
        print(f"Meter {addr}: {data.serial_number}")
        print(f"  Manufacturer: {data.manufacturer}")

        # Access all records
        for record in data.records:
            print(f"  {record.description}: {record.value} {record.unit}")

        # Find specific records
        energy = data.get_record(MBusRecordType.ENERGY)
        if energy:
            print(f"  Energy: {energy.value} {energy.unit}")

        # Get all temperature records (flow and return for heat meters)
        temps = data.get_all_records(MBusRecordType.TEMPERATURE)
        for temp in temps:
            print(f"  {temp.description}: {temp.value} {temp.unit}")
```

This flexible structure means:
- M-Bus devices can return any number and type of records
- Each record is self-describing with type, unit, and metadata
- Helper methods make it easy to find specific values
- Supports multi-tariff meters (using storage_number)
- Handles device-specific and future record types

### Example Usage

```python
import asyncio
from mbusmaster import MBusMaster

async def main():
    # Connect to M-Bus gateway via TCP
    master = MBusMaster("socket://ethmbus.de-la.dk:10001")
    await master.open()  # Explicit connection

    # Ping single meter
    results = await master.ping_addresses([5])
    if results[5]:
        print("Meter 5 is responding!")

    # Ping multiple meters at once
    results = await master.ping_addresses([1, 5, 10, 15])
    for addr, responding in results.items():
        print(f"Meter {addr}: {'OK' if responding else 'No response'}")

    # Get meter data
    data_dict = await master.query_addresses([5])
    data = data_dict[5]
    if data:
        # Use the flexible record structure
        energy = data.get_record(MBusRecordType.ENERGY)
        if energy:
            print(f"Energy: {energy.value} {energy.unit}")
        power = data.get_record(MBusRecordType.POWER)
        if power:
            print(f"Power: {power.value} {power.unit}")

    # Query multiple meters efficiently
    all_data = await master.query_addresses([1, 5, 10])
    for addr, data in all_data.items():
        if data:
            energy = data.get_record(MBusRecordType.ENERGY)
            if energy:
                print(f"Meter {addr}: {energy.value} {energy.unit}")

    # Scan for all meters on specific addresses
    scan_results = await master.scan_addresses(range(1, 251))
    found_meters = [addr for addr, info in scan_results.items() if info is not None]
    print(f"Found meters at: {found_meters}")

    # Close connection when done
    await master.close()

# Serial connection example with context manager
async def serial_example():
    async with MBusMaster("/dev/ttyUSB0", baudrate=2400) as master:
        # Connection opened automatically
        results = await master.query_addresses([1, 2, 3])
        for addr, data in results.items():
            print(f"Meter {addr}: {data}")
        # Connection closed automatically

if __name__ == "__main__":
    asyncio.run(main())
```

## Technical Decisions

### Dependencies
- **Python 3.13**: Latest Python with newest async features and type hints
- **`pyserial-asyncio-fast`**: Async serial communication (maintained Home Assistant fork)
- **`pydantic`**: Data validation and serialization
- **`pytest-asyncio`**: Async testing framework

### Development Tools
- **`ruff`**: Linting and formatting
- **`mypy`**: Static type checking
- **`pytest`**: Testing framework
- **`sphinx`**: Documentation generation

### Project Structure
```
pyMBusMaster/
├── .devcontainer/          # Development container configuration
├── src/mbusmaster/         # Main package
│   ├── transport.py        # Transport layer implementation
│   ├── protocol.py         # M-Bus protocol, frames, and data parsing
│   ├── master.py           # MBusMaster main class
│   ├── exceptions.py       # Custom exceptions
│   └── __init__.py         # Public API exports
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── conftest.py         # Test configuration
├── docs/                   # Documentation
│   ├── api/                # API documentation
│   ├── examples/           # Usage examples
│   └── integration/        # Framework integration guides
├── examples/               # Example applications
│   ├── basic/              # Basic usage examples
│   ├── home_assistant/     # Home Assistant integration
│   └── monitoring/         # Continuous monitoring examples
├── PLAN.md                 # This document
├── TODO.md                 # Development roadmap
├── README.md               # Project introduction
└── pyproject.toml          # Project configuration
```

## Transport Layer Design

### Connection Management Philosophy
- **Explicit lifecycle**: User controls connection with `open()` and `close()` methods
- **Early validation**: Connection tested at `open()`, not during first data operation
- **Single transport class**: Leverages `pyserial-asyncio-fast` for all connection types
- **Clean separation**: Transport handles connections and raw I/O, protocol layer handles M-Bus specifics

### Transport Layer Architecture

#### MBusTransport Class
```python
class MBusTransport:
    """Handles connection and raw byte I/O for M-Bus communication."""

    def __init__(self, url: str, baudrate: int = 2400, timeout_margin: float = 0.5, **kwargs):
        """
        Initialize transport (does not open connection).

        Args:
            url: Connection URL (serial port or socket)
            baudrate: Baud rate for serial connections
            timeout_margin: Extra time (seconds) to add to calculated timeouts
                           for slow/problematic devices (default 0.5s)
            **kwargs: Additional serial parameters
        """
        # Store connection parameters
        # Initialize reader/writer as None

    async def open(self) -> None:
        """Open connection. Raises MBusConnectionError on failure."""
        # Use serial_asyncio.open_serial_connection()
        # Set connected flag

    async def close(self) -> None:
        """Close connection (idempotent)."""
        # Close writer, wait for close
        # Clear reader/writer references

    def is_connected(self) -> bool:
        """Check connection status."""

    async def write(self, data: bytes) -> None:
        """Write raw bytes to transport."""
        # Check connected, write data, drain

    async def read(self, size: int) -> bytes:
        """
        Read exactly size bytes with automatically calculated timeout.

        Timeout is calculated based on:
        - Physics: (size * 10 bits / baudrate) for transmission time
        - Plus timeout_margin for processing delays
        - Automatically adds extra margin for socket connections

        Returns:
            Exactly size bytes, or empty bytes on timeout
        """
        # Calculate timeout:
        # transmission_time = (size * 10) / self.baudrate
        # timeout = transmission_time + self.timeout_margin
        # For socket URLs, add extra network margin
        # Use reader.readexactly(size) with asyncio.wait_for(timeout)
        # Return empty bytes on timeout
```

#### Connection URL Support
- **Serial ports**: `/dev/ttyUSB0`, `COM3`
- **TCP sockets**: `socket://192.168.1.100:10001`
- **RFC2217**: `rfc2217://192.168.1.100:10001`
- All handled transparently by `pyserial-asyncio-fast`

### MBusMaster Integration

```python
class MBusMaster:
    def __init__(self, url: str, timeout_margin: float = 0.5, **options):
        """
        Initialize master (no connection yet).

        Args:
            url: Connection URL
            timeout_margin: Extra seconds added to calculated timeouts
                          Increase for slow/problematic devices
            **options: Additional options (baudrate, etc.)
        """
        self.transport = MBusTransport(url, timeout_margin=timeout_margin, **options)

    async def open(self) -> None:
        """Open M-Bus connection."""
        await self.transport.open()

    async def close(self) -> None:
        """Close M-Bus connection."""
        await self.transport.close()

    # Context manager support
    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
```

### Usage Patterns

#### Explicit Management
```python
master = MBusMaster("/dev/ttyUSB0")
await master.open()  # Test connection early
# ... use master ...
await master.close()
```

#### Context Manager
```python
async with MBusMaster("/dev/ttyUSB0") as master:
    # Connection opened automatically
    # ... use master ...
# Connection closed automatically
```

#### Connection Testing
```python
master = MBusMaster("/dev/ttyUSB0")
try:
    await master.open()
    print("Connected!")
except MBusConnectionError:
    print("Connection failed")
```

### Benefits
- **Fail early**: Connection problems detected immediately at `open()`
- **Resource control**: User decides when to allocate/free serial port
- **Clean errors**: Separate connection errors from protocol errors
- **Persistent connection**: Efficient for multiple operations
- **Simple implementation**: One transport class for all connection types

## Protocol Layer Design

### Telegram Class Architecture

The protocol layer uses a class-based approach to represent M-Bus telegrams, making the code clean, type-safe, and maintainable.

#### Base Telegram Class
```python
class MBusTelegram:
    """Base class for all M-Bus telegrams"""

    def to_bytes(self) -> bytes:
        """Serialize telegram to bytes for sending"""
        raise NotImplementedError

    @classmethod
    def from_bytes(cls, data: bytes) -> "MBusTelegram":
        """Parse bytes into telegram object"""
        raise NotImplementedError

    def calculate_checksum(self, data: bytes) -> int:
        """Calculate M-Bus checksum"""
        return sum(data) & 0xFF
```

#### Outgoing Telegrams (Master → Slave)
```python
class ShortFrame(MBusTelegram):
    """Short frame for master commands (5 bytes)"""

    def __init__(self, c_field: int, address: int):
        self.c_field = c_field
        self.address = address

    def to_bytes(self) -> bytes:
        # Build: 0x10 | C | A | Checksum | 0x16

class SndNke(ShortFrame):
    """Reset/Initialize slave command"""
    def __init__(self, address: int):
        super().__init__(c_field=0x40, address=address)

class ReqUD2(ShortFrame):
    """Request user data with FCB management"""
    def __init__(self, address: int, fcb: bool = False):
        c_field = 0x7B if fcb else 0x5B  # Toggle FCB bit
        super().__init__(c_field=c_field, address=address)
```

#### Incoming Telegrams (Slave → Master)
```python
class AckFrame(MBusTelegram):
    """Single byte acknowledgment (0xE5)"""

    @classmethod
    def from_bytes(cls, data: bytes) -> "AckFrame":
        # Validate ACK byte

class LongFrame(MBusTelegram):
    """Variable length frame with user data"""

    def __init__(self, c_field: int, address: int, ci_field: int, data: bytes):
        self.c_field = c_field
        self.address = address
        self.ci_field = ci_field
        self.data = data

    @classmethod
    def from_bytes(cls, data: bytes) -> "LongFrame":
        # Parse: 0x68 | L | L | 0x68 | C | A | CI | Data | Check | 0x16
        # Validate structure and checksum
        # Extract fields

    def parse_data(self) -> MBusSlaveData:
        """Parse user data into structured MBusSlaveData"""
        # Parse DIFs, VIFs, extract measurement records
```

#### Telegram Factory
```python
class TelegramFactory:
    """Factory for parsing incoming telegrams"""

    @staticmethod
    def parse(data: bytes) -> MBusTelegram:
        """Determine telegram type and parse accordingly"""
        # Identify by first byte: 0xE5 (ACK), 0x68 (Long), etc.
```

### Protocol Layer Integration
```python
class MBusProtocol:
    """Protocol layer handling frame construction and parsing"""

    def __init__(self):
        self.fcb_state = {}  # Track FCB per address

    def build_reset_frame(self, address: int) -> bytes:
        """Build SND_NKE reset frame"""
        return SndNke(address).to_bytes()

    def build_request_frame(self, address: int) -> bytes:
        """Build REQ_UD2 frame with FCB management"""
        # Toggle FCB for this address
        fcb = self.fcb_state.get(address, False)
        frame = ReqUD2(address, fcb)
        self.fcb_state[address] = not fcb
        return frame.to_bytes()

    def parse_response(self, data: bytes) -> MBusTelegram | MBusSlaveData | None:
        """Parse response from slave"""
        if not data:
            return None

        telegram = TelegramFactory.parse(data)

        if isinstance(telegram, LongFrame):
            return telegram.parse_data()  # Return structured data

        return telegram  # Return ACK or other telegram types
```

### Frame Reading Strategy

The protocol layer also handles intelligent frame reading from the transport:

```python
async def read_frame(self, transport: MBusTransport) -> bytes:
    """Read complete M-Bus frame based on type"""
    # Read first byte to determine frame type
    first = await transport.read(1)

    if first == b'\xE5':
        return first  # ACK - single byte
    elif first == b'\x10':
        rest = await transport.read(4)  # Short frame - 4 more bytes
        return first + rest
    elif first == b'\x68':
        # Long frame - read L-fields to determine length
        header = await transport.read(3)
        length = header[0]
        rest = await transport.read(length + 2)  # data + checksum + stop
        return first + header + rest
```

### Benefits of This Design

1. **Type Safety**: Each telegram type is a distinct class
2. **Separation of Concerns**: Construction vs parsing clearly separated
3. **FCB Management**: Automatic Frame Count Bit tracking
4. **Extensibility**: Easy to add new telegram types or commands
5. **Testability**: Each class can be unit tested independently
6. **Clean API**: Consistent `to_bytes()`/`from_bytes()` pattern

## Development Phases

### Phase 1: Foundation (Weeks 1-2)
- Project setup and structure
- Basic async transport layer with explicit connection management
- Core frame parsing (adapted from pyMeterBus)
- Connection management implementation
- Basic test suite

### Phase 2: Protocol Implementation (Weeks 3-4)
- M-Bus protocol implementation
- Device discovery
- Error handling and recovery
- Comprehensive testing

### Phase 3: Device Abstraction (Weeks 5-6)
- High-level device API
- Data parsing and validation
- Monitoring capabilities
- Documentation

### Phase 4: Integration Support (Weeks 7-8)
- Framework integration helpers
- Home Assistant integration example
- Additional examples
- Performance optimization

## Success Criteria

### Technical
- **Non-blocking**: All operations are truly async
- **Reliable**: Robust error handling and recovery
- **Fast**: Efficient protocol implementation
- **Type-safe**: Comprehensive type hints
- **Well-tested**: >90% test coverage

### Developer Experience
- **Easy to integrate**: Simple, intuitive API
- **Well-documented**: Clear documentation with examples
- **Framework-friendly**: Easy integration with popular frameworks
- **Maintainable**: Clean, readable code structure

### Community
- **Open source**: MIT licensed for maximum compatibility
- **Community-driven**: Accept contributions and feedback
- **Stable**: Semantic versioning and backward compatibility
- **Supported**: Regular updates and bug fixes

## Future Considerations

### Potential Extensions
- **Wireless M-Bus support**: Extend to support wM-Bus protocol
- **Multiple transports**: Support TCP, USB, Bluetooth transports
- **Device-specific drivers**: Specialized drivers for common meter types
- **Protocol analyzers**: Tools for debugging and protocol analysis
- **GUI tools**: Desktop applications for meter configuration

### Performance Optimizations
- **Connection pooling**: Manage multiple serial connections
- **Caching**: Intelligent caching of device information
- **Batch operations**: Optimize multiple device reads
- **Background monitoring**: Efficient continuous data collection

This plan provides the foundation for creating a modern, maintainable M-Bus library that addresses current limitations while being extensible for future needs.

---

# M-Bus Protocol Overview

Based on comprehensive research of the M-Bus protocol documentation (MBDOC48.PDF), pyMeterBus implementation, and libmbus C library.

## What is M-Bus?

**M-Bus (Meter-Bus)** is a European standard (EN 13757-2) for remote reading of gas, electricity, water, and heat meters. It enables centralized data collection from utility meters using a two-wire bus system that carries both power and data.

## Architecture & Communication Model

M-Bus follows a **master-slave architecture**:
- **Master**: Central unit that initiates all communication (typically a data collector)
- **Slaves**: Individual meters that respond only when addressed
- **Bus topology**: Up to 250 slaves on a single bus segment
- **Half-duplex communication**: Only one device transmits at a time

## Physical Layer

### Power & Communication
- **Single two-wire bus** carries both power and data
- **Voltage modulation**: 24V (mark/1) to 36V (space/0)
- **Current modulation**: 1.5mA (mark/1) to 22mA (space/0)
- **Maximum distance**: 350m per segment
- **Baud rates**: 300, 600, 1200, 2400, 4800, 9600 bps (typically 2400)
- **Bus-powered slaves**: Meters draw power from the bus itself

### Electrical Characteristics
- Masters provide 24-42V DC to the bus
- Slaves modulate current consumption to send data
- Built-in protection against short circuits and polarity reversal

## Data Link Layer - Telegram Formats

M-Bus defines four telegram types for different communication needs:

### 1. Single Character (1 byte)
- **ACK (0xE5)**: Acknowledgment of successful reception
- Used for simple confirmations

### 2. Short Frame (5 bytes)
```
Start | C-Field | A-Field | Checksum | Stop
0x10  | Control | Address | Sum      | 0x16
```
- Control commands without data payload
- Examples: SND_NKE (reset), REQ_UD1 (request user data)

### 3. Control Frame (9 bytes)
```
Start | C-Field | A-Field | CI-Field | 4 Data Bytes | Checksum | Stop
0x68  | Control | Address | App Code | Data         | Sum      | 0x16
```
- Commands with fixed 4-byte data payload

### 4. Long Frame (variable length)
```
Start | L-Field | L-Field | Start | C-Field | A-Field | CI-Field | Data | Checksum | Stop
0x68  | Length  | Length  | 0x68  | Control | Address | App Code | ...  | Sum      | 0x16
```
- Data transmission with variable payload (3-252 bytes)
- Most common for meter data responses

### Frame Fields Explained
- **L-Field**: Data length (excludes start, length, and stop bytes)
- **C-Field**: Control information (direction, function, frame count bit)
- **A-Field**: Primary address (1-250, or 0 for broadcast)
- **CI-Field**: Application layer control information
- **Checksum**: Arithmetic sum of all bytes from C-Field to last data byte

## Application Layer - Data Structures

The application layer defines how measurement data is encoded and transmitted.

### Fixed Data Structure
Standardized 4-byte format for basic meter values:
- **Identification Number**: 32-bit BCD encoded
- **Access Number**: Sequential counter (0-255)
- **Status**: Device status flags
- **Medium and Unit**: Type of measurement

### Variable Data Structure (Most Common)
Flexible format allowing multiple measurements in one telegram:

#### Data Information Field (DIF)
- **Function**: Instantaneous, maximum, minimum, error state
- **Data Type**: Integer, real, string, date, etc.
- **Storage Number**: Tariff register (0=current, 1-15=historical)
- **Extension**: Indicates if more DIF bytes follow

#### Value Information Field (VIF)
- **Unit**: Physical unit (Wh, m³, °C, W, etc.)
- **Multiplier**: Scaling factor (×10⁻³ to ×10⁶)
- **Extension**: Manufacturer-specific or alternative units

#### Data Format Example
```
DIF | VIF | Data | DIF | VIF | Data | ...
04  | 13  | 1234 | 02  | 5B  | 20   | ...
```
- DIF 04: 32-bit integer, storage 0, instantaneous
- VIF 13: Energy in Wh × 10⁻³ (= Wh)
- Data: 0x1234 = 4660 Wh
- DIF 02: 16-bit integer, storage 0, instantaneous
- VIF 5B: Flow temperature in °C
- Data: 0x20 = 32°C

### Common Measurement Types
- **Energy**: Wh, kWh, MWh, GJ, MJ
- **Volume**: m³, l (water, gas)
- **Mass**: kg, t
- **Power**: W, kW, MW
- **Flow rates**: m³/h, l/h, kg/h
- **Temperature**: °C (flow, return, difference)
- **Time/Date**: Timestamps for readings
- **Pressure**: bar, Pa
- **Voltage/Current**: V, A (for electrical meters)

## Network Layer - Addressing

### Primary Addressing
**Direct communication** using 1-byte address:
- Address range: 1-250 (0 = broadcast, 255 = invalid)
- Fast and simple for known meter locations
- Address must be pre-configured in each meter

### Secondary Addressing
**Identification-based** using 8-byte meter ID:
- **Manufacturer ID**: 2 bytes (3-letter code encoded)
- **Serial number**: 4 bytes (BCD or binary)
- **Version**: 1 byte (firmware/hardware version)
- **Medium type**: 1 byte (electricity, gas, water, heat, etc.)

Example secondary address: `KAM 12345678 V01 Heat`

### Wildcard Searching
Master can discover unknown devices using partial addresses:
- Use 0xF as wildcard in any position
- Example: `??? ???????? ??? Heat` finds all heat meters
- Enables automatic device discovery on installation

### Selection Process
1. Master sends SELECT with secondary address/wildcard
2. Matching slaves prepare to respond to primary address 0xFD
3. Master can then communicate using primary address 0xFD
4. After communication, slaves return to normal state

## Communication Procedures

### Standard Data Collection Process
1. **Reset**: Master sends SND_NKE (reset) to slave
2. **Acknowledge**: Slave responds with ACK (0xE5)
3. **Request**: Master requests data with REQ_UD2
4. **Response**: Slave sends RSP_UD telegram with measurements
5. **Confirm**: Master acknowledges with ACK

### Frame Count Bit (FCB) Mechanism
- **Alternating bit** in C-Field ensures data integrity
- Master toggles FCB with each new request
- Slave compares FCB to detect retransmissions
- Prevents duplicate data processing

### Error Handling
- **Timeouts**: No response within defined time
- **Checksum errors**: Invalid frame structure
- **FCB mismatch**: Frame sequence errors
- **Collision detection**: Multiple slaves responding

### Bus Collision Avoidance
- Only master initiates communication
- Slaves respond only when directly addressed
- Built-in delays prevent bus conflicts
- Collision detection through current monitoring

## Implementation Insights

### From pyMeterBus (Python Implementation)
**Strengths:**
- Focus on telegram parsing and serial communication
- JSON output for easy integration
- Support for both fixed and variable data structures
- Heat/cooling meter specialization
- Good documentation and examples

**Architecture:**
- Modular design with separate parsing components
- Event-driven telegram processing
- Support for multiple transport layers

### From libmbus (C Library Implementation)
**Strengths:**
- Low-level frame handling and protocol implementation
- Comprehensive error handling and recovery
- Support for multiple communication interfaces
- Production-ready reliability and performance
- Cross-platform compatibility

**Architecture:**
- Layered protocol stack
- State machine for connection management
- Memory-efficient data structures

### Key Implementation Considerations
1. **Timing sensitivity**: M-Bus has strict timing requirements
2. **Bus power management**: Slaves may lose power during communication
3. **Noise tolerance**: Industrial environments require robust error handling
4. **Device diversity**: Wide variety of meter types and manufacturers
5. **Backward compatibility**: Support for older meter firmware

## Protocol Features & Benefits

### Self-Describing Data
- **VIF codes** make telegrams interpretable without external configuration
- Units and scaling factors embedded in the data
- Future-proof for new measurement types

### Robust Error Detection
- **Checksum validation** on every frame
- **Frame count verification** prevents duplicates
- **Timeout mechanisms** handle non-responsive devices
- **Retransmission protocols** ensure data delivery

### Flexible Addressing
- **Primary addressing** for performance
- **Secondary addressing** for flexibility
- **Wildcard discovery** for automatic installation
- **Multi-drop capability** up to 250 devices

### Power Efficiency
- **Bus-powered operation** eliminates external power
- **Low current consumption** for battery-operated devices
- **Sleep modes** for energy conservation

### Standardized Implementation
- **European standard EN 13757-2** ensures compatibility
- **Comprehensive unit coding** system covers all measurement types
- **Manufacturer independence** through standardized protocols
- **Interoperability** between different vendor devices

## Real-World Applications

### Residential Metering
- Multi-apartment buildings with centralized reading
- Individual meter monitoring for energy management
- Automatic meter reading (AMR) systems

### Commercial/Industrial
- Factory energy monitoring and submetering
- District heating/cooling networks
- Water distribution system monitoring

### Smart Grid Integration
- Building energy management systems (BEMS)
- Demand response applications
- Energy efficiency monitoring

### Use in Home Assistant
This protocol understanding directly supports the pyMBusMaster library design:
- **Async operation** prevents blocking Home Assistant
- **Multiple meter support** for comprehensive monitoring
- **Automatic discovery** simplifies configuration
- **Standardized data format** enables consistent entity creation
- **Error resilience** maintains system stability

## Technical Challenges & Solutions

### Challenge: Bus Timing
**Problem**: M-Bus requires precise timing between request and response
**Solution**: Implement hardware-accurate timeouts and retry mechanisms

### Challenge: Device Diversity
**Problem**: Different manufacturers implement protocol variations
**Solution**: Comprehensive testing with real devices and fallback parsing

### Challenge: Error Recovery
**Problem**: Communication errors can leave bus in inconsistent state
**Solution**: State machine with proper reset sequences and error detection

### Challenge: Concurrent Access
**Problem**: Multiple applications accessing the same bus cause collisions
**Solution**: Bus locking mechanism ensures sequential access (implemented in pyMBusMaster)

## Summary

M-Bus is a mature, standardized protocol that enables reliable utility meter communication over a simple two-wire interface. Its self-describing data format, flexible addressing, and robust error handling make it ideal for both simple residential installations and complex industrial monitoring systems.

The protocol's design principles of simplicity, reliability, and standardization align perfectly with the goals of the pyMBusMaster library - providing a modern, async Python interface while maintaining compatibility with the extensive ecosystem of M-Bus devices deployed worldwide.

Understanding these protocol fundamentals is essential for implementing a robust M-Bus master that can handle the diversity and complexity of real-world meter installations while providing a simple, reliable interface for applications like Home Assistant.