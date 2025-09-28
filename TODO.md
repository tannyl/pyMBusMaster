# pyMBusMaster Development TODO

## 🚧 Current Phase: Project Setup

### 📋 Immediate Tasks (Week 1)

#### 0.1: Project Setup
- [ ] **0.1.1: Update devcontainer configuration**
  - [x] Add async development dependencies (pyserial-asyncio-fast, pydantic)
  - [x] Add development tools (ruff, mypy, pytest-asyncio)
  - [x] Update Python version requirements
  - [x] Add M-Bus device testing capability (EthMBus-XL gateway: ethmbus.de-la.dk:10001)

- [ ] **0.1.2: Create GitHub repository**
  - [x] Initialize new repository: `pyMBusMaster`
  - [ ] Set up repository settings (description, topics, license)
  - [ ] Configure branch protection and merge settings
  - [ ] Add repository templates (issues, PR, etc.)

- [ ] **0.1.3: Initialize project structure**
  - [x] Create modern Python project layout with `src/` structure
  - [x] Setup `pyproject.toml` with project metadata and dependencies
  - [x] Create basic package structure (`src/mbusmaster/`)
  - [x] Add initial `__init__.py` and version management
  - [x] Setup testing structure (`tests/unit/`, `tests/integration/`)
  - [ ] Create file-based module structure: `transport.py`, `protocol.py`, `master.py` (exceptions.py ✓)

- [ ] **0.1.4: Documentation setup**
  - [x] Create comprehensive README.md
  - [x] Setup documentation structure (`docs/`)
  - [ ] Create contribution guidelines (CONTRIBUTING.md)
  - [ ] Setup changelog format (CHANGELOG.md)

## 📅 Development Phases

### Phase 1: Transport Layer (Weeks 1-2)
**Goal**: Solid foundation with connection management and raw I/O

#### 1.1: Transport Layer Implementation
- [x] **1.1.1: MBusTransport class**
  - [x] Implement `__init__()` with URL parsing and timeout_margin
  - [x] Add `open()` and `close()` methods using pyserial-asyncio-fast
  - [x] Implement `is_connected()` status check
  - [x] Add `write()` method for sending bytes
  - [x] Implement `read()` with smart timeout calculation

- [ ] **1.1.2: Smart timeout calculation**
  - [ ] Calculate transmission time based on baudrate
  - [ ] Add configurable timeout_margin parameter
  - [ ] Handle different connection types (serial vs socket)
  - [ ] Implement per-operation timeout logic

- [ ] **1.1.3: Exception handling**
  - [ ] Create MBusError base class
  - [ ] Add MBusConnectionError for transport issues
  - [ ] Add MBusTimeoutError for timeout scenarios
  - [ ] Add MBusProtocolError for protocol issues
  - [ ] Implement proper error propagation

#### 1.2: Testing Transport Layer
- [ ] **1.2.1: Unit tests**
  - [ ] Test connection lifecycle (open/close)
  - [ ] Test timeout calculation logic
  - [ ] Test error handling scenarios
  - [ ] Mock serial connections for testing

- [ ] **1.2.2: Integration tests**
  - [ ] Test with real serial loopback
  - [ ] Test with TCP socket connections (EthMBus-XL: ethmbus.de-la.dk:10001)
  - [ ] Test with real M-Bus devices (3 meters available via EthMBus-XL)
  - [ ] Verify timeout behavior with slow connections

#### 1.3: Testing Infrastructure
- [ ] **1.3.1: Test setup**
  - [ ] Configure pytest-asyncio
  - [ ] Create test fixtures and mocks
  - [ ] Setup serial port simulation
  - [ ] Add test data from pyMeterBus

- [ ] **1.3.2: Continuous Integration**
  - [ ] Setup GitHub Actions for testing
  - [ ] Add code quality checks (ruff, mypy)
  - [ ] Setup test coverage reporting
  - [ ] Add multiple Python version testing

### Phase 2: Protocol Layer (Weeks 3-4)
**Goal**: Complete M-Bus protocol with class-based telegram handling

