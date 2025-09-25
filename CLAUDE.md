<!-- @import .claude/CLAUDE.local.md -->

# Claude AI Assistant Instructions

This file contains important instructions and context for Claude when working on the pyMBusMaster project.

## CRITICAL RULES

1. **NEVER commit changes unless explicitly asked to commit**
   - You may stage files (`git add`) when necessary
   - You may check status (`git status`) anytime
   - But DO NOT run `git commit` unless the user specifically requests it
   - The user will tell you when they want to commit changes

2. **Python Version**
   - This project uses Python 3.13 exclusively
   - Do not add compatibility for older Python versions

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
   - Use type hints for all functions and methods
   - Follow the configuration in pyproject.toml
   - Run ruff and mypy before suggesting code is complete

2. **Testing**
   - Write tests for new functionality
   - Use pytest with pytest-asyncio for async tests
   - Aim for high code coverage

3. **Documentation**
   - Add docstrings to all public functions and classes
   - Update README.md when adding major features
   - Keep TODO.md current with progress

## File Structure

```
src/mbusmaster/     - Main package source code
tests/              - Test files
docs/               - Documentation source
examples/           - Example code
reference/          - Reference materials (ignored by git)
```

## Common Commands

```bash
# Run tests
pytest

# Type checking
mypy src/mbusmaster/

# Linting
ruff check src/ tests/

# Format code
ruff format src/ tests/
```

## Important Notes

- The `reference/` directory contains the old pyMeterBus code for reference
- Branch protection is enabled - changes must go through PRs
- The project is MIT licensed
- Designed to be a modern replacement for pyMeterBus with async support