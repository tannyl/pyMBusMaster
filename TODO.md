# TODO - pyMBusMaster Implementation

## Project Goal
Implement M-Bus master library for reading data from meters

## Current Status
- ✅ Transport layer complete and tested
- ✅ Architecture and design complete (PLAN.md)
- 🚧 Ready to start Protocol layer implementation

---

## Phase 1: Protocol Layer (Modular Implementation)

### 1.1 Foundation: Constants and Base Tables

#### constants.py - Distributed Approach
**Status**: ✅ Complete (distributed across modules)
**Strategy**: Constants are stored in their respective modules for better cohesion:
- `constants.py` → Frame/transport layer constants (START, STOP, ACK, C-field, CI-field, addresses)
- `protocol/common.py` → CommunicationDirection enum
- `protocol/dif.py` → DIF/DIFE bit masks and constants
- `protocol/vif.py` → VIF/VIFE table entries and constants

**Transport layer constants** (constants.py):
- [x] Extract frame structure constants (START, STOP, ACK bytes)
- [x] Extract address constants (broadcast, no station, reserved)
- [x] Extract C-field values (SND_NKE, REQ_UD2, etc.) with FCB/FCV support
- [x] Extract CI-field values from EN 13757-3:2018
- [x] Extract device type constants
- [x] Organize with IntEnum classes and helper functions
- [x] Add spec references as comments

**Protocol layer constants** (in respective modules):
- [x] DIF/DIFE constants → protocol/dif.py
- [x] VIF/VIFE constants → protocol/vif.py
- [x] CommunicationDirection → protocol/common.py
- [ ] Add missing constants discovered during implementation

#### data.py - Data Type System (🚧 Partially Complete)
**Architecture**: Enum-based data type definitions with decoding functions
- [x] Implement DataType enum (EN 13757-3:2018 Annex A)
  - [x] All 13 data types defined (A, B, C, D, F, G, H, I, J, K, L, M, LVAR)
- [ ] Implement data decoding functions:
  - [ ] `decode_type_a(data: bytes) -> int` - Unsigned BCD
  - [ ] `decode_type_b(data: bytes) -> int` - Signed binary integer
  - [ ] `decode_type_c(data: bytes) -> int` - Unsigned binary integer
  - [ ] `decode_type_d(data: bytes) -> list[bool]` - Boolean bit array
  - [ ] `decode_type_f(data: bytes) -> datetime` - Date/Time CP32
  - [ ] `decode_type_g(data: bytes) -> date` - Date CP16
  - [ ] `decode_type_h(data: bytes) -> float` - IEEE 754 floating point
  - [ ] `decode_type_i(data: bytes) -> datetime` - Date/Time CP48
  - [ ] `decode_type_j(data: bytes) -> time` - Time CP24
  - [ ] `decode_type_k(data: bytes) -> dict` - Daylight savings
  - [ ] `decode_type_l(data: bytes) -> dict` - Listening window management
  - [ ] `decode_type_m(data: bytes, lvar: int) -> datetime | timedelta` - Date/Time or duration
  - [ ] `decode_lvar(data: bytes, lvar: int) -> Any` - Variable length data (Table 5)
- [ ] Test with real meter data
- [ ] Add unit tests

#### vif.py - VIF/VIFE Table System (🚧 65% Complete)
**Architecture**: Class-based with VIF/VIFE as entry points
- [x] Implement VIF class (primary VIF byte parser)
- [x] Implement VIFE class (VIFE extension byte parser)
- [x] Implement _VIFAbstract base class with shared functionality
- [x] Implement TableEnum metaclass with range-based lookup
- [x] Implement _FieldDescriptor metadata structure
- [x] Implement ValueTransform enum with transform functions
- [x] Implement DataTypeRule system for VIF/DIF constraints
- [x] Implement PrimaryTable (EN 13757-3 Table 10)
- [x] Implement FirstExtensionTable (Table 14)
- [x] Implement SecondExtensionTable (Table 12)
- [x] Implement CombinableOrthogonalTable (Table 15)
- [x] Implement CombinableExtensionTable (Table 16)
- [x] Test with real meter data (164/164 VIF/VIFEs matched)
- [x] Implement helper methods:
  - [x] `create_next_vife()` - Chain VIFE creation
  - [x] `get_data_type_rules()` - Data type constraints
  - [x] `_validate_field_code()` - Input validation
- [ ] Validate interpretations with DIF context (after record.py)
- [ ] Fix phase information display (L1/L2/L3)
- [ ] Refine VIFE combination semantics
- [ ] Add unit tests
- [ ] Add additional helper methods as needed during integration

