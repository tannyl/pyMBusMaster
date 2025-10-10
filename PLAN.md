# pyMBusMaster Architecture Plan

## Overview

This document describes the architecture for pyMBusMaster, a modern async Python library for M-Bus (Meter-Bus) communication. The design prioritizes simplicity, testability, and separation of concerns while supporting the full M-Bus protocol.

## Design Philosophy

- **Separation of concerns**: Each layer has a single, clear responsibility
- **Testability**: Pure functions where possible, easy to mock dependencies
- **Async-first**: Built with asyncio throughout
- **Type-safe**: Comprehensive type hints for all interfaces
- **Simple API**: Hide complexity from end users

## Architecture Layers

The library is organized into 4 layers, from low-level to high-level:

```
┌─────────────────────────────────────────┐
│     Layer 4: Master (master.py)         │  ← User-facing API
│  "read_meter(address) -> MeterData"     │
└─────────────────────────────────────────┘
                  ↓ uses
┌─────────────────────────────────────────┐
│    Layer 3: Session (session.py)        │  ← Communication orchestration
│  "Send/receive telegrams with retries"  │
│  "Handle multi-telegram sequences"      │
└─────────────────────────────────────────┘
                  ↓ uses
┌─────────────────────────────────────────┐
│   Layer 2: Protocol (protocol.py)       │  ← Encode/decode/validate
│  "Encode: params -> bytes"              │
│  "Decode: bytes -> structured data"     │
└─────────────────────────────────────────┘
                  ↓ uses
┌─────────────────────────────────────────┐
│   Layer 1: Transport (transport.py)     │  ← Raw byte I/O
│  "write(bytes), read(size) -> bytes"    │  ✅ Already implemented
└─────────────────────────────────────────┘
```

---

## Layer 1: Transport Layer ✅

**File**: `transport.py`
**Status**: ✅ Complete and tested

### Responsibility
Raw byte I/O and connection management. No knowledge of M-Bus protocol or telegram structure.

### Key Features
- Support for serial ports, TCP sockets, and RFC2217
- Automatic timeout calculation based on baud rate and byte size
- Connection state management
- Input buffer clearing before writes
- Smart transmission time calculation with configurable multiplier

### Public API
```python
class Transport:
    async def open() -> None
    async def close() -> None
    def is_connected() -> bool
    async def write(data: bytes) -> None
    async def read(size: int, protocol_timeout: float = 0.0) -> bytes
```

### Design Notes
- Idempotent operations (safe to call open/close multiple times)
- Returns empty bytes on timeout (no exceptions)
- Marks connection as failed on errors
- Clears input buffer before each write to prevent stale data

---

## M-Bus Protocol Constants

**File**: `constants.py`
**Status**: 🚧 To be implemented

### Purpose

Extract all M-Bus protocol constant values from EN 13757-3:2018 specification into a single, well-organized constants file. This provides:
- **Single source of truth** for all protocol constants
- **No magic numbers** in code
- **Easy reference** during implementation
- **Spec traceability** with comments linking to specification sections

### Constant Categories

Based on EN 13757-3:2018, the following constant categories will be extracted:

#### 1. Frame Structure Constants
- Frame start bytes: Long frame (0x68), Short frame (0x10), ACK (0xE5)
- Frame stop byte (0x16)

#### 2. Address Constants
- Special addresses: Broadcast (0xFF), No station (0xFE), Reserved (0xFD)
- Normal address range: 0-250

#### 3. C-Field (Control Field) Values
- Command codes from EN 13757-2: SND_NKE, REQ_UD2, REQ_UD1, SND_UD, RSP_UD, etc.

#### 4. CI-Field (Control Information) Values
- Application layer protocol identifiers from EN 13757-3:2018
- Variable data structure codes and other protocol identifiers

#### 5. DIF (Data Information Field) Constants
- Data type codes from Table 4: integers, BCD, real, variable length, etc.
- Special function codes from Table 6: manufacturer data, more records follow, idle filler, global readout
- Function field codes from Table 7: instantaneous, maximum, minimum, error state

#### 6. LVAR (Variable Length) Constants
- Interpretation ranges from Table 5: text strings, positive/negative BCD, binary numbers

#### 7. VIF (Value Information Field) Constants
- Primary VIF codes from Table 10: energy, volume, mass, power, temperature, pressure, flow, etc.
- Special VIF codes from Table 11: plain text, extensions, etc.
- VIFE extension codes from Tables 12-16: multipliers, combinable codes, etc.

#### 8. Device Type Constants
- M-Bus device types: water, gas, heat, electricity, breaker, valve, etc.

#### 9. BCD Error Codes
- Non-BCD hex codes for error signaling from Annex B

### Benefits

1. **Code clarity**: No magic numbers like `if byte == 0x68:`
   - Instead: `if byte == FRAME_START_LONG:`

2. **Easy maintenance**: Update constants in one place

3. **Spec compliance**: Comments reference exact specification sections

4. **IDE support**: Autocomplete and type hints for all constants

5. **Testing**: Easy to verify constants match specification

### Implementation Priority

This file should be implemented **first** before any other Protocol layer code, as all encoders/decoders will reference these constants.

### Implementation Approach

**Strategy**: Complete `constants.py` as thoroughly as possible upfront by systematically going through all tables in EN 13757-3:2018 and extracting constant values.

**Steps**:
1. Go through specification tables systematically (Tables 1-18, Annexes)
2. Extract all constant values into appropriate classes/enums
3. Add comments with specification table references
4. If we discover problems or missing constants during Protocol layer implementation, we update the file

