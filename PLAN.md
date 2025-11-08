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
│  "Send/receive datagrams with retries"  │
│  "Handle multi-datagram sequences"      │
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
Raw byte I/O and connection management. No knowledge of M-Bus protocol or datagram structure.

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

**Strategy**: ✅ Distributed approach (constants stored in respective modules)
**Status**: ✅ Complete

### Purpose

M-Bus protocol constants are organized in module-specific files rather than a single central file. This provides:
- **Module cohesion** - Constants defined alongside the code that uses them
- **Reduced coupling** - Modules are more self-contained
- **Clear ownership** - Each module owns its constants
- **Easier maintenance** - Related code and constants together
- **No magic numbers** in code
- **Spec traceability** with comments linking to specification sections

### Constant Distribution

#### Central Constants (`constants.py`)
Frame-level and address constants used across transport/application layers:
- **Frame structure**: START, STOP, ACK bytes
- **Address constants**: Broadcast (0xFF), special addresses
- **C-Field values**: SND_NKE, REQ_UD2, etc. (with FCB/FCV support)
- **CI-Field values**: Application layer protocol identifiers
- **Device type constants**: Water, gas, heat, electricity meters
- **Status**: ✅ Complete

#### Protocol Layer Constants (distributed)

**`protocol/common.py`**:
- `CommunicationDirection` enum (MASTER_TO_SLAVE, SLAVE_TO_MASTER, BIDIRECTIONAL)
- **Status**: ✅ Complete

**`protocol/dif.py`**:
- DIF/DIFE bit masks and shift constants
- DIF extension bit masks (0x80)
- DIFE storage/tariff/subunit bit masks
- `DIFSpecialFunction` flags
- DIF data type field codes
- **Status**: ✅ Complete

**`protocol/vif.py`**:
- VIF/VIFE table entries and codes
- VIF units and descriptions
- Value transform function mappings
- Data type rules for VIF/DIF compatibility
- **Status**: ✅ Complete

**`protocol/value.py`**:
- `ValueFunction` enum (INSTANTANEOUS, MAXIMUM, MINIMUM, ERROR)
- **Status**: ✅ Complete

### Benefits of Distributed Approach

1. **Code clarity**: Constants near usage point
   - Example: `if dif.field_code & DIF_EXTENSION_BIT_MASK:` (in dif.py)

2. **Module independence**: Each module is self-contained

3. **No circular dependencies**: Common types in `common.py`, specific constants in their modules

4. **Easier refactoring**: Changes localized to modules

5. **Spec compliance**: Comments still reference exact specification sections

### Implementation

This approach was implemented by:
1. Identifying transport-layer constants → `constants.py`
2. Creating `protocol/common.py` for shared protocol types
3. Adding module-specific constants to `dif.py`, `vif.py`, etc.
4. Ensuring no circular imports via proper module structure

---

## Layer 2: Protocol Layer (Modular Structure)

**Structure**: Multiple specialized modules in `protocol/` package
**Status**: 🚧 Under development - modular implementation approach

### Responsibility
Pure encode/decode/validate operations for M-Bus datagrams. This layer is stateless and performs only data transformations. Due to the complexity of VIF/DIF tables (~3000+ lines each), the protocol layer is split into specialized modules.

### Module Structure

```
protocol/
├── __init__.py           # Public API and orchestration
├── data.py               # Data type definitions and decoding (🚧 partial)
├── vif.py                # VIF/VIFE table system (🚧 65% complete)
├── dif.py                # DIF/DIFE table system (🚧 in progress)
├── vib.py                # VIB parser (VIF + VIFE chain)
├── dib.py                # DIB parser (DIF + DIFE chain)
├── record.py             # Data record parser (DIB + VIB + Data)
├── c_field.py            # C-field encoding/decoding
├── ci_field.py           # CI-field interpretation
├── encoder.py            # Datagram encoder
└── decoder.py            # Progressive datagram decoder
```

**Why modular?**
- VIF/DIF tables are very large (~3000 lines each) but well-contained
- Each module has single, clear responsibility
- Easier testing and maintenance
- Modules can be developed and tested independently
- Reusability across encoder and decoder

### Module Descriptions

#### data.py - Data Type System
**Status**: 🚧 Partially complete - DataType enum done, decoding functions pending
**Lines**: ~67
**Reference**: EN 13757-3:2018 Annex A (Data Types), Table 5 (LVAR interpretation)
**Architecture**: Enum-based data type definitions with decoding functions

**Entry Point Enum**:
- ✅ `DataType` - All 13 M-Bus data types (A, B, C, D, F, G, H, I, J, K, L, M, LVAR)

**Completed Implementation**:
- ✅ DataType enum with all types defined
- ✅ Documentation for each data type

**Remaining Work** (needed by record.py):
- ❌ `decode_type_a(data: bytes) -> int` - Unsigned BCD decoding
- ❌ `decode_type_b(data: bytes) -> int` - Signed binary integer decoding
- ❌ `decode_type_c(data: bytes) -> int` - Unsigned binary integer decoding
- ❌ `decode_type_d(data: bytes) -> list[bool]` - Boolean bit array decoding
- ❌ `decode_type_f(data: bytes) -> datetime` - Date/Time CP32 (4 bytes)
- ❌ `decode_type_g(data: bytes) -> date` - Date CP16 (2 bytes)
- ❌ `decode_type_h(data: bytes) -> float` - IEEE 754 floating point (4 bytes)
- ❌ `decode_type_i(data: bytes) -> datetime` - Date/Time CP48 (6 bytes)
- ❌ `decode_type_j(data: bytes) -> time` - Time CP24 (3 bytes)
- ❌ `decode_type_k(data: bytes) -> dict` - Daylight savings (4 bytes)
- ❌ `decode_type_l(data: bytes) -> dict` - Listening window management (88 bytes via LVAR=EBh)
- ❌ `decode_type_m(data: bytes, lvar: int) -> datetime | timedelta` - Date/Time or duration (variable)
- ❌ `decode_lvar(data: bytes, lvar: int) -> Any` - Variable length data (Table 5 encoding)
- ❌ Test with real meter data
- ❌ Unit tests

