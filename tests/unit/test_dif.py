"""Unit tests for DIF/DIFE classes and helper functions."""

import pytest

from src.mbusmaster.protocol import CommunicationDirection
from src.mbusmaster.protocol.data import DataType
from src.mbusmaster.protocol.dif import (
    DIF,
    DIFE,
    DataDIF,
    DataDIFE,
    FinalDIFE,
    SpecialDIF,
    _find_field_descriptor,
)
from src.mbusmaster.protocol.value import ValueFunction

# =============================================================================
# Test Constants - Duplicated from src for test isolation
# =============================================================================
# If these values change in production code, tests will fail and alert us

# DIF codes - Data fields
TEST_DIF_32BIT_INST = 0x04  # 0b00000100: 32-bit integer, instantaneous, no extension
TEST_DIF_32BIT_INST_EXT = 0x84  # 0b10000100: 32-bit integer, instantaneous, with extension bit
TEST_DIF_32BIT_INST_STORAGE1 = 0x44  # 0b01000100: 32-bit integer, storage bit 6 set
TEST_DIF_32BIT_MAX = 0x14  # 0b00010100: 32-bit integer, maximum function
TEST_DIF_32BIT_MIN = 0x24  # 0b00100100: 32-bit integer, minimum function
TEST_DIF_32BIT_ERR = 0x34  # 0b00110100: 32-bit integer, error function
TEST_DIF_16BIT_INST = 0x02  # 0b00000010: 16-bit integer, instantaneous
TEST_DIF_48BIT_INST_STORAGE1 = 0x46  # 0b01000110: 48-bit integer, storage bit 6 set
TEST_DIF_BCD8_INST = 0x0C  # 0b00001100: 8 digit BCD, instantaneous
TEST_DIF_READOUT_SEL = 0x08  # 0b00001000: Readout selection (master to slave)

# DIF codes - Special functions
TEST_SPECIAL_DIF_MANUFACTURER = 0x0F  # 0b00001111: Manufacturer specific data
TEST_SPECIAL_DIF_IDLE_FILLER = 0x2F  # 0b00101111: Idle filler (padding)
TEST_SPECIAL_DIF_GLOBAL_READOUT = 0x7F  # 0b01111111: Global readout request

# DIFE codes
TEST_DIFE_STORAGE_1 = 0x01  # 0b00000001: Storage bits 0-3 = 0001, no extension
TEST_DIFE_STORAGE_1_EXT = 0x81  # 0b10000001: Storage bits 0-3 = 0001, with extension
TEST_DIFE_STORAGE_FULL = 0x0F  # 0b00001111: Storage bits 0-3 = 1111, no extension
TEST_DIFE_STORAGE_FULL_EXT = 0x8F  # 0b10001111: Storage bits 0-3 = 1111, with extension
TEST_DIFE_TARIFF3 = 0x30  # 0b00110000: Tariff bits 4-5 = 11 (value 3)
TEST_DIFE_SUBUNIT1 = 0x40  # 0b01000000: Subunit bit 6 = 1
TEST_DIFE_TARIFF3_SUBUNIT1_EXT = 0xF0  # 0b11110000: Tariff=3, Subunit=1, extension
TEST_DIFE_STORAGE_5 = 0x05  # 0b00000101: Storage bits 0-3 = 0101
TEST_FINAL_DIFE = 0x00  # 0b00000000: Final DIFE marking register number

# Invalid codes for testing error conditions
TEST_INVALID_DIF = 0xFF  # 0b11111111: Invalid DIF code
TEST_INVALID_DIFE_AS_LAST = 0x8F  # Used to test exceeding chain length

# Chain length limits
TEST_DIFE_MAXIMUM_CHAIN_LENGTH = 10  # Maximum number of chained DIFE bytes

# =============================================================================
# Helper Function Tests
# =============================================================================