**Why this approach**:
- All constants available from the start
- Less context switching later
- Clear overview of what the spec contains
- Can fix/adjust as needed during implementation

---

## Layer 2: Protocol Layer

**File**: `protocol.py`
**Status**: 🚧 To be implemented (requires `constants.py` first)

### Responsibility
Pure encode/decode/validate operations for M-Bus telegrams. This layer is stateless and performs only data transformations.

### Key Responsibilities
1. **Encoding**: Convert parameters to bytes ready for transmission
2. **Decoding**: Parse raw bytes into structured data objects
3. **Validation**: Verify checksums, frame structure, telegram types
4. **Metadata extraction**: Multi-telegram flags, status bytes, error codes

### Important Principles
- **Pure functions**: No I/O, no state, no side effects
- **Immediate validation**: Decode and validate received data immediately
- **Expected type checking**: Decoder knows what telegram type to expect
- **Exception on mismatch**: Throws error if received data doesn't match expected type

### Telegram Types
Based on EN 13757-3:2018, the protocol supports these telegram types:

- **ACK** (E5h): Single character acknowledgment
- **Short Frame**: C-field + A-field + checksum (no data)
- **Long Frame**: Full frame with CI-field and data payload
- **Control Frame**: Used for specific commands

### Commands (C-field values)
- `SND_NKE (40h)`: Send Link Reset - Initialize/reset device
- `REQ_UD2 (5Bh)`: Request User Data (Class 2) - Request meter data
- `REQ_UD1 (5Ah)`: Request User Data (Class 1) - Request alarm data
- `SND_UD (53h)`: Send User Data - Send configuration/commands to meter
- `RSP_UD`: Response User Data - Device response with data

### Progressive Decoding Strategy

Instead of reading all bytes at once and then validating, we use progressive decoding:

1. **Read small chunks** (1-2 bytes at a time)
2. **Validate immediately** after each read
3. **Decoder tells Session** how many bytes to read next
4. **Fail fast** if anything is wrong

**Example: Long Frame Decoding Flow**
```
Step 1: Read 1 byte
  → Got: 0x68 (START byte)
  → Validate: Is this expected frame type? ✓
  → Decoder state: "Need 2 bytes for L-field"

Step 2: Read 2 bytes
  → Got: 0x1F 0x1F (length = 31)
  → Validate: Do both L-fields match? ✓
  → Calculate: Total payload size
  → Decoder state: "Need 1 byte for second START"

Step 3: Read 1 byte
  → Got: 0x68 (second START)
  → Validate: Correct? ✓
  → Decoder state: "Need 1 byte for C-field"

... continues progressively...

Step N: Final validation
  → All bytes received
  → Validate: Checksum correct? ✓
  → Parse: Extract has_more_telegrams flag
  → Return: Complete Telegram object
```

**Advantages:**
- **Fail fast**: Detect errors immediately, don't waste time reading bad data
- **Efficient**: Only read what we need based on validated state
- **Clear state**: Decoder tracks exactly where we are in the frame
- **Better timeouts**: Each small read has appropriate timeout
- **Progressive validation**: Each field validated as we go

### Key Classes

#### Encoding (Simple - Pure Functions)
```python
class TelegramEncoder:
    """Encodes telegrams into bytes for transmission (stateless)"""

    @staticmethod
    def encode_snd_nke(address: int) -> bytes:
        """
        Build SND_NKE telegram (device reset).

        Returns short frame: START + C + A + CHECKSUM + STOP
        Example: 10 40 05 45 16 (reset device at address 5)
        """

    @staticmethod
    def encode_req_ud2(address: int) -> bytes:
        """
        Build REQ_UD2 telegram (request user data).

        Returns short frame: START + C + A + CHECKSUM + STOP
        Example: 10 5B 05 60 16 (request data from address 5)
        """

    @staticmethod
    def encode_req_ud1(address: int) -> bytes:
        """Build REQ_UD1 telegram (request alarm data)"""

    @staticmethod
    def encode_snd_ud(address: int, data: bytes) -> bytes:
        """Build SND_UD telegram (send user data to device)"""

    @staticmethod
    def _calculate_checksum(data: bytes) -> int:
        """Calculate M-Bus checksum (sum of all bytes, modulo 256)"""
```