**Data Type Categories**:

1. **Numeric Types**:
   - Type A: Unsigned BCD (decimal digits in binary coded decimal)
   - Type B: Signed binary integer (little-endian)
   - Type C: Unsigned binary integer (little-endian)
   - Type H: IEEE 754 floating point (4 bytes, little-endian)

2. **Date/Time Types**:
   - Type F: Date/Time CP32 (4 bytes - date and time)
   - Type G: Date CP16 (2 bytes - date only)
   - Type I: Date/Time CP48 (6 bytes - extended date/time)
   - Type J: Time CP24 (3 bytes - time only)
   - Type M: Date/Time or duration (variable length via LVAR E2h-EAh)

3. **Special Types**:
   - Type D: Boolean (bit array for status flags)
   - Type K: Daylight savings (4 bytes - DST rules)
   - Type L: Listening window management (88 bytes via LVAR=EBh)
   - LVAR: Variable length data (Table 5 encoding, 0-200 bytes)

**Usage by Other Modules**:
- `dif.py` - DIF field descriptors specify data_type (DataType enum)
- `vif.py` - VIF data type rules specify required/override types (DataType enum)
- `record.py` - Calls decoding functions to convert raw bytes to Python values

**API Pattern**:
```python
from mbusmaster.protocol.data import DataType, decode_type_b, decode_type_h

# Used by DIF/VIF modules
data_type = DataType.B  # Signed integer
data_type = DataType.H  # Floating point

# Used by record parser
value = decode_type_b(b'\x01\x02\x03\x04')  # Decode 4-byte signed int
value = decode_type_h(b'\x00\x00\x80\x3f')  # Decode IEEE 754 float (1.0)
value = decode_lvar(data, lvar_code)  # Decode variable length data
```

---

#### vif.py - VIF/VIFE Table System
**Status**: 🚧 65% complete - core implementation done, needs refinement
**Lines**: ~2900 (large but focused on one concept)
**Reference**: EN 13757-3:2018 Tables 10-16
**Architecture**: Class-based with VIF/VIFE as entry points

**Entry Point Classes**:
- ✅ `VIF(field_code)` - Parse and represent primary VIF byte
- ✅ `VIFE(field_code, prev_field)` - Parse and represent VIFE extension byte
- ✅ `_VIFAbstract` - Abstract base class with shared functionality

**Completed Implementation**:
- ✅ Table-based VIF/VIFE code lookup using custom TableEnum metaclass
- ✅ All five VIF/VIFE tables implemented:
  - `PrimaryTable` - Main VIF codes (Table 10)
  - `FirstExtensionTable` - Extension via 0xFB (Table 14)
  - `SecondExtensionTable` - Extension via 0xFD (Table 12)
  - `CombinableOrthogonalTable` - Combinable VIFEs (Table 15)
  - `CombinableExtensionTable` - Phase info L1/L2/L3 (Table 16)
- ✅ `_FieldDescriptor` metadata structure (name, unit, value_transform, etc.)
- ✅ `ValueTransform` enum with transformation functions
- ✅ `DataTypeRule` system for VIF/DIF constraints
- ✅ Range-based VIF matching (e.g., 0x03 matches ENERGY range 0x00-0x07)
- ✅ Automatic table selection based on extension pointers
- ✅ VIFE chaining support (multiple VIFEs following VIF)
- ✅ Tested with real meter data (164/164 VIF/VIFEs matched successfully)
- ✅ Helper methods:
  - `create_next_vife(field_code)` - Create next VIFE in chain
  - `get_data_type_rules()` - Get data type constraints
  - `_validate_field_code(code)` - Input validation

**Remaining Work**:
- ❌ Some interpretations need validation (e.g., "Volume" appearing on electricity meters)
- ❌ Phase information (L1/L2/L3) not displaying as expected
- ❌ Need DIF context to fully validate VIF interpretations
- ❌ VIFE combination semantics need refinement
- ❌ Unit tests
- ❌ Additional helper methods may be needed during integration

**Class-Based API Pattern**:
```python
# Parse VIF byte
vif = VIF(0x04)  # Energy Wh
print(vif.field_descriptor.unit)  # "Wh"
print(vif.last_field)  # True (no extension bit)

# Parse VIF with VIFE chain
vif = VIF(0x84)  # Energy Wh + extension bit
vife = vif.create_next_vife(0x01)  # Create extension
# Or: vife = VIFE(0x01, prev_field=vif)
print(vife.field_descriptor)  # Extension field descriptor
print(vife.last_field)  # Check if more VIFEs follow

# Get data type constraints
rules = vif.get_data_type_rules()  # Returns tuple of DataTypeRule
```

**Internal Table Pattern** (used by VIF/VIFE classes):
```python
# Custom metaclass for range-based lookup
class TableEnumType(EnumType):
    def __call__(cls, code: int) -> _FieldDescriptor:
        # Match code against all enum members using mask
        for member in cls:
            if (code & member.value.mask) == (member.value.code & member.value.mask):
                return member.value
        raise ValueError(f"Code 0x{code:02X} not found")

# Table enum with _FieldDescriptor values (internal, used by VIF class)
class PrimaryTable(TableEnum):
    ENERGY = _FieldDescriptor(
        code=0x00, mask=0x78,  # Matches 0x00-0x07
        name=VIFDescription.ENERGY,
        unit=VIFUnit.WH,
        value_transform=ValueTransform.MULT_10_POW_NNN_MINUS_3,
        data_type_rule=(DataTypeRule.A_ANY, DataTypeRule.B_ANY, DataTypeRule.H_ANY, DataTypeRule.LVAR_ANY),
        ...
    )
```