#### dif.py - DIF/DIFE Table System (✅ Complete - pending real-world testing)
**Architecture**: Class-based with DIF/DIFE as entry points, async from_bytes_async() pattern
- [x] Implement DIF class (primary DIF byte parser)
- [x] Implement DIFE class (DIFE extension byte parser)
- [x] Implement DataDIF and SpecialDIF subclasses
- [x] Implement DataDIFE and FinalDIFE subclasses
- [x] Implement _FieldDescriptor structure for DIF metadata
- [x] Implement _FunctionDescriptor structure
- [x] Implement _FieldTable enum (EN 13757-3 Table 4 & 6)
- [x] Implement _FunctionTable enum (Table 7)
- [x] Implement _SpecialFieldFunction flags
- [x] Implement helper methods:
  - [x] `create_next_dife()` - Chain DIFE creation
  - [x] `from_bytes_async()` - Async byte stream parsing
  - [x] `_find_field_descriptor()` - Cached lookup with LRU cache
- [x] Implement FinalDIFE class for OBIS register numbers (0x00)
- [x] DIF/DIFE constants stored in module
- [x] Add comprehensive unit tests (65 tests in tests/unit/test_dif.py)
- [ ] Test with real meter data
- [ ] Add additional helper methods as needed during integration

### 1.2 Block Parsers (DIB/VIB/DRH)

#### dib.py - DIB Block Parser (🚧 In Progress)
**Architecture**: Class-based DIB with DIF/DIFE chain parsing via async from_bytes_async()
**Uses**: `DIF` and `DIFE` classes from dif.py
- [x] Define `DIB` class structure
- [ ] Implement `from_bytes_async()` async parsing method
- [ ] Instantiate `DIF(field_code)` for primary DIF byte
- [ ] Parse DIFE chain by calling `DIF.from_bytes_async()`
- [ ] Calculate storage number from DIF + DIFEs using class attributes
- [ ] Extract tariff and subunit from DIFE instances
- [ ] Extract data type/length/function from DIF instance
- [ ] Implement DIB subclasses (DataDIB, SpecialDIB, etc.)
- [ ] Test with real meter data

#### vib.py - VIB Block Parser (🚧 In Progress)
**Architecture**: Class-based VIB with VIF/VIFE chain parsing via async from_bytes_async()
**Uses**: `VIF` and `VIFE` classes from vif.py
- [x] Define `VIB` class structure
- [ ] Implement `from_bytes_async()` async parsing method
- [ ] Instantiate `VIF(field_code)` for primary VIF byte
- [ ] Parse VIFE chain by calling `VIF.from_bytes_async()`
- [ ] Handle extension pointers (0xFB, 0xFD) via automatic table selection
- [ ] Combine VIFE modifiers semantically using field descriptors
- [ ] Extract unit/transform/description from VIF/VIFE instances
- [ ] Test with real meter data

#### drh.py - Data Record Header (DIB + VIB) (🚧 In Progress)
**Architecture**: Combines DIB and VIB with validation
**Uses**: `DIB` from dib.py and `VIB` from vib.py
- [x] Define `DRH` class structure
- [ ] Implement `from_bytes_async()` async parsing method
- [ ] Parse DIB using `DIB.from_bytes_async()`
- [ ] Parse VIB using `VIB.from_bytes_async()` (if required)
- [ ] Validate DIB/VIB compatibility (data type rules)
- [ ] Handle special-function DIBs (no VIB required)
- [ ] Resolve final data type from DIB + VIB data rules
- [ ] Test with real meter data

### 1.3 Data Record Parsing

#### record.py - Data Record Parser (🚧 In Progress)
**Architecture**: Uses DRH for complete header parsing, coordinates data decoding
**Uses**: `DRH` from drh.py, `decode_*` functions from data.py
- [x] Define basic `DataRecord` dataclass structure
- [ ] Implement `parse_records(payload)` function
- [ ] Parse complete headers using `DRH.from_bytes_async()`
- [ ] Extract raw value based on DIF data type
- [ ] Apply VIF value transformations
- [ ] Handle special DIFs (0x0F, 0x1F manufacturer data)
- [ ] Handle variable length data (LVAR)
- [ ] Test with real meter data
- [ ] **Validate vif.py interpretations in context**

### 1.4 Field Handlers

#### c_field.py - C-Field Handling
- [ ] Implement `encode_c_field(command, fcb, fcv)` function
- [ ] Implement `decode_c_field(c_field)` function
- [ ] Handle FCB/FCV bit manipulation
- [ ] Test encoding/decoding

#### ci_field.py - CI-Field Interpretation
- [ ] Define `CIInfo` dataclass
- [ ] Implement `interpret_ci_field(ci)` function
- [ ] Detect data structure type (variable/fixed)
- [ ] Handle manufacturer specific CIs
- [ ] Test with real meter data

### 1.5 Frame Handlers

#### encoder.py - Datagram Encoder
- [ ] Define `DatagramEncoder` class
- [ ] Implement `encode_snd_nke(address)` - device reset
- [ ] Implement `encode_req_ud2(address, fcb, fcv)` - request user data
- [ ] Implement `encode_req_ud1(address)` - request alarm
- [ ] Implement `_calculate_checksum(data)` helper
- [ ] Use c_field.py for C-field encoding
- [ ] Test with real hardware