#### Decoding (Complex - State Machine)
```python
class TelegramDecoder:
    """
    Progressive telegram decoder with internal state machine.

    Usage pattern (from Session layer):
        decoder = TelegramDecoder(expected_address=5)

        while not decoder.is_complete():
            bytes_needed = decoder.bytes_needed()
            data = await transport.read(bytes_needed)
            decoder.feed(data)  # Validates and updates state

        telegram = decoder.get_telegram()
    """

    # State tracking
    _state: DecoderState
    _buffer: bytearray
    _expected_address: int | None
    _frame_length: int | None

    # Flexible response handling
    _allowed_types: set[FrameType]

    def __init__(
        self,
        expected_address: int | None = None,
        allowed_types: set[FrameType] | None = None
    ):
        """
        Initialize decoder.

        Args:
            expected_address: Expected device address (None = accept any)
            allowed_types: Set of allowed frame types (None = auto-detect)
                         Allows Session to say "expect ACK or Error response"
        """
        self._state = DecoderState.EXPECT_START
        self._buffer = bytearray()
        self._expected_address = expected_address
        self._allowed_types = allowed_types or {FrameType.ANY}

    def bytes_needed(self) -> int:
        """
        Returns how many bytes to read next.

        Based on current state:
        - EXPECT_START: 1 byte
        - EXPECT_LENGTH: 2 bytes (L-field x2)
        - EXPECT_START2: 1 byte
        - EXPECT_C_FIELD: 1 byte
        - EXPECT_PAYLOAD: calculated from L-field
        - etc.
        """
        if self._state == DecoderState.EXPECT_START:
            return 1
        elif self._state == DecoderState.EXPECT_LENGTH:
            return 2
        elif self._state == DecoderState.EXPECT_PAYLOAD:
            return self._frame_length  # Already calculated
        # ... etc

    def feed(self, data: bytes) -> None:
        """
        Feed received bytes to decoder. Validates immediately.

        Updates internal state and advances to next step.

        Raises:
            MBusProtocolError: If validation fails at any step
        """
        if len(data) != self.bytes_needed():
            raise MBusProtocolError(
                f"Expected {self.bytes_needed()} bytes, got {len(data)}"
            )

        self._buffer.extend(data)

        # Validate based on current state
        if self._state == DecoderState.EXPECT_START:
            self._validate_start(data[0])
        elif self._state == DecoderState.EXPECT_LENGTH:
            self._validate_length(data)
        elif self._state == DecoderState.EXPECT_CHECKSUM:
            self._validate_checksum(data[0])
        # ... etc

        # Advance to next state
        self._advance_state()

    def is_complete(self) -> bool:
        """Check if telegram is fully decoded"""
        return self._state == DecoderState.COMPLETE

    def get_telegram(self) -> Telegram:
        """
        Return complete decoded telegram.

        Only callable after is_complete() returns True.

        Returns appropriate telegram type:
        - ACKTelegram
        - ShortFrameTelegram
        - UserDataTelegram
        - etc.
        """
        if not self.is_complete():
            raise MBusProtocolError("Telegram not complete")

        return self._parse_telegram()

    # Internal validation methods
    def _validate_start(self, byte: int) -> None:
        """Validate START byte and determine frame type"""
        if byte == 0xE5:  # ACK
            self._frame_type = FrameType.ACK
        elif byte == 0x10:  # Short frame
            self._frame_type = FrameType.SHORT
        elif byte == 0x68:  # Long frame
            self._frame_type = FrameType.LONG
        else:
            raise MBusProtocolError(f"Invalid START byte: 0x{byte:02X}")

        # Check if this frame type is allowed
        if (self._allowed_types != {FrameType.ANY} and
            self._frame_type not in self._allowed_types):
            raise MBusProtocolError(
                f"Unexpected frame type: {self._frame_type}"
            )

    def _validate_length(self, data: bytes) -> None:
        """Validate L-field (both bytes must match)"""
        if data[0] != data[1]:
            raise MBusProtocolError(
                f"L-field mismatch: {data[0]} != {data[1]}"
            )
        self._frame_length = data[0]

    def _validate_checksum(self, checksum: int) -> None:
        """Validate checksum against accumulated data"""
        # Calculate checksum of all bytes except START, STOP, and CHECKSUM
        calculated = sum(self._buffer[1:-2]) % 256
        if calculated != checksum:
            raise MBusProtocolError(
                f"Checksum error: expected 0x{calculated:02X}, "
                f"got 0x{checksum:02X}"
            )

    def _advance_state(self) -> None:
        """Advance to next decoder state based on frame type and current state"""
        # State machine logic here
        # Different paths for ACK, Short Frame, Long Frame
        pass

    def _parse_telegram(self) -> Telegram:
        """
        Parse complete buffer into appropriate Telegram object.

        For UserDataTelegram:
        - Extract CI-field
        - Parse status byte
        - Parse data records (DIF/VIF/Data)
        - Check has_more_telegrams flag in status byte
        - Extract manufacturer data if present
        """
        pass

class DecoderState(Enum):
    """Decoder state machine states"""
    EXPECT_START = "start"
    EXPECT_LENGTH = "length"
    EXPECT_START2 = "start2"
    EXPECT_C_FIELD = "c_field"
    EXPECT_A_FIELD = "a_field"
    EXPECT_CI_FIELD = "ci_field"
    EXPECT_PAYLOAD = "payload"
    EXPECT_CHECKSUM = "checksum"
    EXPECT_STOP = "stop"
    COMPLETE = "complete"

class FrameType(Enum):
    """M-Bus frame types"""
    ACK = 0xE5
    SHORT = 0x10
    LONG = 0x68
    ANY = "any"  # For flexible response handling
```

#### Data Structures
```python
@dataclass
class Telegram:
    """Base class for all decoded telegrams"""
    address: int
    telegram_type: TelegramType

@dataclass
class ACKTelegram(Telegram):
    """Single character ACK (E5h)"""
    pass

@dataclass
class ShortFrameTelegram(Telegram):
    """Short frame (control without data)"""
    c_field: int

@dataclass
class UserDataTelegram(Telegram):
    """RSP-UD telegram with application data"""
    ci_field: int
    status: StatusByte
    records: list[DataRecord]
    has_more_telegrams: bool  # Critical for multi-telegram handling!
    manufacturer_data: bytes | None

@dataclass
class DataRecord:
    """Single M-Bus data record (DIF + VIF + Data)"""
    dif: int
    dife: list[int]
    vif: int
    vife: list[int]
    data: bytes
    # Parsed values (to be added later)
    # value: Any
    # unit: str
    # description: str
```

### Session Layer Integration

How Session layer uses the progressive decoder:

```python
# In Session Layer
async def _receive_telegram(
    self,
    expected_address: int | None = None,
    allowed_types: set[FrameType] | None = None
) -> Telegram:
    """
    Receive and decode a telegram progressively.

    Args:
        expected_address: Expected device address (validates A-field)
        allowed_types: Allowed frame types (e.g., {ACK, ERROR})

    Returns:
        Decoded telegram

    Raises:
        MBusTimeoutError: If any read times out
        MBusProtocolError: If validation fails
    """
    # Create decoder
    decoder = TelegramDecoder(
        expected_address=expected_address,
        allowed_types=allowed_types
    )

    # Progressive read loop
    while not decoder.is_complete():
        bytes_needed = decoder.bytes_needed()

        # Read from transport (may timeout and return empty bytes)
        data = await self.transport.read(bytes_needed)

        if not data:
            # Timeout - Session handles retry
            raise MBusTimeoutError("No response from device")

        try:
            # Feed to decoder - validates immediately
            decoder.feed(data)
        except MBusProtocolError as e:
            # Validation failed - Session will retry entire sequence
            raise

    # Get complete telegram
    return decoder.get_telegram()
```

### Error Handling Strategy

**Protocol Layer Responsibility:**
- Validate data immediately as it's fed
- Throw `MBusProtocolError` on any validation failure
- Does NOT handle retries - that's Session layer's job

**Session Layer Responsibility:**
- Catch `MBusProtocolError` and `MBusTimeoutError`
- Retry entire sequence from start (per M-Bus specification)
- Clear any partial state before retry
- Give up after max retries and propagate error to Master layer

**Example Error Scenarios:**

1. **Checksum error**: Protocol throws error → Session retries entire request
2. **Wrong frame type**: Protocol throws error → Session retries (might be corruption)
3. **Timeout reading**: Transport returns empty bytes → Session retries
4. **Wrong address**: Protocol throws error → Session retries or fails (depends on config)
5. **L-field mismatch**: Protocol throws error → Session retries

**Flexible Response Handling:**

Some M-Bus operations can receive multiple response types. For example, after SND_NKE:
- Normal case: ACK (0xE5)
- Error case: Error telegram

Session layer can specify allowed types:
```python
telegram = await self._receive_telegram(
    expected_address=5,
    allowed_types={FrameType.ACK, FrameType.SHORT}  # Accept both
)

if isinstance(telegram, ACKTelegram):
    # Success
    return True
else:
    # Handle error telegram
    return False
```

### Design Notes
- **Progressive validation**: Each byte/field validated immediately as received
- **State machine**: Decoder maintains internal state, Session just feeds bytes
- **Fail fast**: Error detection happens as early as possible
- **No retry in Protocol**: Protocol only validates, Session handles retries per M-Bus spec
- **Flexible responses**: Decoder can accept multiple frame types when needed
- **Checksum at end**: Only validated after complete frame received
- **Multi-telegram detection**: Parse `has_more_telegrams` flag in status byte

### Decoder Architecture

**Single Decoder Interface**:
- Session layer uses one `TelegramDecoder` class
- Decoder handles all frame types (ACK, Short, Long)
- Session can specify allowed frame types (e.g., `{ACK, LONG}`)

**Internal Implementation**:
- Internally, decoder can delegate to specialized handlers for each frame type
- ACK handling, Short frame handling, Long frame handling
- This is an internal detail hidden from Session layer

**Benefits**:
- Simple Session layer code - one decoder for all cases
- Session can express "expect ACK or Error" easily
- Internal specialization keeps code organized

### Multi-Telegram Detection
According to M-Bus specification, a device can indicate more data is available:
- Status byte (in Variable Data Structure) contains "DIF_MORE_RECORDS_FOLLOW" flag
- When parsing UserDataTelegram, extract this flag
- Session layer checks `has_more_telegrams` flag and automatically sends additional REQ_UD2
- All records from all telegrams are collected and returned together

---

## Layer 3: Session Layer

**File**: `session.py`
**Status**: 🚧 To be implemented

### Responsibility
Orchestrate communication flow between master and slaves. Handles telegram sequencing, retries, error recovery, and multi-telegram sequences.

### Key Responsibilities
1. **Send telegrams**: Use Transport to send bytes (encoded by Protocol)
2. **Receive telegrams**: Read bytes from Transport, decode with Protocol
3. **Retry logic**: Handle timeouts, retries on failure
4. **Multi-telegram handling**: Automatically request additional telegrams when indicated
5. **Error recovery**: Clean up state on failures
6. **Sequencing**: Ensure correct order (e.g., reset before first read)

### Key Classes