---

#### dif.py - DIF/DIFE Table System
**Status**: ✅ Complete - pending real-world meter testing
**Lines**: ~629 (including constants and implementation)
**Tests**: 65 unit tests in tests/unit/test_dif.py
**Reference**: EN 13757-3:2018 Tables 4, 6, 7, 8
**Architecture**: Class-based with DIF/DIFE as entry points, async from_bytes_async() pattern

**Entry Point Classes**:
- ✅ `DIF(direction, field_code)` - Parse and represent primary DIF byte
- ✅ `DIFE(direction, field_code, prev_field)` - Parse and represent DIFE extension byte
- ✅ `DataDIF` and `SpecialDIF` - Subclasses for different DIF types
- ✅ `DataDIFE` and `FinalDIFE` - Subclasses for different DIFE types

**Completed Implementation**:
- ✅ `_FieldDescriptor` structure for DIF metadata (data_type, length, special_function, etc.)
- ✅ `_FunctionDescriptor` structure for function field metadata
- ✅ `_FieldTable` enum - DIF data types (Table 4) and special functions (Table 6)
- ✅ `_FunctionTable` enum - Function field codes (Table 7)
- ✅ `_SpecialFieldFunction` flags (MANUFACTURER_DATA_HEADER, MORE_RECORDS_FOLLOW, IDLE_FILLER, GLOBAL_READOUT)
- ✅ DIFE chaining support with storage number/tariff/subunit calculation
- ✅ FinalDIFE class for OBIS register numbers (0x00)
- ✅ Helper methods:
  - `create_next_dife(field_code)` - Create next DIFE in chain
  - `from_bytes_async(direction, get_next_bytes)` - Async byte stream parsing
  - `_find_field_descriptor(direction, code)` - Cached lookup with LRU cache
- ✅ DIF/DIFE constants stored in module
- ✅ Comprehensive unit tests (65 tests covering all functionality)

**Remaining Work**:
- ❌ Test with real meter data
- ❌ Additional helper methods may be discovered during higher-level integration

**Class-Based API Pattern**:
```python
# Direct instantiation (for testing or when bytes are available)
from protocol.common import CommunicationDirection

dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, 0x04)  # 32-bit integer
print(dif.data_type)  # DataType.B_4
print(dif.value_function)  # ValueFunction.INSTANTANEOUS
print(dif.last_field)  # True (no extension bit)
print(dif.storage_number)  # 0

# Parse DIF with DIFE chain manually
dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, 0x84)  # 32-bit integer + extension
dife = DIFE(0x01, CommunicationDirection.SLAVE_TO_MASTER, prev_field=dif)
print(dife.storage_number)  # Combined storage number (shifted)
print(dife.tariff)  # Tariff value from DIFE
print(dife.subunit)  # Subunit value from DIFE
print(dife.last_field)  # Check if more DIFEs follow

# Async parsing from byte stream (typical usage)
async def get_next_bytes(n: int) -> bytes:
    # Read n bytes from stream
    return await stream.read(n)

# Parse complete DIF + DIFE chain
dif_chain = await DIF.from_bytes_async(
    CommunicationDirection.SLAVE_TO_MASTER,
    get_next_bytes
)
# Returns: (DIF, *DIFEs) tuple
dif = dif_chain[0]
difes = dif_chain[1:]  # All DIFE bytes in chain
```

**Internal Table Pattern** (used by DIF/DIFE classes):
```python
# Field table with data types and special functions
class _FieldTable(Enum):
    INT_32BIT = _FieldDescriptor(
        code=0b00000100,
        data_type=DataType.B,
        data_length=4,
    )
    MANUFACTURER_SPECIFIC = _FieldDescriptor(
        code=0b00001111,
        mask=0b11111111,  # Exact match
        special_function=_SpecialFunction.MANUFACTURER_SPECIFIC,
    )
    # ...

# Function table for function field interpretation
class _FunctionTable(Enum):
    INSTANTANEOUS_VALUE = _FunctionDescriptor(code=0b00000000)
    MAXIMUM_VALUE = _FunctionDescriptor(code=0b00010000)
    # ...
```

---

#### dib.py - DIB Block Parser
**Status**: 🚧 In Progress
**Estimated Lines**: ~200-300

**Responsibility**: Parse complete DIB (DIF + DIFE chain) and provide high-level access to metadata.

**Uses**: `DIF` and `DIFE` classes from dif.py

**Architecture**: Class-based DIB with async from_bytes_async() pattern

**Implementation**:
```python
class DIB:
    """Data Information Block - DIF + DIFE chain wrapper"""
    _dif: DIF
    _difes: tuple[DIFE, ...]

    # High-level properties extracted from DIF/DIFE chain
    data_type: DataType | None
    data_length: int
    value_function: ValueFunction
    storage_number: int
    tariff: int
    subunit: int

    @staticmethod
    async def from_bytes_async(
        direction: CommunicationDirection,
        get_next_bytes: Callable[[int], Awaitable[bytes]]
    ) -> DIB:
        """
        Parse DIB from byte stream asynchronously.

        Implementation approach:
        1. Call DIF.from_bytes_async() to parse complete DIF/DIFE chain
        2. Extract (dif, *difes) tuple
        3. Create DIB instance with parsed chain
    3. Initialize storage_number from DIF.storage_number
    4. While not DIF/DIFE.last_field:
       - Call create_next_dife(data[offset]) or instantiate DIFE
       - Accumulate storage_number, tariff, subunit
    5. Return DIBInfo with all accumulated metadata
    """
```

---

#### vib.py - VIB Block Parser
**Status**: 🚧 In Progress
**Estimated Lines**: ~200-300

**Responsibility**: Parse complete VIB (VIF + VIFE chain) and provide high-level access to metadata.

