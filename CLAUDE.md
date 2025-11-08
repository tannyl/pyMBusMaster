## CRITICAL RULES

1. **NEVER commit changes unless explicitly asked to commit**
   - You may stage files (`git add`) when necessary
   - You may check status (`git status`) anytime
   - But DO NOT run `git commit` unless the user specifically requests it
   - The user will tell you when they want to commit changes

2. **Python Version**
   - Do not add compatibility for older Python versions that the project does not support
   - Refer to pyproject.toml for supported versions

3. **Dependencies**
   - Use `pyserial-asyncio-fast` (not the original pyserial-asyncio)
   - This is the Home Assistant maintained fork

## Project Context

- **Purpose**: Modern async Python library for M-Bus (Meter-Bus) communication
- **Target**: Home Assistant integration and general Python usage
- **Architecture**: Async-first design using asyncio
- **Import name**: `mbusmaster` (package name is pyMBusMaster)

## Development Guidelines

1. **Code Style**
   - Add type hints everywhere possible
      - Class-level annotations for all instance attributes (public and private)
      - Use shorthand union syntax `SomeType | None` instead of `Optional[SomeType]`
     - Use modern Python typing: `dict[str, Any]`, `list[int]`, etc.
      - Example:
         ```python
         class MyClass:
            # Class-level attribute annotations
            public_attr: str
            _private_attr: int | None

            def __init__(self, value: str) -> None:
                  self.public_attr = value
                  self._private_attr = None
         ```
   - Follow the configuration in pyproject.toml
   - Be judicious about creating variables which are used only once
      - **Avoid when**: The expression is simple and clear inline
         - Bad: `result = x + y; return result`
         - Good: `return x + y`
      - **Keep when**: They improve clarity for complex expressions
         - Good: `bits_per_byte = 1 + bytesize + parity_bit + stopbits`
         - Good: `base_transmission_time = (size * bits_per_byte) / baudrate`
      - **Rule of thumb**: If the variable name adds documentation value, keep it

2. **Testing**
   - Run ruff, mypy, etc. before suggesting your task is complete
   - Write tests for new functionality
   - Use pytest with pytest-asyncio for async tests
   - Aim for high code coverage

3. **Documentation**
   - Add docstrings to all public functions and classes
   - Keep TODO.md current with progress

4. **Temporary Files**
   - Create temporary test scripts, analysis files, and experimental code in `temp/`
   - The `temp/` directory is ignored by git and keeps the root directory clean
   - Organize files in subdirectories as needed (e.g., `temp/test_scripts/`, `temp/analysis/`)
   - Clean up temporary files periodically or when they're no longer needed

## Important Project Files

### When Working on TODO Items
- **ALWAYS reference PLAN.md** - Contains crucial architectural decisions, design patterns, and implementation details
- Cross-reference TODO.md sections with corresponding PLAN.md sections for full context
- The PLAN is the source of truth for implementation approach

### Critical Work Guidelines
- **ONLY work on the specific TODO sections requested** - Do NOT continue through the TODO list automatically
- **Stop after completing requested sections** - Wait for new instructions before proceeding to other tasks
- **If PLAN.md lacks sufficient detail** for requested sections - ASK for clarification rather than making assumptions
- **Better to ask than guess** - Implementation details are important and should match expectations
- **Never improvise architecture** - If design decisions aren't clear in PLAN.md, request guidance


## File Structure

```
src/        - Main package source code
tests/      - Test files
docs/       - Documentation source
examples/   - Example code
reference/  - Reference materials (ignored by git)
temp/       - Temporary analysis/test files (ignored by git)
```

## Important Notes

### Reference Directory Structure

The `reference/` directory contains a comprehensive M-Bus documentation library:

**Specifications:**
- EN 13757-2:2018 (Wired M-Bus / Link Layer)
- EN 13757-3:2018 (Application Layer)
- EN 13757-4:2019 (Wireless M-Bus)
- MBDOC48 (Older M-Bus specification with detailed FCB/FCV documentation)
- OMS specifications (Open Metering System)
- Manufacturer documentation (Carlo Gavazzi, Danfoss, Landis+Gyr, Pipersberg, Rishabh, Wachendorff)

**File Organization:**

Each specification directory contains:
```
EN 13757-X 20XX specs/
├── PDF/
│   └── original.pdf          ← Original PDF (preserved, never modified)
├── original_full.xml          ← Full XML with colors/formatting (for grep search)
├── index.json                 ← Smart index with outline + topic mappings
└── pages/                     ← Individual page files for reading with context
    ├── page_001.xml
    ├── page_002.xml
    └── ...
```

**How to Use Reference Files:**

1. **Finding Information:**
   - Load `index.json` to find relevant pages via outline or topics
   - Example: `index['topics']['FCB']` returns page numbers containing FCB

2. **Reading with Full Context:**
   - Read individual page files (e.g., `pages/page_017.xml`)
   - Each page is ~2-4KB with complete context
   - Preserves colors, formatting, and layout from original PDF

3. **Searching Across Documents:**
   - Use grep on full XML files for keyword search
   - Then read specific pages for full context

**Benefits:**
- ✅ Original PDFs preserved and never modified
- ✅ Full XML available for searching (with colors/formatting)
- ✅ 961 page files split for efficient reading with context
- ✅ 16 index files with hierarchical navigation (where available)
- ✅ Topic mappings for quick lookups

**Example Workflow:**
```python
import json

# Find pages about FCB
with open('reference/EN 13757-2 2018 specs/index.json') as f:
    index = json.load(f)

fcb_pages = index['topics']['FCB']  # Returns: [14, 16, 17]

# Read specific page with full context
Read('reference/EN 13757-2 2018 specs/pages/page_017.xml')
# Gets complete section 5.7.7 "Datagram sequencing" with all details
```