```python
class MBusSession:
    """
    Orchestrates M-Bus communication with retry logic and error handling.

    Responsibilities:
    - Send telegrams and receive responses
    - Progressive telegram decoding (feed bytes to decoder)
    - Retry logic per M-Bus specification
    - Multi-telegram sequence handling
    - Error recovery
    """

    # Dependencies
    transport: Transport
    encoder: TelegramEncoder

    # Configuration
    max_retries: int
    retry_delay: float
    base_timeout: float

    def __init__(
        self,
        transport: Transport,
        max_retries: int = 3,
        retry_delay: float = 0.1,
        base_timeout: float = 0.5
    ):
        """Initialize session with transport and configuration"""
        self.transport = transport
        self.encoder = TelegramEncoder()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.base_timeout = base_timeout

    # High-level operations
    async def reset_device(self, address: int) -> bool:
        """
        Send SND_NKE and wait for ACK with retries.

        Flow:
        1. Encode SND_NKE telegram
        2. Send and receive ACK (with retries)
        3. Return True if ACK, False if max retries exceeded

        Returns:
            True if device acknowledged reset, False otherwise
        """
        request = self.encoder.encode_snd_nke(address)

        for attempt in range(self.max_retries):
            try:
                # Send request
                await self.transport.write(request)

                # Receive response (ACK expected)
                telegram = await self._receive_telegram(
                    expected_address=address,
                    allowed_types={FrameType.ACK}
                )

                return True  # Got ACK

            except (MBusTimeoutError, MBusProtocolError):
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay)
                    continue
                return False  # Max retries exceeded

    async def read_user_data(self, address: int) -> list[DataRecord]:
        """
        Read all data records from device.

        Handles multi-telegram sequences automatically:
        - Sends REQ_UD2
        - Receives RSP_UD telegram
        - Checks has_more_telegrams flag
        - If True: sends another REQ_UD2 for next telegram
        - Collects all records from all telegrams

        Returns:
            All data records from all telegrams

        Raises:
            MBusTimeoutError: If device doesn't respond after retries
            MBusProtocolError: If validation fails after retries
        """
        all_records = []

        while True:
            # Request data
            request = self.encoder.encode_req_ud2(address)

            # Send and receive with retries
            telegram = await self._send_and_receive(
                request=request,
                expected_address=address,
                allowed_types={FrameType.LONG}  # RSP_UD is long frame
            )

            # Telegram must be UserDataTelegram
            if not isinstance(telegram, UserDataTelegram):
                raise MBusProtocolError(
                    f"Expected UserDataTelegram, got {type(telegram)}"
                )

            # Collect records
            all_records.extend(telegram.records)

            # Check for more telegrams
            if not telegram.has_more_telegrams:
                break  # Done

        return all_records

    # Core private methods
    async def _send_and_receive(
        self,
        request: bytes,
        expected_address: int | None = None,
        allowed_types: set[FrameType] | None = None
    ) -> Telegram:
        """
        Send request and receive response with retry logic.

        Implements M-Bus retry strategy:
        - Try up to max_retries times
        - On timeout: retry
        - On protocol error: retry (might be transmission corruption)
        - After max retries: raise last exception

        Args:
            request: Encoded telegram bytes to send
            expected_address: Expected device address
            allowed_types: Allowed response frame types

        Returns:
            Decoded telegram

        Raises:
            MBusTimeoutError: After max retries with timeouts
            MBusProtocolError: After max retries with validation errors
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                # Send request
                await self.transport.write(request)

                # Receive response progressively
                telegram = await self._receive_telegram(
                    expected_address=expected_address,
                    allowed_types=allowed_types
                )

                return telegram  # Success!

            except (MBusTimeoutError, MBusProtocolError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    # Wait before retry
                    await asyncio.sleep(self.retry_delay)
                    continue
                # Max retries exceeded - raise last exception
                raise last_exception

    async def _receive_telegram(
        self,
        expected_address: int | None = None,
        allowed_types: set[FrameType] | None = None
    ) -> Telegram:
        """
        Receive and decode telegram progressively.

        Creates decoder and feeds it bytes in small chunks until complete.
        Decoder validates each chunk immediately.

        Args:
            expected_address: Expected device address (None = any)
            allowed_types: Allowed frame types (None = any)

        Returns:
            Decoded telegram

        Raises:
            MBusTimeoutError: If any read times out
            MBusProtocolError: If validation fails
        """
        # Create decoder with expectations
        decoder = TelegramDecoder(
            expected_address=expected_address,
            allowed_types=allowed_types
        )

        # Progressive read loop
        while not decoder.is_complete():
            # Decoder tells us how many bytes it needs
            bytes_needed = decoder.bytes_needed()

            # Read from transport with timeout
            data = await self.transport.read(
                bytes_needed,
                protocol_timeout=self.base_timeout
            )

            if not data:
                # Timeout (transport returns empty bytes)
                raise MBusTimeoutError(
                    f"Timeout reading {bytes_needed} bytes "
                    f"(state: {decoder._state})"
                )

            # Feed to decoder - validates immediately
            try:
                decoder.feed(data)
            except MBusProtocolError:
                # Validation failed - re-raise for retry logic
                raise

        # Get complete validated telegram
        return decoder.get_telegram()
```

### Configuration

Configuration is passed to Session constructor:

```python
session = MBusSession(
    transport=transport,
    max_retries=3,          # Number of retry attempts
    retry_delay=0.1,        # Seconds to wait between retries
    base_timeout=0.5        # Base timeout for first byte response
)
```

Per M-Bus specification, the master should retry on:
- Timeout (no response)
- Checksum errors (transmission corruption)
- Invalid frame structure (might be corruption)

### Error Handling Strategy

**Retry on These Errors:**
- `MBusTimeoutError`: Device didn't respond in time
- `MBusProtocolError`: Validation failed (checksum, frame structure, etc.)

**Don't Retry on These:**
- `MBusConnectionError`: Transport layer failure (connection lost)

**Retry Logic:**
1. Try to send and receive
2. On error: Wait `retry_delay` seconds
3. Try again (up to `max_retries` attempts)
4. After max retries: Raise the last exception to Master layer

**Progressive Decoding Error Flow:**
```
Attempt 1:
  Send REQ_UD2
  Read 1 byte → 0x68 ✓
  Read 2 bytes → 0x1F 0x1F ✓
  Read 1 byte → 0x68 ✓
  Read 1 byte → 0x08 ✓
  ...
  Read 1 byte → Checksum ✗ MBusProtocolError!

Wait retry_delay...

Attempt 2:
  Send REQ_UD2 (entire sequence from start)
  Read 1 byte → 0x68 ✓
  ...
  Complete successfully ✓
```