#### decoder.py - Progressive Datagram Decoder
- [ ] Define `DecoderState` enum
- [ ] Define `DatagramDecoder` class
- [ ] Implement `__init__(expected_address, allowed_types)`
- [ ] Implement `bytes_needed()` method
- [ ] Implement `feed(data)` method with progressive validation
- [ ] Implement `is_complete()` method
- [ ] Implement `get_datagram()` method
- [ ] Implement `_validate_start()` - detect frame type
- [ ] Implement `_validate_length()` - L-field validation
- [ ] Implement `_validate_checksum()` - frame checksum
- [ ] Implement `_advance_state()` - state transitions
- [ ] Implement internal frame type handlers (ACK, Short, Long)
- [ ] Use c_field.py and ci_field.py for field decoding
- [ ] Use record.py for payload parsing
- [ ] Test with real hardware

### 1.6 Datagram Data Structures
- [ ] Define base `Datagram` class
- [ ] Define `ACKDatagram` class
- [ ] Define `ShortFrameDatagram` class
- [ ] Define `UserDataDatagram` class (with status, records, has_more_datagrams)
- [ ] Define supporting classes (StatusByte, etc.)

### 1.7 Public API

#### protocol/__init__.py
- [ ] Export DatagramEncoder
- [ ] Export DatagramDecoder
- [ ] Export DataRecord and parse_records
- [ ] Export all datagram types
- [ ] Export supporting classes
- [ ] Define __all__ list

### 1.8 Validation & Testing
- [ ] Test complete protocol flow with real hardware
- [ ] Refine vif.py based on learnings from record.py
- [ ] Add unit tests for all modules
- [ ] Verify all VIF/VIFE combinations work correctly
- [ ] Verify phase information displays correctly

**Phase 1 Success Criteria**:
- Can encode/decode all basic datagram types with real hardware
- VIF/VIFE interpretations validated in DIF context
- All modules tested independently and together

---

## Phase 2: Session Layer (Orchestration)

### 2.1 Session Class Setup
- [ ] Create `MBusSession` class
- [ ] Add configuration parameters (max_retries, retry_delay, base_timeout)
- [ ] Initialize with Transport and DatagramEncoder

### 2.2 Core Session Methods
- [ ] Implement `reset_device(address)` with retry logic
- [ ] Implement `_receive_datagram()` with progressive reading
- [ ] Implement `_send_and_receive()` with retry logic
- [ ] Test reset with real hardware using dev_mbus_test.py

### 2.3 Multi-Datagram Support
- [ ] Implement `read_user_data(address)` with multi-datagram loop
- [ ] Handle has_more_datagrams flag
- [ ] Collect records from all datagrams
- [ ] Test with real hardware using dev_mbus_test.py

### 2.4 Error Recovery
- [ ] Implement retry logic per M-Bus specification
- [ ] Handle timeout errors
- [ ] Handle protocol validation errors
- [ ] Test error scenarios with real hardware

**Phase 2 Success Criteria**: Can perform complete read sequence with multi-datagram handling

---

## Phase 3: Master API (User Interface)

### 3.1 Master Class
- [ ] Create `MBusMaster` class
- [ ] Implement `__init__` with connection parameters
- [ ] Implement `connect()` method
- [ ] Implement `disconnect()` method
- [ ] Implement context manager (`__aenter__`, `__aexit__`)

### 3.2 User-Facing Methods
- [ ] Implement `read_meter(address)` - main use case
- [ ] Create `MeterData` result wrapper class
- [ ] Add helper methods (get_value, get_all_values)
- [ ] Test with real hardware using dev_mbus_test.py

### 3.3 Documentation
- [ ] Add docstrings to all public methods
- [ ] Create usage examples in dev_mbus_test.py

**Phase 3 Success Criteria**: Users can read meter data with single method call

---

## Phase 4: Formal Testing (After Implementation)

### 4.1 Unit Tests
- [ ] Protocol layer: Test encoding/decoding with known test vectors
- [ ] Protocol layer: Test checksum calculation
- [ ] Protocol layer: Test data record parsing
- [ ] Session layer: Test with mocked Transport
- [ ] Session layer: Test retry logic
- [ ] Master layer: Test with mocked Session

### 4.2 Integration Tests
- [ ] Full stack: Test with simulated M-Bus devices
- [ ] Test multi-datagram sequences
- [ ] Test error scenarios and recovery

### 4.3 Test Organization
- [ ] Move tests to `tests/` directory
- [ ] Clean up dev_mbus_test.py

---

## Future Features (Phase 4+)

- [ ] Secondary addressing (12-digit ID selection)
- [ ] Alarm reading (REQ_UD1)
- [ ] Device scanning/discovery
- [ ] Baud rate switching
- [ ] Clock synchronization
- [ ] Encrypted communication (AES)

---

## Notes

- Test frequently with real hardware (ethmbus.de-la.dk:10001, addresses 1, 5, 10)
- Use `dev_mbus_test.py` for ongoing testing (not in git)
- Refer to EN 13757-3:2018 specification for all implementation details
- Formal unit/integration tests written at the END