class TestFindFieldDescriptor:
    """Tests for _find_field_descriptor helper function."""

    def test_find_valid_data_field(self) -> None:
        """Test finding a valid data field descriptor."""
        descriptor = _find_field_descriptor(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert descriptor is not None
        assert descriptor.code == TEST_DIF_32BIT_INST

    def test_find_special_field(self) -> None:
        """Test finding a special function field descriptor."""
        descriptor = _find_field_descriptor(CommunicationDirection.SLAVE_TO_MASTER, TEST_SPECIAL_DIF_MANUFACTURER)
        assert descriptor is not None
        assert descriptor.code == TEST_SPECIAL_DIF_MANUFACTURER

    def test_invalid_field_code_raises(self) -> None:
        """Test that invalid field code raises ValueError."""
        with pytest.raises(ValueError, match="not found in DIF table"):
            _find_field_descriptor(CommunicationDirection.SLAVE_TO_MASTER, TEST_INVALID_DIF)

    def test_lru_cache_works(self) -> None:
        """Test that LRU cache returns same object on repeated calls."""
        desc1 = _find_field_descriptor(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        desc2 = _find_field_descriptor(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert desc1 is desc2  # Same object from cache


# =============================================================================
# DIF Class Tests
# =============================================================================


class TestDIF:
    """Tests for DIF base class."""

    def test_factory_creates_data_dif(self) -> None:
        """Test that DIF factory creates DataDIF for data field codes."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert isinstance(dif, DataDIF)

    def test_factory_creates_special_dif(self) -> None:
        """Test that DIF factory creates SpecialDIF for special codes."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_SPECIAL_DIF_MANUFACTURER)
        assert isinstance(dif, SpecialDIF)

    def test_bidirectional_direction_raises(self) -> None:
        """Test that BIDIRECTIONAL direction raises ValueError."""
        with pytest.raises(ValueError, match="cannot be BIDIRECTIONAL"):
            DIF(CommunicationDirection.BIDIRECTIONAL, TEST_DIF_32BIT_INST)

    def test_chain_position_is_zero(self) -> None:
        """Test that DIF has chain_position=0."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert dif.chain_position == 0

    def test_prev_field_is_none(self) -> None:
        """Test that DIF has no prev_field."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert dif.prev_field is None

    def test_create_next_dife(self) -> None:
        """Test creating next DIFE in chain."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)  # With extension bit
        dife = dif.create_next_dife(TEST_DIFE_STORAGE_1)
        assert isinstance(dife, DataDIFE)
        assert dife.chain_position == 1
        assert dife.prev_field is dif
        assert dif.next_field is dife


# =============================================================================
# DataDIF Class Tests
# =============================================================================


class TestDataDIF:
    """Tests for DataDIF class."""

    def test_data_type_extracted(self) -> None:
        """Test that data_type is extracted correctly."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert isinstance(dif, DataDIF)
        assert dif.data_type is not None
        assert DataType.B_4 in dif.data_type  # 32-bit integer

    def test_value_function_instantaneous(self) -> None:
        """Test extraction of INSTANTANEOUS function."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert isinstance(dif, DataDIF)
        assert dif.value_function == ValueFunction.INSTANTANEOUS

    def test_value_function_maximum(self) -> None:
        """Test extraction of MAXIMUM function."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_MAX)
        assert isinstance(dif, DataDIF)
        assert dif.value_function == ValueFunction.MAXIMUM

    def test_value_function_minimum(self) -> None:
        """Test extraction of MINIMUM function."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_MIN)
        assert isinstance(dif, DataDIF)
        assert dif.value_function == ValueFunction.MINIMUM

    def test_value_function_error(self) -> None:
        """Test extraction of ERROR function."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_ERR)
        assert isinstance(dif, DataDIF)
        assert dif.value_function == ValueFunction.ERROR

    def test_storage_number_bit_zero(self) -> None:
        """Test storage number extraction when bit 6 is 0."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert isinstance(dif, DataDIF)
        assert dif.storage_number == 0

    def test_storage_number_bit_one(self) -> None:
        """Test storage number extraction when bit 6 is 1."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_STORAGE1)  # Bit 6 set
        assert isinstance(dif, DataDIF)
        assert dif.storage_number == 1

    def test_last_field_no_extension(self) -> None:
        """Test last_field=True when extension bit is 0."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        assert isinstance(dif, DataDIF)
        assert dif.last_field is True

    def test_last_field_with_extension(self) -> None:
        """Test last_field=False when extension bit is 1."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)  # Extension bit set
        assert isinstance(dif, DataDIF)
        assert dif.last_field is False

    def test_readout_selection_field(self) -> None:
        """Test readout_selection flag for DIF code TEST_DIF_READOUT_SEL."""
        dif = DIF(CommunicationDirection.MASTER_TO_SLAVE, TEST_DIF_READOUT_SEL)
        assert isinstance(dif, DataDIF)
        assert dif.readout_selection is True


# =============================================================================
# SpecialDIF Class Tests
# =============================================================================


class TestSpecialDIF:
    """Tests for SpecialDIF class."""

    def test_manufacturer_data_header(self) -> None:
        """Test MANUFACTURER_DATA_HEADER special function."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_SPECIAL_DIF_MANUFACTURER)
        assert isinstance(dif, SpecialDIF)
        from src.mbusmaster.protocol.dif import _SpecialFieldFunction

        assert _SpecialFieldFunction.MANUFACTURER_DATA_HEADER in dif.special_function

    def test_idle_filler(self) -> None:
        """Test IDLE_FILLER special function."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_SPECIAL_DIF_IDLE_FILLER)
        assert isinstance(dif, SpecialDIF)
        from src.mbusmaster.protocol.dif import _SpecialFieldFunction

        assert dif.special_function == _SpecialFieldFunction.IDLE_FILLER


# =============================================================================
# DIFE Class Tests
# =============================================================================


class TestDIFE:
    """Tests for DIFE base class."""

    def test_factory_creates_data_dife(self) -> None:
        """Test that DIFE factory creates DataDIFE for non-zero codes."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife = dif.create_next_dife(TEST_DIFE_STORAGE_1)
        assert isinstance(dife, DataDIFE)

    def test_factory_creates_final_dife(self) -> None:
        """Test that DIFE factory creates FinalDIFE for 0x00."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife = dif.create_next_dife(TEST_FINAL_DIFE)
        assert isinstance(dife, FinalDIFE)

    def test_chain_linking(self) -> None:
        """Test that DIFE correctly links to previous field."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create DIFE manually to test linking
        dife = DIFE(
            field_code=TEST_DIFE_STORAGE_1,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        assert dife.prev_field is dif
        assert dif.next_field is dife

    def test_chain_position_increment(self) -> None:
        """Test that chain_position increments correctly."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create DIFEs manually to test position increment
        dife1 = DIFE(
            field_code=TEST_DIFE_STORAGE_1_EXT,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        dife2 = DIFE(
            field_code=TEST_DIFE_STORAGE_1,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dife1,
        )
        assert dife1.chain_position == 1
        assert dife2.chain_position == 2

    def test_cannot_extend_last_field(self) -> None:
        """Test that extending a last_field raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)  # No extension bit
        with pytest.raises(ValueError, match="Cannot extend.*past last field"):
            dif.create_next_dife(TEST_DIFE_STORAGE_1)

    def test_direction_mismatch_raises(self) -> None:
        """Test that direction mismatch raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Manually create DIFE with wrong direction
        with pytest.raises(ValueError, match="direction does not match"):
            DIFE(CommunicationDirection.MASTER_TO_SLAVE, TEST_DIFE_STORAGE_1, dif)


# =============================================================================
# DataDIFE Class Tests
# =============================================================================


class TestDataDIFE:
    """Tests for DataDIFE class."""

    def test_extract_storage_number_position_1(self) -> None:
        """Test storage number extraction at chain position 1."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create DIFE manually by passing prev_field
        dife = DIFE(
            field_code=TEST_DIFE_STORAGE_FULL,  # All storage bits set
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        assert isinstance(dife, DataDIFE)
        # Position 1: raw_bits=15, shift by 1 (DIF_STORAGE_NUMBER_BIT_LENGTH)
        # Result: 15 << 1 = 30
        assert dife.storage_number == 30

    def test_extract_storage_number_position_2(self) -> None:
        """Test storage number extraction at chain position 2."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create first DIFE manually
        dife1 = DIFE(
            field_code=TEST_DIFE_STORAGE_1_EXT,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        # Create second DIFE manually, linked to first
        dife2 = DIFE(
            field_code=TEST_DIFE_STORAGE_FULL,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dife1,
        )
        assert isinstance(dife2, DataDIFE)
        # Position 2: raw_bits=15, shift by (4*1 + 1) = 5
        # Result: 15 << 5 = 480
        assert dife2.storage_number == 480

    def test_extract_tariff(self) -> None:
        """Test tariff extraction."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create DIFE manually
        dife = DIFE(
            field_code=TEST_DIFE_TARIFF3,  # Tariff bits 4-5 = 11 (value 3)
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        assert isinstance(dife, DataDIFE)
        # Position 1: raw_bits=3, shift by 2*(1-1) = 0
        # Result: 3 << 0 = 3
        assert dife.tariff == 3

    def test_extract_subunit(self) -> None:
        """Test subunit extraction."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create DIFE manually
        dife = DIFE(
            field_code=TEST_DIFE_SUBUNIT1,  # Subunit bit 6 = 1
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        assert isinstance(dife, DataDIFE)
        # Position 1: raw_bit=1, shift by 1*(1-1) = 0
        # Result: 1 << 0 = 1
        assert dife.subunit == 1

    def test_last_field_detection(self) -> None:
        """Test last_field detection based on extension bit."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create first DIFE manually with extension bit set
        dife_not_last = DIFE(
            field_code=TEST_DIFE_STORAGE_1_EXT,  # Extension bit set
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        # Create second DIFE manually without extension bit
        dife_last = DIFE(
            field_code=TEST_DIFE_STORAGE_1,  # Extension bit not set
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dife_not_last,
        )
        assert isinstance(dife_not_last, DataDIFE)
        assert isinstance(dife_last, DataDIFE)
        assert dife_not_last.last_field is False
        assert dife_last.last_field is True

    def test_maximum_chain_length_exceeded(self) -> None:
        """Test that exceeding max chain length raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        current = dif
        # Create TEST_DIFE_MAXIMUM_CHAIN_LENGTH DIFEs
        for _ in range(TEST_DIFE_MAXIMUM_CHAIN_LENGTH):
            current = current.create_next_dife(TEST_DIFE_STORAGE_1_EXT)

        # Trying to add one more should fail
        with pytest.raises(ValueError, match="Exceeded maximum DIFE chain length"):
            current.create_next_dife(TEST_DIFE_STORAGE_1)

    def test_all_zeros_as_last_field_raises(self) -> None:
        """Test that DataDIFE with all zeros as last field raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Try to create a DataDIFE with 0x00 - should create FinalDIFE instead
        dife = dif.create_next_dife(0x00)
        # Factory should create FinalDIFE, not DataDIFE
        assert isinstance(dife, FinalDIFE)


# =============================================================================
# Isolated Method Tests (Bypass Factory)
# =============================================================================


class TestDataDIFIsolatedMethods:
    """Tests for DataDIF methods in isolation (bypassing __init__)."""

    def test_is_last_field_no_extension_bit(self) -> None:
        """Test _is_last_field() returns True when extension bit not set."""
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_INST  # Extension bit 7 not set (0x04)

        result = dif._is_last_field()
        assert result is True

    def test_is_last_field_with_extension_bit(self) -> None:
        """Test _is_last_field() returns False when extension bit is set."""
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_INST_EXT  # Extension bit 7 set (0x84)

        result = dif._is_last_field()
        assert result is False

    def test_extract_storage_number_isolated(self) -> None:
        """Test _extract_storage_number() method directly without __init__."""
        # Create instance bypassing factory and __init__
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_INST_STORAGE1  # Storage bit 6 set

        # Test the extraction method directly
        result = dif._extract_storage_number()
        # Bit 6 set means storage number = 1
        assert result == 1

    def test_extract_storage_number_zero_isolated(self) -> None:
        """Test _extract_storage_number() returns 0 when bit 6 not set."""
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_INST  # Storage bit 6 not set

        result = dif._extract_storage_number()
        assert result == 0

    def test_extract_function_instantaneous_isolated(self) -> None:
        """Test _extract_function() for instantaneous value."""
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_INST  # Bits 4-5 = 00 (instantaneous)

        result = dif._extract_function()
        assert result == ValueFunction.INSTANTANEOUS

    def test_extract_function_maximum_isolated(self) -> None:
        """Test _extract_function() for maximum value."""
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_MAX  # Bits 4-5 = 01 (maximum)

        result = dif._extract_function()
        assert result == ValueFunction.MAXIMUM

    def test_extract_function_minimum_isolated(self) -> None:
        """Test _extract_function() for minimum value."""
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_MIN  # Bits 4-5 = 10 (minimum)

        result = dif._extract_function()
        assert result == ValueFunction.MINIMUM

    def test_extract_function_error_isolated(self) -> None:
        """Test _extract_function() for error value."""
        dif = object.__new__(DataDIF)
        dif.field_code = TEST_DIF_32BIT_ERR  # Bits 4-5 = 11 (error)

        result = dif._extract_function()
        assert result == ValueFunction.ERROR


class TestDataDIFEIsolatedMethods:
    """Tests for DataDIFE methods in isolation (bypassing __init__)."""

    def test_is_last_field_no_extension_bit(self) -> None:
        """Test DIFE _is_last_field() returns True when extension bit not set."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_STORAGE_1  # Extension bit 7 not set (0x01)

        result = dife._is_last_field()
        assert result is True

    def test_is_last_field_with_extension_bit(self) -> None:
        """Test DIFE _is_last_field() returns False when extension bit is set."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_STORAGE_1_EXT  # Extension bit 7 set (0x81)

        result = dife._is_last_field()
        assert result is False

    def test_extract_storage_number_position_1_isolated(self) -> None:
        """Test _extract_storage_number() at position 1 without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_STORAGE_FULL  # All storage bits set (0x0F)
        dife.chain_position = 1

        result = dife._extract_storage_number()
        # Position 1: raw_bits=15, shift by 1 = 30
        assert result == 30

    def test_extract_storage_number_position_2_isolated(self) -> None:
        """Test _extract_storage_number() at position 2 without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_STORAGE_FULL  # All storage bits set (0x0F)
        dife.chain_position = 2

        result = dife._extract_storage_number()
        # Position 2: raw_bits=15, shift by (4*1 + 1) = 5, result = 480
        assert result == 480

    def test_extract_tariff_position_1_isolated(self) -> None:
        """Test _extract_tariff() at position 1 without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_TARIFF3  # Tariff bits = 11 (value 3)
        dife.chain_position = 1

        result = dife._extract_tariff()
        # Position 1: raw_bits=3, shift by 0 = 3
        assert result == 3

    def test_extract_subunit_position_1_isolated(self) -> None:
        """Test _extract_subunit() at position 1 without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_SUBUNIT1  # Subunit bit set
        dife.chain_position = 1

        result = dife._extract_subunit()
        # Position 1: raw_bit=1, shift by 0 = 1
        assert result == 1


# =============================================================================
# Async Byte Parsing Tests
# =============================================================================


class TestDIFFromBytesAsync:
    """Tests for DIF.from_bytes_async() method (integration-level)."""

    async def test_parse_single_dif_no_extension(self) -> None:
        """Test parsing single DIF without extension bit."""

        # Mock byte provider - returns single DIF byte
        async def get_next_bytes(n: int) -> bytes:
            assert n == 1
            return bytes([TEST_DIF_32BIT_INST])  # No extension bit

        result = await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        # Should return tuple with only DIF, no DIFEs
        assert len(result) == 1
        dif = result[0]
        assert isinstance(dif, DataDIF)
        assert dif.field_code == TEST_DIF_32BIT_INST
        assert dif.last_field is True

    async def test_parse_dif_with_single_dife(self) -> None:
        """Test parsing DIF + 1 DIFE chain."""
        byte_sequence = [TEST_DIF_32BIT_INST_EXT, TEST_DIFE_STORAGE_1]  # DIF with ext, DIFE without ext
        call_count = 0

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            result = bytes([byte_sequence[call_count]])
            call_count += 1
            return result

        result = await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        # Should return tuple with DIF + 1 DIFE
        assert len(result) == 2
        dif, dife = result
        assert isinstance(dif, DataDIF)
        assert isinstance(dife, DataDIFE)
        assert dif.field_code == TEST_DIF_32BIT_INST_EXT
        assert dife.field_code == TEST_DIFE_STORAGE_1
        assert dife.prev_field is dif
        assert dif.next_field is dife

    async def test_parse_long_chain(self) -> None:
        """Test parsing DIF + multiple DIFEs."""
        byte_sequence = [
            TEST_DIF_32BIT_INST_EXT,  # DIF with extension
            TEST_DIFE_STORAGE_1_EXT,  # DIFE 1 with extension
            TEST_DIFE_TARIFF3_SUBUNIT1_EXT,  # DIFE 2 with extension
            TEST_DIFE_STORAGE_5,  # DIFE 3 without extension (last)
        ]
        call_count = 0

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            result = bytes([byte_sequence[call_count]])
            call_count += 1
            return result

        result = await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        # Should return tuple with DIF + 3 DIFEs
        assert len(result) == 4
        dif = result[0]
        dife1 = result[1]
        dife2 = result[2]
        dife3 = result[3]

        assert isinstance(dif, DataDIF)
        assert isinstance(dife1, DataDIFE)
        assert isinstance(dife2, DataDIFE)
        assert isinstance(dife3, DataDIFE)

        # Verify chain linking
        assert dife1.chain_position == 1
        assert dife2.chain_position == 2
        assert dife3.chain_position == 3
        assert dife3.last_field is True

    async def test_parse_with_final_dife(self) -> None:
        """Test parsing chain ending with FinalDIFE."""
        byte_sequence = [
            TEST_DIF_32BIT_INST_EXT,  # DIF with extension
            TEST_DIFE_STORAGE_1_EXT,  # DIFE with extension
            TEST_FINAL_DIFE,  # Final DIFE (0x00)
        ]
        call_count = 0

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            result = bytes([byte_sequence[call_count]])
            call_count += 1
            return result

        result = await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        # Should return tuple with DIF + 1 DataDIFE + 1 FinalDIFE
        assert len(result) == 3
        dif = result[0]
        dife = result[1]
        final = result[2]

        assert isinstance(dif, DataDIF)
        assert isinstance(dife, DataDIFE)
        assert isinstance(final, FinalDIFE)
        assert final.last_field is True

    async def test_insufficient_dif_bytes_raises(self) -> None:
        """Test ValueError when stream provides no bytes for DIF."""

        async def get_next_bytes(n: int) -> bytes:
            return b""  # Empty bytes

        with pytest.raises(ValueError, match="Expected exactly one byte for DIF"):
            await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

    async def test_insufficient_dife_bytes_raises(self) -> None:
        """Test ValueError when stream provides no bytes for DIFE."""
        call_count = 0

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            if call_count == 0:
                call_count += 1
                return bytes([TEST_DIF_32BIT_INST_EXT])  # DIF with extension bit
            else:
                return b""  # Empty bytes for DIFE

        with pytest.raises(ValueError, match="Expected exactly one byte for DIFE"):
            await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

    async def test_parse_special_dif(self) -> None:
        """Test parsing special DIF (manufacturer data header)."""

        async def get_next_bytes(n: int) -> bytes:
            return bytes([TEST_SPECIAL_DIF_MANUFACTURER])

        result = await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        assert len(result) == 1
        dif = result[0]
        assert isinstance(dif, SpecialDIF)
        assert dif.last_field is True


# =============================================================================
# FinalDIFE Class Tests
# =============================================================================


class TestFinalDIFE:
    """Tests for FinalDIFE class."""

    def test_creation_with_zero_code(self) -> None:
        """Test that FinalDIFE is created with code 0x00."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        final = dif.create_next_dife(TEST_FINAL_DIFE)
        assert isinstance(final, FinalDIFE)
        assert final.field_code == TEST_FINAL_DIFE

    def test_must_be_last_field(self) -> None:
        """Test that FinalDIFE is always marked as last_field."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        final = dif.create_next_dife(0x00)
        assert isinstance(final, FinalDIFE)
        assert final.last_field is True

    def test_after_max_dife_allowed(self) -> None:
        """Test that FinalDIFE can appear after 10 regular DIFEs."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        current = dif
        # Create 10 regular DIFEs
        for _ in range(TEST_DIFE_MAXIMUM_CHAIN_LENGTH):
            current = current.create_next_dife(TEST_DIFE_STORAGE_1_EXT)

        # FinalDIFE should be allowed as 11th DIFE
        final = current.create_next_dife(0x00)
        assert isinstance(final, FinalDIFE)
        assert final.chain_position == TEST_DIFE_MAXIMUM_CHAIN_LENGTH + 1

    def test_exceeding_final_limit_raises(self) -> None:
        """Test that creating too many regular DIFEs raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        current = dif
        # Create TEST_DIFE_MAXIMUM_CHAIN_LENGTH regular DIFEs (max allowed)
        for _ in range(TEST_DIFE_MAXIMUM_CHAIN_LENGTH):
            current = current.create_next_dife(TEST_DIFE_STORAGE_1_EXT)

        # Trying to add another regular DIFE should fail (exceeds limit)
        with pytest.raises(ValueError, match="Exceeded maximum DIFE chain length"):
            current.create_next_dife(TEST_DIFE_STORAGE_1_EXT)  # Regular DIFE, not FinalDIFE

    def test_incorrect_code_raises(self) -> None:
        """Test that FinalDIFE with non-zero code raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Manually try to create FinalDIFE with wrong code
        # Factory won't let us, so test the validation in __init__
        # We need to bypass factory for this test
        final = object.__new__(FinalDIFE)
        with pytest.raises(ValueError, match="must match final DIFE code"):
            FinalDIFE.__init__(final, CommunicationDirection.SLAVE_TO_MASTER, TEST_DIFE_STORAGE_1, dif)


# =============================================================================
# Error Scenario Tests
# =============================================================================


class TestErrorScenarios:
    """Tests for error scenarios and edge cases."""

    def test_link_dife_already_in_chain_raises(self) -> None:
        """Test that linking a DIFE already in a chain raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Create first chain
        dife1 = DIFE(
            field_code=TEST_DIFE_STORAGE_1_EXT,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dif,
        )
        dife2 = DIFE(
            field_code=TEST_DIFE_STORAGE_1,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dife1,
        )

        # Verify chain is established
        assert dife1.next_field is dife2

        # Now try to create another DIFE with dife1 as prev_field
        # This should fail because dife1.next_field is already set to dife2
        with pytest.raises(ValueError, match="Previous field already has a next field assigned"):
            DIFE(
                field_code=TEST_DIFE_STORAGE_5,
                direction=CommunicationDirection.SLAVE_TO_MASTER,
                prev_field=dife1,  # Already has next_field set
            )

    def test_data_dife_all_zeros_as_last_field_validation(self) -> None:
        """Test DataDIFE validation for all-zeros as last field (bypass factory)."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)

        # Bypass factory to force creation of DataDIFE with all zeros
        data_dife = object.__new__(DataDIFE)
        with pytest.raises(ValueError, match="DataDIFE may not have storage number, subunit, tariff all zero"):
            # Call __init__ directly with field_code that results in all zeros
            # This simulates what would happen if factory allowed DataDIFE with 0x00
            DataDIFE.__init__(
                data_dife,
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_FINAL_DIFE,  # 0x00 - all zeros, no extension bit
                dif,
            )

    def test_final_dife_at_position_10_valid(self) -> None:
        """Test that FinalDIFE at position 10 (exactly at limit) is valid."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        current = dif

        # Create 9 regular DIFEs (positions 1-9)
        for _ in range(9):
            current = DIFE(
                field_code=TEST_DIFE_STORAGE_1_EXT,
                direction=CommunicationDirection.SLAVE_TO_MASTER,
                prev_field=current,
            )

        # DIFE at position 10 should be allowed
        dife10 = DIFE(
            field_code=TEST_DIFE_STORAGE_1_EXT,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=current,
        )
        assert dife10.chain_position == 10

        # FinalDIFE at position 11 should be allowed
        final = DIFE(
            field_code=TEST_FINAL_DIFE,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=dife10,
        )
        assert isinstance(final, FinalDIFE)
        assert final.chain_position == 11

    def test_final_dife_after_position_11_raises(self) -> None:
        """Test that FinalDIFE after position 11 raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        current = dif

        # Create 10 regular DIFEs (positions 1-10)
        for _ in range(10):
            current = DIFE(
                field_code=TEST_DIFE_STORAGE_1_EXT,
                direction=CommunicationDirection.SLAVE_TO_MASTER,
                prev_field=current,
            )

        # 11th DIFE must be FinalDIFE (position 11)
        final = DIFE(
            field_code=TEST_FINAL_DIFE,
            direction=CommunicationDirection.SLAVE_TO_MASTER,
            prev_field=current,
        )
        assert isinstance(final, FinalDIFE)

        # Trying to add anything after position 11 should fail
        with pytest.raises(ValueError, match="Exceeded maximum DIFE"):
            DIFE(
                field_code=TEST_FINAL_DIFE,
                direction=CommunicationDirection.SLAVE_TO_MASTER,
                prev_field=final,
            )