#### 2.1: Telegram Class Implementation
- [ ] **2.1.1: Base telegram classes**
  - [ ] Implement MBusTelegram base class
  - [ ] Add calculate_checksum() method
  - [ ] Create to_bytes() and from_bytes() interface
  - [ ] Add proper error handling

- [ ] **2.1.2: Outgoing telegrams (Master → Slave)**
  - [ ] Implement ShortFrame base class
  - [ ] Create SndNke class for reset commands
  - [ ] Create ReqUD2 class with FCB management
  - [ ] Add ReqUD1 class for special cases

- [ ] **2.1.3: Incoming telegrams (Slave → Master)**
  - [ ] Implement AckFrame class for single-byte ACK
  - [ ] Create LongFrame class for data responses
  - [ ] Add ControlFrame class for 9-byte responses
  - [ ] Implement frame validation and checksum verification

#### 2.2: Protocol Layer Integration
- [ ] **2.2.1: MBusProtocol class**
  - [ ] Implement FCB state management per address
  - [ ] Add build_reset_frame() method
  - [ ] Add build_request_frame() with FCB toggle
  - [ ] Create parse_response() for incoming data

- [ ] **2.2.2: Frame reading strategy**
  - [ ] Implement intelligent frame type detection
  - [ ] Add read_frame() method using transport layer
  - [ ] Handle different frame lengths correctly
  - [ ] Add timeout handling for incomplete frames

#### 2.3: Data Parsing Implementation
- [ ] **2.3.1: Variable data structure parsing**
  - [ ] Parse DIF (Data Information Field)
  - [ ] Parse VIF (Value Information Field)
  - [ ] Extract measurement values with proper scaling
  - [ ] Create MBusSlaveRecord objects

- [ ] **2.3.2: MBusSlaveData construction**
  - [ ] Parse device identification fields
  - [ ] Extract manufacturer information
  - [ ] Build list of measurement records
  - [ ] Add timestamp and metadata

#### 2.4: Testing Protocol Layer
- [ ] **2.4.1: Unit tests for telegram classes**
  - [ ] Test to_bytes() serialization
  - [ ] Test from_bytes() parsing with valid data
  - [ ] Test checksum calculation and validation
  - [ ] Test error handling with invalid data

- [ ] **2.4.2: Integration tests with real data**
  - [ ] Test with captured M-Bus telegrams
  - [ ] Verify frame reading with different device types
  - [ ] Test FCB management across multiple requests
  - [ ] Validate data parsing accuracy

### Phase 3: Application Layer (Weeks 5-6)
**Goal**: User-facing MBusMaster API and device operations

#### 3.1: MBusMaster Class Implementation
- [ ] **3.1.1: Core master functionality**
  - [ ] Implement MBusMaster __init__() with transport and protocol setup
  - [ ] Add open() and close() connection management
  - [ ] Implement is_connected() status check
  - [ ] Add context manager support (__aenter__, __aexit__)
  - [ ] Add bus_lock for safe concurrent operations

- [ ] **3.1.2: Device communication methods**
  - [ ] Implement ping_addresses() for device availability checking
  - [ ] Add query_addresses() for data collection
  - [ ] Create scan_addresses() for device discovery
  - [ ] Add timeout_margin parameter handling

- [ ] **3.1.3: Error handling and recovery**
  - [ ] Proper exception propagation from lower layers
  - [ ] Add retry logic for intermittent failures
  - [ ] Implement graceful handling of non-responsive devices
  - [ ] Add logging for debugging and monitoring

#### 3.2: Integration and Testing
- [ ] **3.2.1: End-to-end functionality**
  - [ ] Test complete ping → acknowledge flow
  - [ ] Test complete reset → request → data flow
  - [ ] Verify multi-device operations work correctly
  - [ ] Test concurrent operations with bus locking

- [ ] **3.2.2: Real device testing**
  - [ ] Test with actual M-Bus devices (3 meters via EthMBus-XL gateway)
  - [ ] Verify data accuracy against known values
  - [ ] Test with different device types and manufacturers
  - [ ] Performance testing with multiple devices
  - [ ] Test socket:// URL format with ethmbus.de-la.dk:10001

