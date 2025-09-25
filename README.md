# pyMBusMaster

Modern async Python library for M-Bus (Meter-Bus) communication.

## Features

- **Async-first**: Built with asyncio for non-blocking serial communication
- **Python 3.13**: Uses the latest Python features and type hints
- **Home Assistant Ready**: Designed for easy integration with Home Assistant
- **Type Safe**: Comprehensive type hints with mypy checking
- **Well Tested**: Comprehensive test suite with pytest

## Quick Start

```python
import asyncio
from mbusmaster import MBusConnection, MBusDevice

async def main():
    async with MBusConnection("/dev/ttyUSB0", baudrate=2400) as protocol:
        # Device discovery
        addresses = await protocol.discover_devices()
        print(f"Found devices at addresses: {addresses}")

        # Simple device interaction
        device = MBusDevice(protocol, address=5)
        data = await device.read_data()
        print(f"Device data: {data}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Installation

```bash
pip install pyMBusMaster
```

## Requirements

- Python 3.13+
- pyserial-asyncio-fast
- pydantic

## License

MIT License - see [LICENSE](LICENSE) for details.

## Development Status

This project is in active development. See [TODO.md](TODO.md) for the development roadmap.