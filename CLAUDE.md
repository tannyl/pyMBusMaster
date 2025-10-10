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
```

## Important Notes

The `reference/` directory contains
- M-Bus specifications (EN 13757-3)
- Documentation from manufacturers implementing M-Bus in their devices
- Other related files.

The original PDF files have been converted into .txt files for easy processing.

Large files have also been split up into separate files containing the different chapters.