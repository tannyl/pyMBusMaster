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
    _SpecialFieldFunction,
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
TEST_SPECIAL_DIF_MORE_RECORDS = 0x1F  # 0b00011111: Manufacturer data + more records follow
TEST_SPECIAL_DIF_IDLE_FILLER = 0x2F  # 0b00101111: Idle filler (padding)
TEST_SPECIAL_DIF_GLOBAL_READOUT = 0x7F  # 0b01111111: Global readout request

# DIFE codes
TEST_DIFE_STORAGE_1 = 0x01  # 0b00000001: Storage bits 0-3 = 0001, no extension
TEST_DIFE_STORAGE_1_EXT = 0x81  # 0b10000001: Storage bits 0-3 = 0001, with extension
TEST_DIFE_STORAGE_FULL = 0x0F  # 0b00001111: Storage bits 0-3 = 1111 (all bits set)
TEST_DIFE_STORAGE_FULL_EXT = 0x8F  # 0b10001111: Storage bits 0-3 = 1111 (all bits set), with extension
TEST_DIFE_TARIFF_FULL = 0x30  # 0b00110000: Tariff bits 4-5 = 11 (all bits set, value 3)
TEST_DIFE_SUBUNIT_FULL = 0x40  # 0b01000000: Subunit bit 6 = 1 (bit set)
TEST_DIFE_TARIFF_SUBUNIT_FULL_EXT = 0xF0  # 0b11110000: Tariff=3, Subunit=1 (all bits set), extension
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

    @pytest.mark.parametrize(
        ("dif_code", "expected_type"),
        [
            (TEST_DIF_32BIT_INST, DataDIF),
            (TEST_SPECIAL_DIF_MANUFACTURER, SpecialDIF),
        ],
    )
    def test_factory_creates_correct_type(self, dif_code: int, expected_type: type) -> None:
        """Test that DIF factory creates correct subclass based on DIF code."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        assert isinstance(dif, expected_type)

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

    @pytest.mark.parametrize(
        ("dif_code", "expected_function"),
        [
            (TEST_DIF_32BIT_INST, ValueFunction.INSTANTANEOUS),
            (TEST_DIF_32BIT_MAX, ValueFunction.MAXIMUM),
            (TEST_DIF_32BIT_MIN, ValueFunction.MINIMUM),
            (TEST_DIF_32BIT_ERR, ValueFunction.ERROR),
        ],
    )
    def test_value_function_from_dif(self, dif_code: int, expected_function: ValueFunction) -> None:
        """Test that value_function is correctly extracted from DIF."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        assert isinstance(dif, DataDIF)
        assert dif.value_function == expected_function

    @pytest.mark.parametrize(
        ("dif_code", "expected_storage"),
        [
            (TEST_DIF_32BIT_INST, 0),  # Storage bit 6 = 0
            (TEST_DIF_32BIT_INST_STORAGE1, 1),  # Storage bit 6 = 1
        ],
    )
    def test_storage_number_from_dif_only(self, dif_code: int, expected_storage: int) -> None:
        """Test storage number extraction from DIF alone (no DIFEs)."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        assert isinstance(dif, DataDIF)
        assert dif.storage_number == expected_storage

    @pytest.mark.parametrize(
        ("dif_code", "expected_last_field"),
        [
            (TEST_DIF_32BIT_INST, True),  # No extension bit
            (TEST_DIF_32BIT_INST_EXT, False),  # Extension bit set
        ],
    )
    def test_last_field_detection(self, dif_code: int, expected_last_field: bool) -> None:
        """Test last_field detection based on extension bit."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        assert isinstance(dif, DataDIF)
        assert dif.last_field is expected_last_field

    @pytest.mark.parametrize(
        ("dif_code", "direction", "expected_readout_selection"),
        [
            (TEST_DIF_READOUT_SEL, CommunicationDirection.MASTER_TO_SLAVE, True),
            (TEST_DIF_32BIT_INST, CommunicationDirection.SLAVE_TO_MASTER, False),
        ],
    )
    def test_readout_selection_field(
        self, dif_code: int, direction: CommunicationDirection, expected_readout_selection: bool
    ) -> None:
        """Test readout_selection flag is correctly set based on DIF code."""
        dif = DIF(direction, dif_code)
        assert isinstance(dif, DataDIF)
        assert dif.readout_selection is expected_readout_selection


