# TODO - pyMBusMaster Implementation

## Project Goal
Implement M-Bus master library for reading data from meters

## Current Status
- ✅ Transport layer complete and tested
- ✅ Architecture and design complete (PLAN.md)
- 🚧 Ready to start Protocol layer implementation

---

## Phase 1: Protocol Layer (Foundation)

### 1.1 Constants File (`constants.py`)
- [ ] Extract frame structure constants (START, STOP, ACK bytes)
- [ ] Extract address constants (broadcast, no station, reserved)
- [ ] Extract C-field values (SND_NKE, REQ_UD2, etc.)
- [ ] Extract CI-field values from EN 13757-3:2018
- [ ] Extract DIF constants (data types, special functions, function fields)
- [ ] Extract LVAR interpretation ranges
- [ ] Extract VIF/VIFE codes (Tables 10-16)
- [ ] Extract device type constants
- [ ] Extract BCD error codes
- [ ] Organize with IntEnum classes and helper functions
- [ ] Add spec references as comments

### 1.2 Telegram Data Structures
- [ ] Define base `Telegram` class
- [ ] Define `ACKTelegram` class
- [ ] Define `ShortFrameTelegram` class
- [ ] Define `UserDataTelegram` class (with status, records, has_more_telegrams)
- [ ] Define `DataRecord` class (DIF, VIF, data)
- [ ] Define supporting classes (StatusByte, DIFInfo, VIFInfo, etc.)

### 1.3 Telegram Encoder (`TelegramEncoder`)
- [ ] Implement `encode_snd_nke(address)` - device reset
- [ ] Implement `encode_req_ud2(address)` - request user data
- [ ] Implement `encode_req_ud1(address)` - request alarm
- [ ] Implement checksum calculation helper
- [ ] Test with real hardware using dev_mbus_test.py

### 1.4 Telegram Decoder (`TelegramDecoder`)
- [ ] Implement state machine (DecoderState enum)
- [ ] Implement `__init__` with expected_address and allowed_types
- [ ] Implement `bytes_needed()` method
- [ ] Implement `feed(data)` method with progressive validation
- [ ] Implement `is_complete()` method
- [ ] Implement `get_telegram()` method
- [ ] Implement `_validate_start()` - detect frame type
- [ ] Implement `_validate_length()` - L-field validation
- [ ] Implement `_validate_checksum()` - frame checksum
- [ ] Implement `_advance_state()` - state transitions
- [ ] Implement internal frame type handlers (ACK, Short, Long)
- [ ] Test with real hardware using dev_mbus_test.py

### 1.5 Data Record Parsing
- [ ] Design data record parsing approach (progressive vs batch)
- [ ] Implement DIF/DIFE parsing
- [ ] Implement VIF/VIFE parsing
- [ ] Implement data extraction based on DIF type
- [ ] Handle variable length data (LVAR)
- [ ] Parse manufacturer data (after 0x0F/0x1F marker)
- [ ] Extract has_more_telegrams flag from status
- [ ] Test with real hardware using dev_mbus_test.py

**Phase 1 Success Criteria**: Can encode/decode all basic telegram types with real hardware

---

## Phase 2: Session Layer (Orchestration)

### 2.1 Session Class Setup
- [ ] Create `MBusSession` class
- [ ] Add configuration parameters (max_retries, retry_delay, base_timeout)
- [ ] Initialize with Transport and TelegramEncoder

### 2.2 Core Session Methods
- [ ] Implement `reset_device(address)` with retry logic
- [ ] Implement `_receive_telegram()` with progressive reading
- [ ] Implement `_send_and_receive()` with retry logic
- [ ] Test reset with real hardware using dev_mbus_test.py

### 2.3 Multi-Telegram Support
- [ ] Implement `read_user_data(address)` with multi-telegram loop
- [ ] Handle has_more_telegrams flag
- [ ] Collect records from all telegrams
- [ ] Test with real hardware using dev_mbus_test.py

### 2.4 Error Recovery
- [ ] Implement retry logic per M-Bus specification
- [ ] Handle timeout errors
- [ ] Handle protocol validation errors
- [ ] Test error scenarios with real hardware

**Phase 2 Success Criteria**: Can perform complete read sequence with multi-telegram handling

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
- [ ] Test multi-telegram sequences
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