### Design Notes
- **Stateful orchestration**: Session tracks operations in progress
- **Protocol layer is stateless**: Create new decoder for each telegram
- **Retry entire sequence**: On error, start from the beginning (send request again)
- **Progressive reading**: Feed decoder byte-by-byte as needed
- **Multi-telegram transparency**: Upper layers don't know about multiple telegrams
- **Configurable behavior**: Retries, delays, timeouts all configurable

---

## Layer 4: Master API

**File**: `master.py`
**Status**: 🚧 To be implemented

### Responsibility
Provide a simple, user-friendly API that hides all complexity. Users should be able to read meter data with a single method call.

### Key Features
- Simple one-line meter reading
- Connection lifecycle management
- Friendly error messages
- Convenient data structures for results
- Context manager support

### Main Class
```python
class MBusMaster:
    """
    High-level M-Bus master interface.

    Example usage:
        async with MBusMaster("/dev/ttyUSB0") as master:
            data = await master.read_meter(5)
            print(f"Energy: {data.get_value('Energy')}")
    """

    def __init__(self, url: str, **kwargs):
        """
        Initialize M-Bus master.

        Args:
            url: Connection URL (serial port, socket://host:port, etc.)
            **kwargs: Transport parameters (baudrate, etc.)
        """

    async def connect(self) -> None:
        """Open connection to M-Bus"""

    async def disconnect(self) -> None:
        """Close connection to M-Bus"""

    async def read_meter(self, address: int) -> MeterData:
        """
        Read all data from a meter (main use case).

        Performs complete read sequence:
        1. Reset device (SND_NKE)
        2. Read all data (REQ_UD2, handles multi-telegram automatically)
        3. Return parsed data in friendly format

        Args:
            address: Primary address (0-250)

        Returns:
            MeterData object with all records

        Raises:
            MBusConnectionError: If not connected
            MBusTimeoutError: If device doesn't respond
            MBusProtocolError: If communication fails
        """
```

### Result Data Structure
```python
@dataclass
class MeterData:
    """Friendly representation of meter data"""
    address: int
    records: list[DataRecord]

    def get_value(self, description: str) -> Any:
        """Get value by description (e.g., 'Energy', 'Volume')"""

    def get_all_values(self) -> dict[str, Any]:
        """Get all values as dictionary"""
```

### Design Notes
- Hides all complexity from users
- Provides sensible defaults
- Context manager support for automatic cleanup
- All methods are async (consistent with library design)
- Future expansion: scan_devices(), select_device() for secondary addressing

---

## Complete Data Flow Example: read_meter()

This example shows the complete flow through all layers with progressive decoding:

```
User calls: master.read_meter(address=5)
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 4: Master (master.py)                                     │
│                                                                  │
│  1. Validate connection state                                   │
│  2. Call: session.reset_device(5)                               │
│  3. Call: session.read_user_data(5)                             │
│  4. Wrap result in MeterData                                    │
│  5. Return to user                                              │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 3: Session (session.py)                                   │
│                                                                  │
│ reset_device(5):                                                │
│   1. encoder.encode_snd_nke(5) → bytes                          │
│   2. transport.write(bytes)                                     │
│   3. _receive_telegram():                                       │
│      - Create TelegramDecoder(expected_address=5)               │
│      - Loop: bytes_needed = decoder.bytes_needed()              │
│              data = transport.read(bytes_needed)                │
│              decoder.feed(data)  # validates!                   │
│      - telegram = decoder.get_telegram()                        │
│   4. Return True if ACK                                         │
│                                                                  │
│ read_user_data(5):                                              │
│   Loop until has_more_telegrams == False:                       │
│     1. encoder.encode_req_ud2(5) → bytes                        │
│     2. _send_and_receive():                                     │
│        - transport.write(bytes)                                 │
│        - _receive_telegram() [progressive!]                     │
│     3. Collect telegram.records                                 │
│     4. Check telegram.has_more_telegrams                        │
│   Return all collected records                                  │
│                                                                  │
│ Retry logic: On error, retry entire sequence up to 3 times     │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 2: Protocol (protocol.py)                                 │
│                                                                  │
│ TelegramEncoder (stateless):                                    │
│   - encode_snd_nke(5) → bytes [10 40 05 45 16]                  │
│   - encode_req_ud2(5) → bytes [10 5B 05 60 16]                  │
│                                                                  │
│ TelegramDecoder (state machine):                                │
│   Progressive decoding with immediate validation:               │
│                                                                  │
│   State: EXPECT_START                                           │
│     bytes_needed() → 1                                          │
│     feed(0x68) → validate START, advance to EXPECT_LENGTH       │
│                                                                  │
│   State: EXPECT_LENGTH                                          │
│     bytes_needed() → 2                                          │
│     feed(0x1F 0x1F) → validate L-fields match, advance          │
│                                                                  │
│   State: EXPECT_START2                                          │
│     bytes_needed() → 1                                          │
│     feed(0x68) → validate second START, advance                 │
│                                                                  │
│   ... continues for C, A, CI fields, payload, checksum ...      │
│                                                                  │
│   State: COMPLETE                                               │
│     get_telegram() → UserDataTelegram with parsed records       │
│                                                                  │
│ If validation fails at ANY step: raise MBusProtocolError        │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1: Transport (transport.py)                               │
│                                                                  │
│ write(bytes):                                                   │
│   - Clear input buffer                                          │
│   - Send bytes to serial/TCP                                    │
│                                                                  │
│ read(size, timeout):                                            │
│   - Calculate total timeout (base + transmission time)          │
│   - Read exactly 'size' bytes                                   │
│   - Return bytes or empty on timeout                            │
│                                                                  │
│ No knowledge of M-Bus protocol or telegram structure            │
└─────────────────────────────────────────────────────────────────┘
```