#### 3.3: Documentation and Examples
- [ ] **3.3.1: Usage examples**
  - [ ] Basic ping and query examples
  - [ ] Context manager usage patterns
  - [ ] Error handling examples
  - [ ] Multi-device monitoring example

- [ ] **3.3.2: API documentation**
  - [ ] Comprehensive docstrings for all public methods
  - [ ] Type hints for all parameters and return values
  - [ ] Clear examples in docstrings
  - [ ] Error condition documentation

### Phase 4: Integration Support (Weeks 7-8)
**Goal**: Framework integration and examples

#### 4.1: Integration Helpers
- [ ] **4.1.1: Generic integration support**
  - [ ] Create integration base classes
  - [ ] Add configuration helpers
  - [ ] Implement state synchronization
  - [ ] Add error handling patterns

- [ ] **4.1.2: Home Assistant integration**
  - [ ] Create HA integration example
  - [ ] Add entity management patterns
  - [ ] Implement configuration flow
  - [ ] Add device registry integration

#### 4.2: Examples and Documentation
- [ ] **4.2.1: Example applications**
  - [ ] Basic usage examples
  - [ ] Monitoring application
  - [ ] Data logging example
  - [ ] Web dashboard example

- [ ] **4.2.2: Documentation**
  - [ ] API documentation with Sphinx
  - [ ] Integration guides
  - [ ] Tutorial and quickstart
  - [ ] Migration guide from pyMeterBus

## 🔧 Technical Debt and Improvements

### 5.1: Code Quality
- [ ] Add comprehensive docstrings
- [ ] Implement consistent error messages
- [ ] Add performance benchmarks
- [ ] Create debugging tools

### 5.2: Testing
- [ ] Add property-based testing
- [ ] Create integration test suite
- [ ] Add stress testing
- [ ] Implement test data generation

### 5.3: Performance
- [ ] Profile async operations
- [ ] Optimize frame parsing
- [ ] Implement caching strategies for device information

## 🚀 Future Features (Beyond v1.0)

### 6.1: Protocol Extensions
- [ ] **6.1.1: Wireless M-Bus (wM-Bus)**
  - [ ] Add wireless protocol support
  - [ ] Implement encryption handling
  - [ ] Add radio communication layer

### 6.2: Advanced Features
- [ ] **6.2.1: Protocol analysis tools**
  - [ ] Frame analyzer and debugger
  - [ ] Protocol trace recording

### 6.3: User Interface
- [ ] **6.3.1: Command-line tools**
  - [ ] Device discovery CLI
  - [ ] Data reading CLI

## 📊 Success Metrics

### 7.1: Technical Metrics
- [ ] **7.1.1: Test coverage > 90%**
- [ ] **7.1.2: All functions have type hints**
- [ ] **7.1.3: Documentation coverage > 80%**

### 7.2: User Experience Metrics
- [ ] **7.2.1: Basic usage example < 10 lines of code**
- [ ] **7.2.2: Complete integration example < 50 lines**
- [ ] **7.2.3: Clear error messages for common issues**

### 7.3: Community Metrics
- [ ] **7.3.1: GitHub repository setup**
- [ ] **7.3.2: PyPI package published**
- [ ] **7.3.3: Documentation site deployed**

---

## 📝 Notes

### 8.1: Development Environment
- Using Python 3.13 exclusively (latest Python version)
- VS Code devcontainer for consistent development environment
- GitHub repository for version control and collaboration

### 8.2: Naming Decision
- **Project name**: `pyMBusMaster`
- **Package name**: `pyMBusMaster`
- **Import name**: `mbusmaster`
- **Repository**: `https://github.com/{username}/pyMBusMaster`

### 8.3: Dependencies Strategy
- Minimal runtime dependencies for broad compatibility
- Rich development dependencies for excellent DX
- Optional dependencies for framework integrations

This TODO serves as a living document that will be updated as development progresses and priorities shift.