**Uses**: `VIF` and `VIFE` classes from vif.py

**Architecture**: Class-based VIB with async from_bytes_async() pattern

**Implementation**:
```python
class VIB:
    """Value Information Block - VIF + VIFE chain wrapper"""
    _vif: VIF
    _vifes: tuple[VIFE, ...]

    # High-level properties extracted from VIF/VIFE chain
    description: str
    unit: str | None
    value_transform: Callable | None
    modifiers: list[str]

    @staticmethod
    async def from_bytes_async(
        direction: CommunicationDirection,
        get_next_bytes: Callable[[int], Awaitable[bytes]]
    ) -> VIB:
        """
        Parse VIB from byte stream asynchronously.

        Implementation approach:
        1. Call VIF.from_bytes_async() to parse complete VIF/VIFE chain
        2. Extract (vif, *vifes) tuple
        3. Create VIB instance with parsed chain
        4. Combine VIF + VIFE descriptions and modifiers semantically
        5. Handle extension pointers (0xFB, 0xFD) automatically
        """
```

**Key Challenge**: Understanding how to semantically combine VIF + multiple VIFEs.
**Note**: Automatic table selection handled by VIFE class based on extension pointers.

---

#### drh.py - Data Record Header (DIB + VIB)
**Status**: 🚧 In Progress
**Estimated Lines**: ~100-150

**Responsibility**: Combine DIB and VIB with validation, resolve final data type.

**Uses**: `DIB` from dib.py and `VIB` from vib.py

**Architecture**: Class-based DRH with async from_bytes_async() pattern

**Implementation**:
```python
class DRH:
    """Data Record Header - combines DIB and VIB with validation"""
    _dib: DIB
    _vib: VIB | None  # None for special-function DIBs

    # Resolved properties
    data_type: DataType | None  # Final data type after VIB data rules
    data_length: int
    value_function: ValueFunction
    storage_number: int
    tariff: int
    subunit: int
    description: str
    unit: str | None
    value_transform: Callable | None

    @staticmethod
    async def from_bytes_async(
        direction: CommunicationDirection,
        get_next_bytes: Callable[[int], Awaitable[bytes]]
    ) -> DRH:
        """
        Parse DRH from byte stream asynchronously.

        Implementation approach:
        1. Parse DIB using DIB.from_bytes_async()
        2. Check if DIB requires VIB (special-function DIBs don't)
        3. If VIB required, parse using VIB.from_bytes_async()
        4. Validate DIB/VIB compatibility using VIF data type rules
        5. Resolve final data type from DIB + VIB data rules
        6. Return DRH with complete metadata
        """
```

**Key Responsibilities**:
- Validate DIB/VIB compatibility (data type rules)
- Handle special-function DIBs (no VIB required)
- Resolve final data type using VIF data type rules
- Provide unified interface for record.py

---

#### record.py - Data Record Parser
**Status**: 🚧 In Progress - basic structure exists
**Estimated Lines**: ~500-800

**Responsibility**: Parse complete data record (DRH + Data) and extract actual values.

**Uses**: `DRH` from drh.py, decode functions from data.py

**Implementation**:
```python
@dataclass
class DataRecord:
    """Complete M-Bus data record"""
    # DIF information
    data_type: str
    function: str
    storage_number: int
    tariff: int
    subunit: int

    # VIF information
    description: str
    unit: str | None
    modifiers: list[str]

    # Value
    raw_value: int | float | str | bytes
    scaled_value: float | str | None  # After applying VIF transform

    # Raw bytes
    raw_dif: int
    raw_difes: list[int]
    raw_vif: int
    raw_vifes: list[int]
    value_bytes: bytes

def parse_records(payload: bytes) -> list[DataRecord]:
    """
    Parse all data records from payload.

    Coordinates:
    - dib.py to parse DIF/DIFE (get data type, length, function, storage, tariff, subunit)
    - vib.py to parse VIF/VIFE (get unit, transform, description, modifiers)
    - data.py to decode raw data bytes (convert bytes to Python values)
    - Apply VIF transform to get final scaled value

    Handles:
    - Multiple records
    - Special DIFs (0x0F, 0x1F manufacturer data)
    - Variable length data (LVAR via data.py)
    - Type validation via VIF DataTypeRules
    """
```

**Critical**: This is where vif.py/dif.py/data.py get validated in context together.

---

#### c_field.py - C-Field Handling
**Status**: ❌ Not started
**Estimated Lines**: ~200-300

**Responsibility**: Encode/decode C-field values, handle FCB/FCV bits.

```python
def encode_c_field(command: CField, fcb: bool = False, fcv: bool = False) -> int:
    """Encode C-field with optional FCB/FCV bits"""

def decode_c_field(c_field: int) -> tuple[CField, bool, bool]:
    """Decode C-field, returns (command, fcb, fcv)"""
```

---

#### ci_field.py - CI-Field Interpretation
**Status**: ❌ Not started
**Estimated Lines**: ~200-300

**Responsibility**: Interpret CI-field values, detect data structure type.

```python
def interpret_ci_field(ci: int) -> CIInfo:
    """Interpret CI-field value"""

@dataclass
class CIInfo:
    ci_type: str  # "variable_data", "manufacturer_specific", etc.
    description: str
```

---

#### encoder.py - Datagram Encoder
**Status**: ❌ Not started
**Estimated Lines**: ~400-600

**Responsibility**: Build M-Bus frames from parameters (uses c_field.py, ci_field.py).

---

#### decoder.py - Progressive Datagram Decoder
**Status**: ❌ Not started
**Estimated Lines**: ~800-1200

**Responsibility**: State machine for progressive frame parsing (uses c_field.py, ci_field.py, record.py).

---

#### protocol/__init__.py - Public API
**Status**: ❌ Not started
**Estimated Lines**: ~100-200

**Responsibility**: Export public API, coordinate between modules.