### Progressive Decoding Example (Long Frame with Multi-Telegram)

```
Session: Send REQ_UD2 to address 5
Session: Create decoder, start progressive read

Decoder: bytes_needed() → 1
Transport: read(1) → 0x68
Decoder: feed(0x68) → ✓ Long frame START, state → EXPECT_LENGTH

Decoder: bytes_needed() → 2
Transport: read(2) → 0x1F 0x1F
Decoder: feed(0x1F 0x1F) → ✓ L-fields match (31 bytes), state → EXPECT_START2

Decoder: bytes_needed() → 1
Transport: read(1) → 0x68
Decoder: feed(0x68) → ✓ Second START, state → EXPECT_C_FIELD

Decoder: bytes_needed() → 1
Transport: read(1) → 0x08
Decoder: feed(0x08) → ✓ C-field (RSP_UD), state → EXPECT_A_FIELD

Decoder: bytes_needed() → 1
Transport: read(1) → 0x05
Decoder: feed(0x05) → ✓ Address matches expected, state → EXPECT_CI_FIELD

... continues reading CI-field, status, data records ...

Decoder: bytes_needed() → 1
Transport: read(1) → 0xAB (checksum)
Decoder: feed(0xAB) → ✓ Checksum valid, state → EXPECT_STOP

Decoder: bytes_needed() → 1
Transport: read(1) → 0x16
Decoder: feed(0x16) → ✓ STOP byte, state → COMPLETE

Decoder: is_complete() → True
Decoder: get_telegram() → UserDataTelegram(
    address=5,
    ci_field=0x72,
    status=StatusByte(has_more=True),  ← MORE DATA AVAILABLE!
    records=[...],
    has_more_telegrams=True
)

Session: Check has_more_telegrams → True
Session: Send another REQ_UD2 to get next telegram...
Session: Repeat progressive decoding...
Session: Eventually has_more_telegrams → False
Session: Return all collected records to Master
```

---

## Implementation Scope

### What We're Implementing (Phase 1-3)

**Primary Goal**: Safely read data from M-Bus meters

**Supported**:
- Primary addressing (0-250, including broadcast 0xFF)
- Variable Data Structure (CI-field values from EN 13757-3:2018)
- Telegram types: ACK, Short Frame, Long Frame
- Data record types: All from Table 4 (integers, BCD, real, variable length, etc.)
- Multi-telegram sequences
- Error handling per M-Bus specification
- No encryption (plain text communication)

**Not in Initial Scope** (can be added in Phase 4):
- Sending data TO meters (only reading FROM meters)
- Secondary addressing (12-digit ID selection)
- Encrypted communication (AES)
- Baud rate switching
- Advanced features: alarm polling, clock sync, device discovery

**Note on Features**: As we develop, we may add features like clock synchronization if they're straightforward and useful. The scope is flexible based on what's needed for reliable meter reading.

### Important: Old vs Current Specifications

**Current Spec**: EN 13757-3:2018 (in `reference/EN 13757-3 2018 specs/`)
- This is what we implement

**Old Specs**: EN 13757-3 older versions (in `reference/Original specs (out of date)/`)
- Included for reference only
- Help understand why current spec is designed this way
- **DO NOT implement outdated features**

**Examples of outdated terminology**:
- "Control Frames" → Now called "Long Frames without user data"
- "Fixed Data Structure" → Removed in 2018 spec, use Variable Data Structure
- "Mode 2" → Phased out in 2018 spec
- Old CI-field values → Use 2018 values only

---

## Implementation Phases

### Phase 1: Protocol Layer (Foundation)
**Goal**: Implement encoding, decoding, and validation

Tasks:
- Extract M-Bus constants from specification to `constants.py`
- Define telegram data structures (Telegram, ACKTelegram, UserDataTelegram, etc.)
- Implement encoding functions (SND_NKE, REQ_UD2, etc.)
- Implement decoding functions (parse frames, validate checksums)
- Implement data record parsing (DIF, VIF, data extraction)

**Success criteria**: Can encode/decode all basic telegram types (tested with real hardware)

---

### Phase 2: Session Layer (Orchestration)
**Goal**: Implement communication flow and retry logic

Tasks:
- Implement MBusSession class
- Implement reset_device() with retries
- Implement read_user_data() with multi-telegram support
- Add error recovery logic per M-Bus specification

**Success criteria**: Can perform complete read sequence with multi-telegram handling (tested with real hardware)

---

### Phase 3: Master API (User Interface)
**Goal**: Provide simple, user-friendly API

Tasks:
- Implement MBusMaster class
- Implement read_meter() convenience method
- Add MeterData result wrapper
- Add context manager support

**Success criteria**: Users can read meter data with single method call (tested with real hardware)

---

### Phase 4: Advanced Features (Future)
Optional features to add later:
- Secondary addressing (device selection by ID)
- Alarm reading (REQ_UD1)
- Device scanning/discovery
- Baud rate switching
- Clock synchronization
- Encrypted communication (AES)

---

## Testing Strategy

### Development Testing (During Implementation)

**Approach**: Test frequently with real hardware during development
- Use physical M-Bus gateway for testing
- Manual verification of results by developer
- Rapid iteration and debugging with real devices
- Test file: `dev_mbus_test.py` (not committed to git)