# =============================================================================
# SpecialDIF Class Tests
# =============================================================================


class TestSpecialDIF:
    """Tests for SpecialDIF class."""

    @pytest.mark.parametrize(
        ("dif_code", "direction", "expected_function"),
        [
            (
                TEST_SPECIAL_DIF_MANUFACTURER,
                CommunicationDirection.SLAVE_TO_MASTER,
                _SpecialFieldFunction.MANUFACTURER_DATA_HEADER,
            ),
            (
                TEST_SPECIAL_DIF_MORE_RECORDS,
                CommunicationDirection.SLAVE_TO_MASTER,
                _SpecialFieldFunction.MANUFACTURER_DATA_HEADER | _SpecialFieldFunction.MORE_RECORDS_FOLLOW,
            ),
            (
                TEST_SPECIAL_DIF_IDLE_FILLER,
                CommunicationDirection.SLAVE_TO_MASTER,
                _SpecialFieldFunction.IDLE_FILLER,
            ),
            (
                TEST_SPECIAL_DIF_GLOBAL_READOUT,
                CommunicationDirection.MASTER_TO_SLAVE,
                _SpecialFieldFunction.GLOBAL_READOUT,
            ),
        ],
    )
    def test_special_function_extraction(
        self, dif_code: int, direction: CommunicationDirection, expected_function: _SpecialFieldFunction
    ) -> None:
        """Test that special_function is correctly extracted from SpecialDIF codes."""
        dif = DIF(direction, dif_code)
        assert isinstance(dif, SpecialDIF)
        assert dif.special_function == expected_function


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
            field_code=TEST_DIFE_TARIFF_FULL,  # Tariff bits 4-5 = 11 (value 3)
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
            field_code=TEST_DIFE_SUBUNIT_FULL,  # Subunit bit 6 = 1
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


# =============================================================================
# Isolated Method Tests (Bypass Factory)
# =============================================================================


class TestDataDIFIsolatedMethods:
    """Tests for DataDIF methods in isolation (bypassing __init__)."""

    @pytest.mark.parametrize(
        ("field_code", "expected_result"),
        [
            (TEST_DIF_32BIT_INST, True),  # Extension bit not set
            (TEST_DIF_32BIT_INST_EXT, False),  # Extension bit set
        ],
    )
    def test_is_last_field_isolated(self, field_code: int, expected_result: bool) -> None:
        """Test _is_last_field() method directly without __init__."""
        dif = object.__new__(DataDIF)
        dif.field_code = field_code

        result = dif._is_last_field()
        assert result is expected_result

    @pytest.mark.parametrize(
        ("field_code", "expected_storage"),
        [
            (TEST_DIF_32BIT_INST, 0),  # Storage bit 6 not set
            (TEST_DIF_32BIT_INST_STORAGE1, 1),  # Storage bit 6 set
        ],
    )
    def test_extract_storage_number_isolated(self, field_code: int, expected_storage: int) -> None:
        """Test _extract_storage_number() method directly without __init__."""
        dif = object.__new__(DataDIF)
        dif.field_code = field_code

        result = dif._extract_storage_number()
        assert result == expected_storage

    @pytest.mark.parametrize(
        ("field_code", "expected_function"),
        [
            (TEST_DIF_32BIT_INST, ValueFunction.INSTANTANEOUS),  # Bits 4-5 = 00
            (TEST_DIF_32BIT_MAX, ValueFunction.MAXIMUM),  # Bits 4-5 = 01
            (TEST_DIF_32BIT_MIN, ValueFunction.MINIMUM),  # Bits 4-5 = 10
            (TEST_DIF_32BIT_ERR, ValueFunction.ERROR),  # Bits 4-5 = 11
        ],
    )
    def test_extract_function_isolated(self, field_code: int, expected_function: ValueFunction) -> None:
        """Test _extract_function() method directly without __init__."""
        dif = object.__new__(DataDIF)
        dif.field_code = field_code

        result = dif._extract_function()
        assert result == expected_function