```python
from mbusmaster.protocol.encoder import DatagramEncoder
from mbusmaster.protocol.decoder import DatagramDecoder
from mbusmaster.protocol.record import DataRecord, parse_records

__all__ = ["DatagramEncoder", "DatagramDecoder", "DataRecord", ...]
```

---

### Module Data Flow

**Encoding Flow**:
```
User params → encoder.py → c_field.py (encode C-field)
                        → ci_field.py (encode CI-field)
                        → bytes
```

**Decoding Flow**:
```
bytes → decoder.py (progressive state machine)
     ↓
     c_field.py (decode C-field)
     ci_field.py (decode CI-field)
     ↓
     record.py (parse all records)
     ↓
     ├─ dib.py (parse DIF + DIFE chain)
     │  ├─ Instantiate DIF(field_code) from dif.py
     │  └─ Call create_next_dife() or instantiate DIFE instances
     │  → Extract data type, length, function, storage, tariff, subunit
     │
     ├─ vib.py (parse VIF + VIFE chain)
     │  ├─ Instantiate VIF(field_code) from vif.py
     │  └─ Call create_next_vife() or instantiate VIFE instances
     │  → Extract unit, transform, description, modifiers
     │
     └─ data.py (decode data field bytes)
        ├─ Use DataType from DIB to select decoding function
        └─ Call decode_type_x(data_bytes) to convert to Python value
        → Raw value (int, float, datetime, etc.)
     ↓
     DataRecord objects with complete metadata and decoded values
```

**Why This Flow?**:
- Encoder builds frames from high-level to low-level (parameters → bytes)
- Decoder parses frames from low-level to high-level (bytes → structured data)
- record.py coordinates between DIB, VIB, and data decoding
- dib.py/vib.py instantiate DIF/DIFE and VIF/VIFE classes and extract metadata
- dif.py/vif.py provide VIF/VIFE/DIF/DIFE classes with internal table lookups
- data.py provides decoding functions to convert raw bytes to Python values

### Key Responsibilities
1. **Encoding**: Convert parameters to bytes ready for transmission
2. **Decoding**: Parse raw bytes into structured data objects
3. **Validation**: Verify checksums, frame structure, datagram types
4. **Metadata extraction**: Multi-datagram flags, status bytes, error codes

### Important Principles
- **Pure functions**: No I/O, no state, no side effects
- **Immediate validation**: Decode and validate received data immediately
- **Expected type checking**: Decoder knows what datagram type to expect
- **Exception on mismatch**: Throws error if received data doesn't match expected type

### Datagram Types
Based on EN 13757-3:2018, the protocol supports these datagram types:

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
  → Parse: Extract has_more_datagrams flag
  → Return: Complete Datagram object
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
class DatagramEncoder:
    """Encodes datagrams into bytes for transmission (stateless)"""

    @staticmethod
    def encode_snd_nke(address: int) -> bytes:
        """
        Build SND_NKE datagram (device reset).

        Returns short frame: START + C + A + CHECKSUM + STOP
        Example: 10 40 05 45 16 (reset device at address 5)
        """

    @staticmethod
    def encode_req_ud2(address: int) -> bytes:
        """
        Build REQ_UD2 datagram (request user data).

        Returns short frame: START + C + A + CHECKSUM + STOP
        Example: 10 5B 05 60 16 (request data from address 5)
        """

    @staticmethod
    def encode_req_ud1(address: int) -> bytes:
        """Build REQ_UD1 datagram (request alarm data)"""

    @staticmethod
    def encode_snd_ud(address: int, data: bytes) -> bytes:
        """Build SND_UD datagram (send user data to device)"""

    @staticmethod
    def _calculate_checksum(data: bytes) -> int:
        """Calculate M-Bus checksum (sum of all bytes, modulo 256)"""
```

#### Decoding (Complex - State Machine)
```python
class DatagramDecoder:
    """
    Progressive datagram decoder with internal state machine.

    Usage pattern (from Session layer):
        decoder = DatagramDecoder(expected_address=5)

        while not decoder.is_complete():
            bytes_needed = decoder.bytes_needed()
            data = await transport.read(bytes_needed)
            decoder.feed(data)  # Validates and updates state

        datagram = decoder.get_datagram()
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
        """Check if datagram is fully decoded"""
        return self._state == DecoderState.COMPLETE

    def get_datagram(self) -> Datagram:
        """
        Return complete decoded datagram.

        Only callable after is_complete() returns True.

        Returns appropriate datagram type:
        - ACKDatagram
        - ShortFrameDatagram
        - UserDataDatagram
        - etc.
        """
        if not self.is_complete():
            raise MBusProtocolError("Datagram not complete")

        return self._parse_datagram()

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

    def _parse_datagram(self) -> Datagram:
        """
        Parse complete buffer into appropriate Datagram object.

        For UserDataDatagram:
        - Extract CI-field
        - Parse status byte
        - Parse data records (DIF/VIF/Data)
        - Check has_more_datagrams flag in status byte
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
class Datagram:
    """Base class for all decoded datagrams"""
    address: int
    datagram_type: DatagramType

@dataclass
class ACKDatagram(Datagram):
    """Single character ACK (E5h)"""
    pass

@dataclass
class ShortFrameDatagram(Datagram):
    """Short frame (control without data)"""
    c_field: int

