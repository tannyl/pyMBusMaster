# pyMBusMaster: Modern Asynchronous M-Bus Library

## Project Vision

Create a modern, async-first Python library for M-Bus (Meter-Bus) communication that addresses the limitations of existing libraries and provides an excellent developer experience for integration into modern applications.

## Current State Analysis

### Limitations of Existing Libraries (pyMeterBus)
- **No async support**: All operations are blocking, unsuitable for modern async applications
- **Confusing API design**: Functions with misleading logic and unclear return types
- **Complex integration**: Not designed for easy integration into frameworks
- **Legacy patterns**: Outdated code patterns that are hard to understand and maintain
- **Mixed responsibilities**: Serial communication mixed with frame parsing in confusing ways

## Design Principles

### 1. Async-First Architecture
- Built from the ground up with `asyncio` support
- Non-blocking serial communication using `pyserial-asyncio`
- Proper async/await patterns throughout the codebase
- Background tasks for continuous monitoring and reading

### 2. Clear Separation of Concerns
- **Transport Layer**: Raw serial communication, connection management, error handling
- **Protocol Layer**: M-Bus frame parsing, validation, and construction
- **Device Layer**: High-level device abstractions and communication patterns
- **Integration Layer**: Easy-to-use APIs for applications and frameworks

### 3. Developer-Friendly Design
- Intuitive, well-documented API with clear method names
- Comprehensive type hints with accurate return types
- Excellent error handling with descriptive messages
- Easy testing and mocking support
- Comprehensive documentation with examples

### 4. Framework Agnostic
- Not tied to any specific framework (Home Assistant, Django, FastAPI, etc.)
- Provides integration helpers and examples for common frameworks
- Clean, extensible architecture for custom integrations

## Technical Architecture

### Core Components

#### Transport Layer (`mbusmaster.transport`)
```python
class MBusTransport:
    """Async serial transport for M-Bus communication"""
    async def open(self) -> None
    async def close(self) -> None
    async def read(self, length: int) -> bytes
    async def write(self, data: bytes) -> int
    async def read_frame(self) -> bytes | None
```

#### Protocol Layer (`mbusmaster.protocol`)
```python
class MBusFrame:
    """Base class for M-Bus frames with parsing and validation"""
    @classmethod
    def parse(cls, data: bytes) -> Self
    def to_bytes(self) -> bytes
    def validate(self) -> bool

class MBusProtocol:
    """Protocol handler for M-Bus communication patterns"""
    async def ping(self, address: int) -> bool
    async def request_data(self, address: int) -> MBusFrame
    async def discover_devices(self) -> list[int]
```

#### Device Layer (`mbusmaster.devices`)
```python
class MBusDevice:
    """High-level device abstraction"""
    def __init__(self, protocol: MBusProtocol, address: int)
    async def read_data(self) -> DeviceData
    async def get_info(self) -> DeviceInfo
    async def monitor(self) -> AsyncIterator[DeviceData]
```

#### Connection Management (`mbusmaster.connection`)
```python
class MBusConnection:
    """Main entry point with connection lifecycle management"""
    async def __aenter__(self) -> MBusProtocol
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None
```

### Example Usage

```python
import asyncio
from mbusmaster import MBusConnection, MBusDevice

async def main():
    # Simple connection management
    async with MBusConnection("/dev/ttyUSB0", baudrate=2400) as protocol:
        # Device discovery
        addresses = await protocol.discover_devices()
        print(f"Found devices at addresses: {addresses}")

        # Simple device interaction
        device = MBusDevice(protocol, address=5)
        data = await device.read_data()
        print(f"Device data: {data}")

        # Continuous monitoring
        async for reading in device.monitor():
            print(f"New reading: {reading}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Home Assistant Integration Example

```python
import asyncio
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from mbusmaster import MBusConnection, MBusDevice

class MBusSensor(Entity):
    def __init__(self, device: MBusDevice):
        self._device = device
        self._state = None

    async def async_update(self):
        try:
            data = await self._device.read_data()
            self._state = data.value
        except Exception as err:
            _LOGGER.error("Failed to read M-Bus device: %s", err)
```

## Technical Decisions

### Dependencies
- **`pyserial-asyncio-fast`**: Async serial communication (maintained Home Assistant fork)
- **`pydantic`**: Data validation and serialization
- **Python 3.13**: Latest Python with newest async features and type hints
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
│   ├── transport/          # Serial transport layer
│   ├── protocol/           # M-Bus protocol implementation
│   ├── devices/            # Device abstractions
│   ├── frames/             # Frame parsing and construction
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

## Development Phases

### Phase 1: Foundation (Weeks 1-2)
- Project setup and structure
- Basic async transport layer
- Core frame parsing (adapted from pyMeterBus)
- Connection management
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