class TestDataDIFEIsolatedMethods:
    """Tests for DataDIFE methods in isolation (bypassing __init__)."""

    @pytest.mark.parametrize(
        ("field_code", "expected_result"),
        [
            (TEST_DIFE_STORAGE_1, True),  # Extension bit not set
            (TEST_DIFE_STORAGE_1_EXT, False),  # Extension bit set
        ],
    )
    def test_is_last_field_isolated(self, field_code: int, expected_result: bool) -> None:
        """Test DIFE _is_last_field() method directly without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = field_code

        result = dife._is_last_field()
        assert result is expected_result

    @pytest.mark.parametrize(
        ("chain_position", "expected_storage"),
        [
            (1, 30),  # Position 1: shift=1, 15 << 1 = 30
            (5, 1966080),  # Position 5: shift=17, 15 << 17 = 1966080
            (10, 2061584302080),  # Position 10: shift=37, 15 << 37 = 2061584302080
        ],
    )
    def test_extract_storage_number_isolated(self, chain_position: int, expected_storage: int) -> None:
        """Test _extract_storage_number() at different positions without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_STORAGE_FULL  # All storage bits set
        dife.chain_position = chain_position

        result = dife._extract_storage_number()
        assert result == expected_storage

    @pytest.mark.parametrize(
        ("chain_position", "expected_tariff"),
        [
            (1, 3),  # Position 1: shift=0, 3 << 0 = 3
            (5, 768),  # Position 5: shift=8, 3 << 8 = 768
            (10, 786432),  # Position 10: shift=18, 3 << 18 = 786432
        ],
    )
    def test_extract_tariff_isolated(self, chain_position: int, expected_tariff: int) -> None:
        """Test _extract_tariff() at different positions without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_TARIFF_FULL  # All tariff bits set
        dife.chain_position = chain_position

        result = dife._extract_tariff()
        assert result == expected_tariff

    @pytest.mark.parametrize(
        ("chain_position", "expected_subunit"),
        [
            (1, 1),  # Position 1: 1 << 0 = 1
            (5, 16),  # Position 5: 1 << 4 = 16
            (10, 512),  # Position 10: 1 << 9 = 512
        ],
    )
    def test_extract_subunit_isolated(self, chain_position: int, expected_subunit: int) -> None:
        """Test _extract_subunit() at different positions without __init__."""
        dife = object.__new__(DataDIFE)
        dife.field_code = TEST_DIFE_SUBUNIT_FULL  # Subunit bit set
        dife.chain_position = chain_position

        result = dife._extract_subunit()
        assert result == expected_subunit


# =============================================================================
# Async Byte Parsing Tests
# =============================================================================


class TestDIFFromBytesAsync:
    """Tests for DIF.from_bytes_async() method (integration-level)."""

    @pytest.mark.parametrize(
        ("byte_sequence", "expected_types"),
        [
            # Single DIF, no extension
            (
                [TEST_DIF_32BIT_INST],
                [DataDIF],
            ),
            # DIF + 1 DIFE
            (
                [TEST_DIF_32BIT_INST_EXT, TEST_DIFE_STORAGE_1],
                [DataDIF, DataDIFE],
            ),
            # Long chain - DIF + 3 DIFEs
            (
                [
                    TEST_DIF_32BIT_INST_EXT,
                    TEST_DIFE_STORAGE_1_EXT,
                    TEST_DIFE_TARIFF_SUBUNIT_FULL_EXT,
                    TEST_DIFE_STORAGE_5,
                ],
                [DataDIF, DataDIFE, DataDIFE, DataDIFE],
            ),
            # DIF + DIFE + FinalDIFE
            (
                [TEST_DIF_32BIT_INST_EXT, TEST_DIFE_STORAGE_1_EXT, TEST_FINAL_DIFE],
                [DataDIF, DataDIFE, FinalDIFE],
            ),
        ],
    )
    async def test_parse_dif_chain(
        self,
        byte_sequence: list[int],
        expected_types: list[type],
    ) -> None:
        """Test parsing DIF chains with various DIFE configurations."""
        call_count = 0
        max_calls = len(byte_sequence)

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            assert call_count < max_calls
            result = bytes([byte_sequence[call_count]])
            call_count += 1
            return result

        result = await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        # Verify chain length
        assert len(result) == len(expected_types)

        # Verify types and chain positions
        for i, (field, expected_type) in enumerate(zip(result, expected_types, strict=True)):
            assert isinstance(field, expected_type)
            assert field.chain_position == i

        # Verify last field property
        assert result[-1].last_field is True

    async def test_insufficient_dif_bytes_raises(self) -> None:
        """Test ValueError when stream provides no bytes for DIF."""
        byte_sequence = [[]]  # Empty bytes
        call_count = 0
        max_calls = len(byte_sequence)

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            assert call_count < max_calls
            result = bytes(byte_sequence[call_count])
            call_count += 1
            return result

        with pytest.raises(ValueError, match="Expected exactly one byte for DIF"):
            await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

    async def test_insufficient_dife_bytes_raises(self) -> None:
        """Test ValueError when stream provides no bytes for DIFE."""
        byte_sequence = [
            [TEST_DIF_32BIT_INST_EXT],  # DIF with extension bit
            [],  # Empty bytes for DIFE
        ]
        call_count = 0
        max_calls = len(byte_sequence)

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            assert call_count < max_calls
            result = bytes(byte_sequence[call_count])
            call_count += 1
            return result

        with pytest.raises(ValueError, match="Expected exactly one byte for DIFE"):
            await DIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

    async def test_parse_special_dif(self) -> None:
        """Test parsing special DIF (manufacturer data header)."""
        byte_sequence = [TEST_SPECIAL_DIF_MANUFACTURER]
        call_count = 0
        max_calls = len(byte_sequence)

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            assert call_count < max_calls
            result = bytes([byte_sequence[call_count]])
            call_count += 1
            return result

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
        final = dif.create_next_dife(TEST_FINAL_DIFE)
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
        final = current.create_next_dife(TEST_FINAL_DIFE)
        assert isinstance(final, FinalDIFE)
        assert final.chain_position == TEST_DIFE_MAXIMUM_CHAIN_LENGTH + 1

    def test_incorrect_code_raises(self) -> None:
        """Test that FinalDIFE with non-zero code raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        # Manually try to create FinalDIFE with wrong code
        # Factory won't let us, so test the validation in __init__
        # We need to bypass factory for this test
        final = object.__new__(FinalDIFE)
        with pytest.raises(ValueError, match="must match final DIFE code"):
            FinalDIFE.__init__(final, CommunicationDirection.SLAVE_TO_MASTER, TEST_DIFE_STORAGE_1, dif)

    def test_final_dife_after_position_11_raises(self) -> None:
        """Test that FinalDIFE after position 11 raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        current = dif

        # Create 10 regular DIFEs (positions 1-10)
        for _ in range(TEST_DIFE_MAXIMUM_CHAIN_LENGTH):
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


# =============================================================================
# Error Scenario Tests
# =============================================================================


class TestErrorScenarios:
    """Tests for error scenarios and edge cases."""

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