@dataclass
class UserDataDatagram(Datagram):
    """RSP-UD datagram with application data"""
    ci_field: int
    status: StatusByte
    records: list[DataRecord]
    has_more_datagrams: bool  # Critical for multi-datagram handling!
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
async def _receive_datagram(
    self,
    expected_address: int | None = None,
    allowed_types: set[FrameType] | None = None
) -> Datagram:
    """
    Receive and decode a datagram progressively.

    Args:
        expected_address: Expected device address (validates A-field)
        allowed_types: Allowed frame types (e.g., {ACK, ERROR})

    Returns:
        Decoded datagram

    Raises:
        MBusTimeoutError: If any read times out
        MBusProtocolError: If validation fails
    """
    # Create decoder
    decoder = DatagramDecoder(
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

    # Get complete datagram
    return decoder.get_datagram()
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
- Error case: Error datagram

Session layer can specify allowed types:
```python
datagram = await self._receive_datagram(
    expected_address=5,
    allowed_types={FrameType.ACK, FrameType.SHORT}  # Accept both
)

if isinstance(datagram, ACKDatagram):
    # Success
    return True
else:
    # Handle error datagram
    return False
```

### Design Notes
- **Progressive validation**: Each byte/field validated immediately as received
- **State machine**: Decoder maintains internal state, Session just feeds bytes
- **Fail fast**: Error detection happens as early as possible
- **No retry in Protocol**: Protocol only validates, Session handles retries per M-Bus spec
- **Flexible responses**: Decoder can accept multiple frame types when needed
- **Checksum at end**: Only validated after complete frame received
- **Multi-datagram detection**: Parse `has_more_datagrams` flag in status byte

### Decoder Architecture

**Single Decoder Interface**:
- Session layer uses one `DatagramDecoder` class
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

### Multi-Datagram Detection
According to M-Bus specification, a device can indicate more data is available:
- Status byte (in Variable Data Structure) contains "DIF_MORE_RECORDS_FOLLOW" flag
- When parsing UserDataDatagram, extract this flag
- Session layer checks `has_more_datagrams` flag and automatically sends additional REQ_UD2
- All records from all datagrams are collected and returned together

---

## Layer 3: Session Layer

**File**: `session.py`
**Status**: 🚧 To be implemented

### Responsibility
Orchestrate communication flow between master and slaves. Handles datagram sequencing, retries, error recovery, and multi-datagram sequences.

### Key Responsibilities
1. **Send datagrams**: Use Transport to send bytes (encoded by Protocol)
2. **Receive datagrams**: Read bytes from Transport, decode with Protocol
3. **Retry logic**: Handle timeouts, retries on failure
4. **Multi-datagram handling**: Automatically request additional datagrams when indicated
5. **Error recovery**: Clean up state on failures
6. **Sequencing**: Ensure correct order (e.g., reset before first read)

### Key Classes

```python
class MBusSession:
    """
    Orchestrates M-Bus communication with retry logic and error handling.

    Responsibilities:
    - Send datagrams and receive responses
    - Progressive datagram decoding (feed bytes to decoder)
    - Retry logic per M-Bus specification
    - Multi-datagram sequence handling
    - Error recovery
    """

    # Dependencies
    transport: Transport
    encoder: DatagramEncoder

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
        self.encoder = DatagramEncoder()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.base_timeout = base_timeout

    # High-level operations
    async def reset_device(self, address: int) -> bool:
        """
        Send SND_NKE and wait for ACK with retries.

        Flow:
        1. Encode SND_NKE datagram
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
                datagram = await self._receive_datagram(
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

        Handles multi-datagram sequences automatically:
        - Sends REQ_UD2
        - Receives RSP_UD datagram
        - Checks has_more_datagrams flag
        - If True: sends another REQ_UD2 for next datagram
        - Collects all records from all datagrams

        Returns:
            All data records from all datagrams

        Raises:
            MBusTimeoutError: If device doesn't respond after retries
            MBusProtocolError: If validation fails after retries
        """
        all_records = []

        while True:
            # Request data
            request = self.encoder.encode_req_ud2(address)

            # Send and receive with retries
            datagram = await self._send_and_receive(
                request=request,
                expected_address=address,
                allowed_types={FrameType.LONG}  # RSP_UD is long frame
            )

            # Datagram must be UserDataDatagram
            if not isinstance(datagram, UserDataDatagram):
                raise MBusProtocolError(
                    f"Expected UserDataDatagram, got {type(datagram)}"
                )

            # Collect records
            all_records.extend(datagram.records)

            # Check for more datagrams
            if not datagram.has_more_datagrams:
                break  # Done

        return all_records

    # Core private methods
    async def _send_and_receive(
        self,
        request: bytes,
        expected_address: int | None = None,
        allowed_types: set[FrameType] | None = None
    ) -> Datagram:
        """
        Send request and receive response with retry logic.

        Implements M-Bus retry strategy:
        - Try up to max_retries times
        - On timeout: retry
        - On protocol error: retry (might be transmission corruption)
        - After max retries: raise last exception

        Args:
            request: Encoded datagram bytes to send
            expected_address: Expected device address
            allowed_types: Allowed response frame types

        Returns:
            Decoded datagram

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
                datagram = await self._receive_datagram(
                    expected_address=expected_address,
                    allowed_types=allowed_types
                )

                return datagram  # Success!

            except (MBusTimeoutError, MBusProtocolError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    # Wait before retry
                    await asyncio.sleep(self.retry_delay)
                    continue
                # Max retries exceeded - raise last exception
                raise last_exception

    async def _receive_datagram(
        self,
        expected_address: int | None = None,
        allowed_types: set[FrameType] | None = None
    ) -> Datagram:
        """
        Receive and decode datagram progressively.

        Creates decoder and feeds it bytes in small chunks until complete.
        Decoder validates each chunk immediately.

        Args:
            expected_address: Expected device address (None = any)
            allowed_types: Allowed frame types (None = any)

        Returns:
            Decoded datagram

        Raises:
            MBusTimeoutError: If any read times out
            MBusProtocolError: If validation fails
        """
        # Create decoder with expectations
        decoder = DatagramDecoder(
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

        # Get complete validated datagram
        return decoder.get_datagram()
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
- **Protocol layer is stateless**: Create new decoder for each datagram
- **Retry entire sequence**: On error, start from the beginning (send request again)
- **Progressive reading**: Feed decoder byte-by-byte as needed
- **Multi-datagram transparency**: Upper layers don't know about multiple datagrams
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
        2. Read all data (REQ_UD2, handles multi-datagram automatically)
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
│   3. _receive_datagram():                                       │
│      - Create DatagramDecoder(expected_address=5)               │
│      - Loop: bytes_needed = decoder.bytes_needed()              │
│              data = transport.read(bytes_needed)                │
│              decoder.feed(data)  # validates!                   │
│      - datagram = decoder.get_datagram()                        │
│   4. Return True if ACK                                         │
│                                                                  │
│ read_user_data(5):                                              │
│   Loop until has_more_datagrams == False:                       │
│     1. encoder.encode_req_ud2(5) → bytes                        │
│     2. _send_and_receive():                                     │
│        - transport.write(bytes)                                 │
│        - _receive_datagram() [progressive!]                     │
│     3. Collect datagram.records                                 │
│     4. Check datagram.has_more_datagrams                        │
│   Return all collected records                                  │
│                                                                  │
│ Retry logic: On error, retry entire sequence up to 3 times     │
└─────────────────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────────────────┐
│ Layer 2: Protocol (protocol.py)                                 │
│                                                                  │
│ DatagramEncoder (stateless):                                    │
│   - encode_snd_nke(5) → bytes [10 40 05 45 16]                  │
│   - encode_req_ud2(5) → bytes [10 5B 05 60 16]                  │
│                                                                  │
│ DatagramDecoder (state machine):                                │
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
│     get_datagram() → UserDataDatagram with parsed records       │
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
│ No knowledge of M-Bus protocol or datagram structure            │
└─────────────────────────────────────────────────────────────────┘
```

### Progressive Decoding Example (Long Frame with Multi-Datagram)

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
Decoder: get_datagram() → UserDataDatagram(
    address=5,
    ci_field=0x72,
    status=StatusByte(has_more=True),  ← MORE DATA AVAILABLE!
    records=[...],
    has_more_datagrams=True
)

Session: Check has_more_datagrams → True
Session: Send another REQ_UD2 to get next datagram...
Session: Repeat progressive decoding...
Session: Eventually has_more_datagrams → False
Session: Return all collected records to Master
```

---

## Implementation Scope

### What We're Implementing (Phase 1-3)

**Primary Goal**: Safely read data from M-Bus meters

**Supported**:
- Primary addressing (0-250, including broadcast 0xFF)
- Variable Data Structure (CI-field values from EN 13757-3:2018)
- Datagram types: ACK, Short Frame, Long Frame
- Data record types: All from Table 4 (integers, BCD, real, variable length, etc.)
- Multi-datagram sequences
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
- Define datagram data structures (Datagram, ACKDatagram, UserDataDatagram, etc.)
- Implement encoding functions (SND_NKE, REQ_UD2, etc.)
- Implement decoding functions (parse frames, validate checksums)
- Implement data record parsing (DIF, VIF, data extraction)

**Success criteria**: Can encode/decode all basic datagram types (tested with real hardware)

---

### Phase 2: Session Layer (Orchestration)
**Goal**: Implement communication flow and retry logic

Tasks:
- Implement MBusSession class
- Implement reset_device() with retries
- Implement read_user_data() with multi-datagram support
- Add error recovery logic per M-Bus specification

**Success criteria**: Can perform complete read sequence with multi-datagram handling (tested with real hardware)

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
**Decision**: Read and validate datagrams progressively, byte-by-byte
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

### Multi-Datagram Handling ✅
**Decision**: Session layer automatically handles multi-datagram sequences using FCB/FCV mechanism

**Critical Discovery**: The EN 13757-3:2018 spec describes DIF=1Fh for signaling "more datagrams follow" but **omits** the FCB/FCV mechanism needed to actually request the next datagram. This is documented in older specs (MBDOC48 Section 5.5.1) and confirmed through hardware testing.

**FCB/FCV Mechanism** (EN 13757-2, MBDOC48 Section 5.5):
- **FCB** (Frame Count Bit, bit 5 in C-field): Toggle this bit to signal "I received your last datagram, send me the next one"
- **FCV** (Frame Count Valid, bit 4 in C-field): Set to 1 to activate FCB mechanism
- **Protocol**: Master toggles FCB with each successful datagram reception; slave sends next datagram on FCB toggle, otherwise repeats previous datagram

**C-Field Values for REQ_UD2**:
```
Base (no FCB/FCV)  = 0x5B  # Normal single-datagram request
FCV=1, FCB=0       = 0x6B  # Multi-datagram with FCB=0
FCV=1, FCB=1       = 0x7B  # Multi-datagram with FCB=1
```

**After SND_NKE**: FCB state resets, first REQ_UD2 uses FCB=1

**Implementation**:
```python
async def read_user_data(self, address: int) -> UserDataDatagram:
    """Read user data, automatically handling multi-datagram sequences with FCB/FCV."""
    # Reset FCB state
    await self.send_nke(address)

    datagrams = []
    fcb = True  # First request after SND_NKE uses FCB=1

    while True:
        # Request with current FCB
        datagram = await self._request_datagram(address, fcb=fcb, fcv=True)
        datagrams.append(datagram)

        if not datagram.has_more_datagrams:
            break

        # Toggle FCB for next request
        fcb = not fcb

    return self._merge_datagrams(datagrams)
```

**Benefits**:
- Simple Master API - user calls once, gets all data
- Complete data retrieval following M-Bus standard
- Transparent to upper layers
- Hardware verified with real M-Bus meters

### Flexible Response Types ✅
**Decision**: Decoder can accept multiple datagram types when needed
- `allowed_types` parameter lets Session specify acceptable responses
- Example: After SND_NKE, accept either ACK or Error datagram
- Decoder validates against allowed types and throws error if mismatch

**Benefits**: Handles M-Bus spec variations, robust error handling

### Layer Boundaries ✅
**Decision**: Strict separation of responsibilities
- **Transport**: Byte I/O only, no protocol knowledge
- **Protocol**: Stateless encode/decode/validate (except decoder state machine)
- **Session**: Stateful orchestration, retry logic, multi-datagram
- **Master**: Simple user API

**Benefits**: Easy testing, clear responsibilities, maintainable code

### Error Handling: `raise` vs `assert` ✅
**Decision**: Clear distinction between external validation and internal consistency checks

**Use `raise ValueError/TypeError/etc.`** for external data validation:
- Data from outside sources (network, files, user input)
- Data we don't control
- Errors that must be handled in production
- Can occur during normal operation

**Examples**:
```python
# Validating data from network
if len(data_bytes) == 0:
    raise ValueError("data_bytes cannot be empty")

# Validating record structure from meter
if dib.vib_required and vib is None:
    raise ValueError("VIB is required for data records")

# Invalid DIF code from meter
raise ValueError(f"DIF code 0x{field_code:02X} not found")
```

**Use `assert`** for internal consistency checks:
- Checking programming errors (bugs in our code)
- Preconditions that should always be true in correct code
- Can be disabled in production with `-O` flag for performance
- Should never trigger in correct code

**Examples**:
```python
# Protecting against API misuse
assert self.special_function is None, \
    f"data_type not available for special function: {self.special_function}"

# Guaranteeing invariants
assert data_type is not None  # vib_required guarantees this

# Internal structure validation
assert len(field_chain) == field.chain_position + 1
```

**Benefits**:
- Clear distinction between external errors and internal bugs
- Production optimization: assertions can be disabled with `-O` flag
- Better error messages: `raise` for user errors, `assert` for developer errors
- Self-documenting: `assert` shows what preconditions must hold

**Rule of thumb**:
- Can a user/external system cause the error? → `raise`
- Only a programming error can cause it? → `assert`

---

## Implementation Notes

### Decisions Made During Development

**Resolved**:
- ~~How to decode progressively?~~ ✅ State machine with `bytes_needed()` / `feed()` pattern
- ~~How to handle retries?~~ ✅ Retry entire sequence, configurable count
- ~~How to handle multi-datagram?~~ ✅ Automatic using FCB/FCV toggle mechanism (MBDOC48 Section 5.5.1)
- ~~Decoder architecture?~~ ✅ Single decoder handling all frame types, internal delegation

**To Be Decided During Implementation**:
- **Checksum calculation**: Exact algorithm defined in EN 13757-2 specification
- **Multi-datagram error handling**: Retry strategy defined in M-Bus specification
- **Data record parsing approach**: Parse progressively (DIF → length → data) vs batch parse
- **`has_more_datagrams` flag**: Location defined in specification, extract during implementation
- **Manufacturer data length**: Determined from frame structure per specification
- **Error datagram structure**: Defined in M-Bus specification, implement when needed

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
- **EN 13757-2**: M-Bus Physical and Link Layer (defines FCB/FCV mechanism)
- **MBDOC48**: Older M-Bus specification with detailed FCB/FCV documentation (see `reference/Original specs (out of date)/MBDOC48/`)
- **OMS Specification**: Open Metering System extensions (see `reference/OMS/`)

---

## Status and Next Steps

### Completed ✅
- **Architecture design**: 4-layer design with clear responsibilities
- **Transport layer**: Fully implemented and tested
- **Progressive decoding strategy**: State machine approach defined
- **Error handling strategy**: Protocol validates, Session retries
- **Multi-datagram handling**: Automatic collection via flag detection
- **High-level API design**: All three layers (Protocol, Session, Master) outlined

### Ready for Implementation

The plan is now complete and ready for implementation. With the modular protocol layer structure, the implementation order is:

1. **Foundation Modules** (table systems and data types)
   - ✅ `constants.py` - Basic constants complete (may need additions during development)
   - 🚧 `data.py` - DataType enum complete, decoding functions pending
   - 🚧 `vif.py` - 65% complete, VIF/VIFE classes implemented, needs DIF context for validation
   - 🚧 `dif.py` - Core DIF/DIFE classes implemented, needs testing and possible method additions

2. **Parser Modules** (instantiate and use foundation classes)
   - `dib.py` - Parse DIF/DIFE chains by instantiating DIF/DIFE classes
   - `vib.py` - Parse VIF/VIFE chains by instantiating VIF/VIFE classes
   - `record.py` - Combine DIB + VIB + data decoding (uses data.py functions)

3. **Field Handlers** (encoding/decoding helpers)
   - `c_field.py` - C-field encoding/decoding with FCB/FCV
   - `ci_field.py` - CI-field interpretation

4. **Frame Handlers** (top-level protocol)
   - `encoder.py` - Datagram encoding (uses c_field.py, ci_field.py)
   - `decoder.py` - Progressive decoding (uses c_field.py, ci_field.py, record.py)

5. **Public API**
   - `protocol/__init__.py` - Export public interfaces

6. **Validation & Refinement**
   - Test complete flow with real hardware
   - Refine vif.py based on learnings from record.py
   - Add unit tests for all modules

**Why This Order?**:
- Build foundation modules first:
  - DataType enum and decoding functions (data.py)
  - VIF/VIFE and DIF/DIFE classes (vif.py/dif.py)
- Then build parsers that instantiate and use these classes (dib.py, vib.py)
- Then build record parser that coordinates parsers and data decoding (record.py)
- This validates vif.py/dif.py/data.py in context before moving to higher layers
- Field handlers can be built in parallel with parsers
- Frame handlers built last as they depend on everything else
- API may evolve as integration needs emerge

2. **Implement Session Layer**
   - `MBusSession` class
   - `reset_device()` method
   - `read_user_data()` method
   - Retry logic with proper error handling
   - Progressive datagram reception

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