**Benefits**:
- Ensures implementation works with real devices
- Catches protocol issues early
- Validates assumptions against actual hardware
- Quick feedback loop

### Formal Unit/Integration Tests (At the End)

**Unit Tests** (fast, no I/O):
- Protocol layer: Test encoding/decoding with known test vectors
- Session layer: Test with mocked Transport
- Master layer: Test with mocked Session

**Integration Tests** (slower, uses I/O):
- Transport layer: Already tested ✅
- Session + Protocol: Test with mocked connections
- Full stack: Test with simulated M-Bus devices

**Test Data Sources**:
- Examples from EN 13757-3:2018 specification
- Real device captures from `reference/` directory
- Synthetic test cases for edge cases

### Test File Management

- Main development testing: `dev_mbus_test.py` (not in git)
- Keep temporary test files to minimum
- Clean up when done
- Formal tests in `tests/` directory added at the end

---

## Key Design Decisions Summary

### Progressive Decoding ✅
**Decision**: Read and validate telegrams progressively, byte-by-byte
- Decoder maintains internal state machine
- Session feeds bytes in small chunks (1-2 at a time)
- Validation happens immediately after each read
- Fail fast on any error

**Benefits**: Early error detection, efficient bandwidth use, clear state tracking

### Error Handling Strategy ✅
**Decision**: Protocol layer validates only, Session layer handles retries
- Protocol throws `MBusProtocolError` on validation failure
- Session catches errors and retries entire sequence (per M-Bus spec)
- Configurable retry count and delay
- Clean separation of concerns

**Benefits**: Simple Protocol layer testing, flexible retry logic, matches M-Bus specification

### Multi-Telegram Handling ✅
**Decision**: Session layer automatically handles multi-telegram sequences
- Protocol layer parses `has_more_telegrams` flag from status byte
- Session checks flag and sends additional REQ_UD2 automatically
- All records collected and returned together
- Transparent to Master layer

**Benefits**: Simple Master API, complete data retrieval, follows M-Bus standard

### Flexible Response Types ✅
**Decision**: Decoder can accept multiple telegram types when needed
- `allowed_types` parameter lets Session specify acceptable responses
- Example: After SND_NKE, accept either ACK or Error telegram
- Decoder validates against allowed types and throws error if mismatch

**Benefits**: Handles M-Bus spec variations, robust error handling

### Layer Boundaries ✅
**Decision**: Strict separation of responsibilities
- **Transport**: Byte I/O only, no protocol knowledge
- **Protocol**: Stateless encode/decode/validate (except decoder state machine)
- **Session**: Stateful orchestration, retry logic, multi-telegram
- **Master**: Simple user API

**Benefits**: Easy testing, clear responsibilities, maintainable code

---

## Implementation Notes

### Decisions Made During Development

**Resolved**:
- ~~How to decode progressively?~~ ✅ State machine with `bytes_needed()` / `feed()` pattern
- ~~How to handle retries?~~ ✅ Retry entire sequence, configurable count
- ~~How to handle multi-telegram?~~ ✅ Automatic based on flag
- ~~Decoder architecture?~~ ✅ Single decoder handling all frame types, internal delegation

**To Be Decided During Implementation**:
- **Checksum calculation**: Exact algorithm defined in EN 13757-2 specification
- **Multi-telegram error handling**: Retry strategy defined in M-Bus specification
- **Data record parsing approach**: Parse progressively (DIF → length → data) vs batch parse
- **`has_more_telegrams` flag**: Location defined in specification, extract during implementation
- **Manufacturer data length**: Determined from frame structure per specification
- **Error telegram structure**: Defined in M-Bus specification, implement when needed

**Future Considerations** (Phase 4):
- Session device state caching
- Device-specific quirk handling
- Sync wrappers for non-async users
- Advanced API exposure
- Batch operations
- Progress callbacks

---

## References

- **EN 13757-3:2018**: M-Bus Application Layer specification (see `reference/EN 13757-3 2018 specs/`)
- **EN 13757-2**: M-Bus Physical and Link Layer
- **OMS Specification**: Open Metering System extensions (see `reference/OMS/`)

---

## Status and Next Steps

### Completed ✅
- **Architecture design**: 4-layer design with clear responsibilities
- **Transport layer**: Fully implemented and tested
- **Progressive decoding strategy**: State machine approach defined
- **Error handling strategy**: Protocol validates, Session retries
- **Multi-telegram handling**: Automatic collection via flag detection
- **High-level API design**: All three layers (Protocol, Session, Master) outlined

### Ready for Implementation

The plan is now complete and ready for implementation. The next steps are:

1. **Implement Protocol Layer**
   - **M-Bus constants file** (`constants.py`) - Extract all protocol constants from spec
   - `TelegramEncoder` class (simple, stateless)
   - `TelegramDecoder` class (state machine)
   - Telegram data structures (ACKTelegram, UserDataTelegram, etc.)
   - Data record parsing (DIF/VIF/Data)

2. **Implement Session Layer**
   - `MBusSession` class
   - `reset_device()` method
   - `read_user_data()` method
   - Retry logic with proper error handling
   - Progressive telegram reception

3. **Implement Master API**
   - `MBusMaster` class
   - `read_meter()` convenience method
   - `MeterData` result wrapper
   - Context manager support
   - Connection lifecycle management

### Implementation Order

Follow the phases defined earlier:
- **Phase 1**: Protocol Layer (foundation)
- **Phase 2**: Session Layer (orchestration)
- **Phase 3**: Master API (user interface)
- **Phase 4**: Advanced features (optional, future)

Each phase should be completed with unit tests before moving to the next phase.
