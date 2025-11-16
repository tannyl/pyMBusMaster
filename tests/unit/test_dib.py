"""Unit tests for DIB classes and helper functions."""

import pytest

from src.mbusmaster.protocol import CommunicationDirection
from src.mbusmaster.protocol.data import DataRules
from src.mbusmaster.protocol.dib import (
    DIB,
    DataDIB,
    GlobalReadoutDIB,
    IdleFillerDIB,
    ManufacturerDIB,
    ReadoutSelectionDIB,
    SpecialDIB,
)
from src.mbusmaster.protocol.dif import DIF
from src.mbusmaster.protocol.value import ValueFunction

# =============================================================================
# Test Constants - Duplicated from src for test isolation
# =============================================================================
# If these values change in production code, tests will fail and alert us

# DIF codes used in tests
TEST_DIF_32BIT_INST = 0x04  # 32-bit integer, instantaneous, no extension, no storage
TEST_DIF_32BIT_INST_EXT = 0x84  # 32-bit integer, instantaneous, with extension bit
TEST_DIF_32BIT_INST_STORAGE1 = 0x44  # 32-bit integer, storage bit 6 set, no extension
TEST_DIF_32BIT_INST_STORAGE1_EXT = 0xC4  # 32-bit integer, storage bit 6 set, with extension
TEST_DIF_32BIT_MAX = 0x14  # 32-bit integer, maximum function
TEST_DIF_32BIT_MAX_STORAGE1_EXT = 0xD4  # 32-bit integer, maximum, storage bit 6 set, with extension
TEST_DIF_32BIT_MIN = 0x24  # 32-bit integer, minimum function
TEST_DIF_32BIT_ERROR = 0x34  # 32-bit integer, error function
TEST_DIF_48BIT_INST = 0x06  # 48-bit integer, instantaneous, no extension
TEST_DIF_48BIT_INST_EXT = 0x86  # 48-bit integer, instantaneous, with extension
TEST_DIF_48BIT_INST_STORAGE1_EXT = 0xC6  # 48-bit integer, storage bit 6 set, with extension
TEST_DIF_READOUT_SEL = 0x08  # Readout selection (master to slave)
TEST_DIF_READOUT_SEL_EXT = 0x88  # Readout selection with extension bit

# Special DIF codes
TEST_SPECIAL_DIF_MANUFACTURER = 0x0F  # Manufacturer specific data
TEST_SPECIAL_DIF_MORE_RECORDS = 0x1F  # Manufacturer data + more records follow
TEST_SPECIAL_DIF_IDLE_FILLER = 0x2F  # Idle filler (padding)
TEST_SPECIAL_DIF_GLOBAL_READOUT = 0x7F  # Global readout request

# DIFE codes
TEST_DIFE_STORAGE_0_EXT = 0x80  # Storage bits=0, extension bit set (extension bit only)
TEST_DIFE_STORAGE_1 = 0x01  # Storage bits 0-3 = 0001, no extension
TEST_DIFE_STORAGE_1_EXT = 0x81  # Storage bits 0-3 = 0001, with extension
TEST_DIFE_STORAGE_15 = 0x0F  # Storage bits 0-3 = 1111 (15), no extension
TEST_DIFE_STORAGE_15_EXT = 0x8F  # Storage bits=15, extension bit set
TEST_DIFE_TARIFF_1 = 0x10  # Tariff bits 4-5 = 01 (value 1), no extension
TEST_DIFE_TARIFF_1_EXT = 0x90  # Tariff bits 4-5 = 01 (value 1), with extension
TEST_DIFE_TARIFF_3 = 0x30  # Tariff bits 4-5 = 11 (value 3)
TEST_DIFE_SUBUNIT_1 = 0x40  # Subunit bit 6 = 1
TEST_DIFE_COMBINED = 0x75  # Storage=5, tariff=3, subunit=1, no extension
TEST_FINAL_DIFE = 0x00  # Final DIFE marking register number

# Chain length limits
TEST_DIFE_MAXIMUM_CHAIN_LENGTH = 10
TEST_DIB_MAXIMUM_REGISTER_NUMBER = 125

# Expected bytes for to_bytes() tests
TEST_DIB_32BIT_INST_BYTES = bytes([TEST_DIF_32BIT_INST])
TEST_DIB_32BIT_WITH_DIFE_BYTES = bytes([TEST_DIF_32BIT_INST_EXT, TEST_DIFE_STORAGE_1])
TEST_DIB_32BIT_WITH_MULTIPLE_DIFES_BYTES = bytes(
    [TEST_DIF_32BIT_INST_EXT, TEST_DIFE_STORAGE_1_EXT, TEST_DIFE_STORAGE_1]
)
TEST_DIB_SPECIAL_MANUFACTURER_BYTES = bytes([TEST_SPECIAL_DIF_MANUFACTURER])


# =============================================================================
# DIB Base Class Tests
# =============================================================================


class TestDIB:
    """Tests for DIB base class validation."""

    def test_bidirectional_direction_raises(self) -> None:
        """Test that BIDIRECTIONAL direction raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        with pytest.raises(ValueError, match="cannot be BIDIRECTIONAL"):
            DIB(CommunicationDirection.BIDIRECTIONAL, dif)

    def test_direction_mismatch_raises(self) -> None:
        """Test that DIF/DIB direction mismatch raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        # Try to create DIB with different direction
        with pytest.raises(ValueError, match="direction does not match"):
            DIB(CommunicationDirection.MASTER_TO_SLAVE, dif)

    def test_chain_length_mismatch_raises(self) -> None:
        """Test that chain length mismatch raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife1 = dif.create_next_dife(TEST_DIFE_STORAGE_1_EXT)
        dife2 = dife1.create_next_dife(TEST_DIFE_STORAGE_1)

        # Create DIB with wrong chain - skip dife1
        with pytest.raises(ValueError, match="chain is broken"):
            DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife2)

    def test_stores_direction(self) -> None:
        """Test that DIB stores direction attribute."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert dib.direction == CommunicationDirection.SLAVE_TO_MASTER

    @pytest.mark.parametrize(
        ("dif_code", "dife_codes", "expected_bytes"),
        [
            # Simple DataDIB without DIFEs
            (
                TEST_DIF_32BIT_INST,
                [],
                TEST_DIB_32BIT_INST_BYTES,
            ),
            # DataDIB with single DIFE
            (
                TEST_DIF_32BIT_INST_EXT,
                [TEST_DIFE_STORAGE_1],
                TEST_DIB_32BIT_WITH_DIFE_BYTES,
            ),
            # DataDIB with multiple DIFEs
            (
                TEST_DIF_32BIT_INST_EXT,
                [TEST_DIFE_STORAGE_1_EXT, TEST_DIFE_STORAGE_1],
                TEST_DIB_32BIT_WITH_MULTIPLE_DIFES_BYTES,
            ),
            # SpecialDIB
            (
                TEST_SPECIAL_DIF_MANUFACTURER,
                [],
                TEST_DIB_SPECIAL_MANUFACTURER_BYTES,
            ),
        ],
        ids=["data_dib_no_dife", "data_dib_single_dife", "data_dib_multiple_difes", "special_dib"],
    )
    def test_to_bytes_serializes_complete_chain(
        self, dif_code: int, dife_codes: list[int], expected_bytes: bytes
    ) -> None:
        """Test that to_bytes() correctly serializes the complete DIF/DIFE chain."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)

        # Build DIFE chain and collect in list
        difes = []
        current_field = dif
        for dife_code in dife_codes:
            current_field = current_field.create_next_dife(dife_code)
            difes.append(current_field)

        # Create DIB from complete chain
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, *difes)

        result = dib.to_bytes()
        assert result == expected_bytes
        assert len(result) == len(expected_bytes)


# =============================================================================
# DataDIB Class Tests
# =============================================================================


class TestDataDIB:
    """Tests for DataDIB class."""

    def test_factory_creates_data_dib(self) -> None:
        """Test that DIB factory creates DataDIB for data DIF."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert isinstance(dib, DataDIB)

    @pytest.mark.parametrize(
        ("dif_code", "expected_data_support"),
        [
            (TEST_DIF_32BIT_INST, DataRules.Supports.BCDFK_4),
            (TEST_DIF_48BIT_INST, DataRules.Supports.BCDI_6),
        ],
        ids=["32bit_integer", "48bit_integer"],
    )
    def test_data_support_from_dif(self, dif_code: int, expected_data_support: DataRules.Supports) -> None:
        """Test that data_support is correctly set from DIF."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert isinstance(dib, DataDIB)
        assert dib.data_support is expected_data_support

    @pytest.mark.parametrize(
        ("dif_code", "expected_function"),
        [
            (TEST_DIF_32BIT_INST, ValueFunction.INSTANTANEOUS),
            (TEST_DIF_32BIT_MAX, ValueFunction.MAXIMUM),
            (TEST_DIF_32BIT_MIN, ValueFunction.MINIMUM),
            (TEST_DIF_32BIT_ERROR, ValueFunction.ERROR),
        ],
        ids=["instantaneous", "maximum", "minimum", "error"],
    )
    def test_value_function_from_dif(self, dif_code: int, expected_function: ValueFunction) -> None:
        """Test that value_function is correctly set from DIF."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert isinstance(dib, DataDIB)
        assert dib.value_function == expected_function

    @pytest.mark.parametrize(
        ("dif_code", "expected_storage"),
        [
            (TEST_DIF_32BIT_INST, 0),  # Storage bit 6 = 0
            (TEST_DIF_32BIT_INST_STORAGE1, 1),  # Storage bit 6 = 1
        ],
        ids=["storage_0", "storage_1"],
    )
    def test_storage_number_from_dif_only(self, dif_code: int, expected_storage: int) -> None:
        """Test storage number from DIF alone (no DIFEs)."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert isinstance(dib, DataDIB)
        assert dib.storage_number == expected_storage

    def test_storage_number_accumulation_with_dife(self) -> None:
        """Test storage number accumulation from DIF + DIFE."""
        # DIF contributes 0, DIFE contributes 1 << 1 = 2
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife = dif.create_next_dife(TEST_DIFE_STORAGE_1)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife)
        assert isinstance(dib, DataDIB)
        # DIF bit 6 = 0, DIFE bits 0-3 = 1, shifted by 1 → 0 + 2 = 2
        assert dib.storage_number == 2

    def test_storage_number_accumulation_with_multiple_difes(self) -> None:
        """Test storage number accumulation from DIF + multiple DIFEs."""
        # DIF: storage bit = 1 (contributes 1)
        # DIFE1: storage = 15 (contributes 15 << 1 = 30)
        # DIFE2: storage = 1 (contributes 1 << 5 = 32)
        # Total: 1 + 30 + 32 = 63
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_STORAGE1_EXT)
        dife1 = dif.create_next_dife(TEST_DIFE_STORAGE_15_EXT)
        dife2 = dife1.create_next_dife(TEST_DIFE_STORAGE_1)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife1, dife2)
        assert isinstance(dib, DataDIB)
        assert dib.storage_number == 63

    def test_tariff_accumulation(self) -> None:
        """Test tariff accumulation from DIFEs."""
        # DIFE1: tariff = 1 (bits 4-5 = 01), shifted by 0 → 1
        # DIFE2: tariff = 3 (bits 4-5 = 11), shifted by 2 → 12
        # Total: 1 + 12 = 13
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife1 = dif.create_next_dife(TEST_DIFE_TARIFF_1_EXT)
        dife2 = dife1.create_next_dife(TEST_DIFE_TARIFF_3)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife1, dife2)
        assert isinstance(dib, DataDIB)
        assert dib.tariff == 13

    def test_subunit_accumulation(self) -> None:
        """Test subunit accumulation from DIFEs."""
        # DIFE1: subunit = 0 (bit 6 = 0), shifted by 0 → 0
        # DIFE2: subunit = 1 (bit 6 = 1), shifted by 1 → 2
        # Total: 0 + 2 = 2
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife1 = dif.create_next_dife(TEST_DIFE_STORAGE_1_EXT)  # subunit bit 6 = 0
        dife2 = dife1.create_next_dife(TEST_DIFE_SUBUNIT_1)  # subunit bit 6 = 1
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife1, dife2)
        assert isinstance(dib, DataDIB)
        assert dib.subunit == 2

    def test_combined_accumulators(self) -> None:
        """Test all accumulators working together simultaneously."""
        # DIF: value_function=MAXIMUM, storage bit 6 = 1 (contributes 1)
        # DIFE: TEST_DIFE_COMBINED = storage=5, tariff=3, subunit=1
        # Expected: storage=1+(5<<1)=11, tariff=3, subunit=1, value_function=MAXIMUM
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_MAX_STORAGE1_EXT)
        dife = dif.create_next_dife(TEST_DIFE_COMBINED)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife)
        assert isinstance(dib, DataDIB)
        assert dib.value_function == ValueFunction.MAXIMUM
        assert dib.storage_number == 11  # 1 + (5 << 1)
        assert dib.tariff == 3
        assert dib.subunit == 1

    @pytest.mark.parametrize(
        ("dife_code", "expected_register_number"),
        [
            (TEST_FINAL_DIFE, True),
            (TEST_DIFE_STORAGE_1, False),
        ],
        ids=["final_dife", "normal_dife"],
    )
    def test_register_number_flag(self, dife_code: int, expected_register_number: bool) -> None:
        """Test that register_number flag is correctly set based on DIFE type."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife = dif.create_next_dife(dife_code)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife)
        assert isinstance(dib, DataDIB)
        assert dib.register_number is expected_register_number

    def test_register_number_exceeds_maximum_raises(self) -> None:
        """Test that register number exceeding maximum raises ValueError."""
        # Create a chain that produces storage > 125
        # This requires many DIFEs with high storage values
        with pytest.raises(ValueError, match="exceeds maximum allowed value"):
            # Create DIF with storage=1, then 5 DIFEs with storage=15 each
            dif2 = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_48BIT_INST_STORAGE1_EXT)  # storage=1
            d1 = dif2.create_next_dife(TEST_DIFE_STORAGE_15_EXT)  # storage=15, extended
            d2 = d1.create_next_dife(TEST_DIFE_STORAGE_15_EXT)
            d3 = d2.create_next_dife(TEST_DIFE_STORAGE_15_EXT)
            d4 = d3.create_next_dife(TEST_DIFE_STORAGE_15_EXT)  # This would give us >125 after shifts
            d5 = d4.create_next_dife(TEST_FINAL_DIFE)
            # Storage calculation: 1 + (15<<1) + (15<<5) + (15<<9) + (15<<13) = 1+30+480+7680+122880 = 131071 > 125
            DIB(CommunicationDirection.SLAVE_TO_MASTER, dif2, d1, d2, d3, d4, d5)

    def test_chain_is_incomplete_raises(self) -> None:
        """Test that incomplete DIF/DIFE chain raises ValueError."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        dife = dif.create_next_dife(TEST_DIFE_STORAGE_1_EXT)  # Extension bit set, no next_field

        with pytest.raises(ValueError, match="chain is incomplete"):
            DIB(CommunicationDirection.SLAVE_TO_MASTER, dif, dife)

    def test_at_chain_limit_is_valid(self) -> None:
        """Test that chain at exactly the limit (10 DIFEs) is valid."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)
        chain = [dif]
        current = dif

        # Create first 9 DIFEs with extension bit
        for _ in range(9):
            current = current.create_next_dife(TEST_DIFE_STORAGE_1_EXT)
            chain.append(current)

        # Create last DIFE without extension bit
        current = current.create_next_dife(TEST_DIFE_STORAGE_1)
        chain.append(current)

        # Should succeed
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, *chain)  # type: ignore
        assert isinstance(dib, DataDIB)

    def test_final_dife_at_position_11_is_valid(self) -> None:
        """Test that FinalDIFE at position 11 (after 10 regular DIFEs) is valid."""
        # Use storage value of 0 for all DIFEs to keep storage number under 125
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_DIF_32BIT_INST_EXT)  # storage=0
        chain = [dif]
        current = dif

        # Create 10 regular DIFEs with storage=0 (extension bit only)
        for _ in range(10):
            current = current.create_next_dife(TEST_DIFE_STORAGE_0_EXT)  # Extension bit set, storage=0
            chain.append(current)

        # Add FinalDIFE as 11th
        final = current.create_next_dife(TEST_FINAL_DIFE)
        chain.append(final)

        # Should succeed - storage number is 0 which is valid
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, *chain)  # type: ignore
        assert isinstance(dib, DataDIB)
        assert dib.register_number is True
        assert dib.storage_number == 0  # All storage bits were 0


# =============================================================================
# ReadoutSelectionDIB Class Tests
# =============================================================================


class TestReadoutSelectionDIB:
    """Tests for ReadoutSelectionDIB class."""

    def test_factory_creates_correct_type(self) -> None:
        """Test that factory creates ReadoutSelectionDIB for readout selection DIF."""
        dif = DIF(CommunicationDirection.MASTER_TO_SLAVE, TEST_DIF_READOUT_SEL)
        dib = DIB(CommunicationDirection.MASTER_TO_SLAVE, dif)
        assert isinstance(dib, ReadoutSelectionDIB)

    def test_works_with_difes(self) -> None:
        """Test that ReadoutSelectionDIB works with DIFEs."""
        dif = DIF(CommunicationDirection.MASTER_TO_SLAVE, TEST_DIF_READOUT_SEL_EXT)
        dife = dif.create_next_dife(TEST_DIFE_STORAGE_1)
        dib = DIB(CommunicationDirection.MASTER_TO_SLAVE, dif, dife)
        assert isinstance(dib, ReadoutSelectionDIB)
        # Verify it's a proper DataDIB with accumulated values
        assert dib.storage_number == 2  # DIF:0 + DIFE:(1<<1)


# =============================================================================
# SpecialDIB Class Tests
# =============================================================================


class TestSpecialDIB:
    """Tests for SpecialDIB base class validation."""

    @pytest.mark.parametrize(
        ("dif_code", "direction"),
        [
            (TEST_SPECIAL_DIF_MANUFACTURER, CommunicationDirection.SLAVE_TO_MASTER),
            (TEST_SPECIAL_DIF_MORE_RECORDS, CommunicationDirection.SLAVE_TO_MASTER),
            (TEST_SPECIAL_DIF_IDLE_FILLER, CommunicationDirection.SLAVE_TO_MASTER),
            (TEST_SPECIAL_DIF_GLOBAL_READOUT, CommunicationDirection.MASTER_TO_SLAVE),
        ],
        ids=["manufacturer", "more_records", "idle_filler", "global_readout"],
    )
    def test_factory_creates_special_dib(self, dif_code: int, direction: CommunicationDirection) -> None:
        """Test that factory creates SpecialDIB for special DIF codes."""
        dif = DIF(direction, dif_code)
        dib = DIB(direction, dif)
        assert isinstance(dib, SpecialDIB)


# =============================================================================
# ManufacturerDIB Class Tests
# =============================================================================


class TestManufacturerDIB:
    """Tests for ManufacturerDIB class."""

    @pytest.mark.parametrize(
        ("dif_code", "expected_more_records"),
        [
            (TEST_SPECIAL_DIF_MANUFACTURER, False),
            (TEST_SPECIAL_DIF_MORE_RECORDS, True),
        ],
        ids=["manufacturer_only", "with_more_records"],
    )
    def test_more_records_follow(self, dif_code: int, expected_more_records: bool) -> None:
        """Test that more_records_follow is correctly set based on DIF code."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert dib.more_records_follow is expected_more_records  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "dif_code",
        [
            TEST_SPECIAL_DIF_MANUFACTURER,
            TEST_SPECIAL_DIF_MORE_RECORDS,
        ],
        ids=["manufacturer", "more_records"],
    )
    def test_factory_creates_correct_type(self, dif_code: int) -> None:
        """Test that factory creates ManufacturerDIB for manufacturer codes."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, dif_code)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert isinstance(dib, ManufacturerDIB)


# =============================================================================
# IdleFillerDIB Class Tests
# =============================================================================


class TestIdleFillerDIB:
    """Tests for IdleFillerDIB class."""

    def test_factory_creates_correct_type(self) -> None:
        """Test that factory creates IdleFillerDIB for idle filler code."""
        dif = DIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_SPECIAL_DIF_IDLE_FILLER)
        dib = DIB(CommunicationDirection.SLAVE_TO_MASTER, dif)
        assert isinstance(dib, IdleFillerDIB)


# =============================================================================
# GlobalReadoutDIB Class Tests
# =============================================================================


class TestGlobalReadoutDIB:
    """Tests for GlobalReadoutDIB class."""

    def test_factory_creates_correct_type(self) -> None:
        """Test that factory creates GlobalReadoutDIB for global readout code."""
        dif = DIF(CommunicationDirection.MASTER_TO_SLAVE, TEST_SPECIAL_DIF_GLOBAL_READOUT)
        dib = DIB(CommunicationDirection.MASTER_TO_SLAVE, dif)
        assert isinstance(dib, GlobalReadoutDIB)


# =============================================================================
# Async Byte Parsing Tests
# =============================================================================


class TestDIBFromBytesAsync:
    """Tests for DIB.from_bytes_async() method (integration-level)."""

    @pytest.mark.parametrize(
        ("byte_sequence", "expected_storage", "expected_function", "expected_register_number"),
        [
            # No DIFEs
            (
                [TEST_DIF_32BIT_INST],
                0,
                ValueFunction.INSTANTANEOUS,
                False,
            ),
            # Single DIFE
            (
                [TEST_DIF_32BIT_INST_EXT, TEST_DIFE_STORAGE_1],
                2,
                ValueFunction.INSTANTANEOUS,
                False,
            ),
            # Multiple DIFEs - storage: 1 + (15<<1) + (1<<5) = 1 + 30 + 32 = 63
            (
                [TEST_DIF_32BIT_INST_STORAGE1_EXT, TEST_DIFE_STORAGE_15_EXT, TEST_DIFE_STORAGE_1],
                63,
                ValueFunction.INSTANTANEOUS,
                False,
            ),
            # FinalDIFE
            (
                [TEST_DIF_32BIT_INST_EXT, TEST_FINAL_DIFE],
                0,
                ValueFunction.INSTANTANEOUS,
                True,
            ),
        ],
        ids=["no_difes", "single_dife", "multiple_difes", "with_final_dife"],
    )
    async def test_parse_data_dib(
        self,
        byte_sequence: list[int],
        expected_storage: int,
        expected_function: ValueFunction,
        expected_register_number: bool,
    ) -> None:
        """Test parsing DataDIB with various DIFE configurations."""
        call_count = 0
        max_calls = len(byte_sequence)

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            assert call_count < max_calls
            result = bytes([byte_sequence[call_count]])
            call_count += 1
            return result

        dib = await DIB.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        assert isinstance(dib, DataDIB)
        assert dib.storage_number == expected_storage
        assert dib.value_function == expected_function
        assert dib.register_number is expected_register_number

    async def test_parse_readout_selection_dib(self) -> None:
        """Test parsing ReadoutSelectionDIB."""

        async def get_next_bytes(n: int) -> bytes:
            assert n == 1
            return bytes([TEST_DIF_READOUT_SEL])

        dib = await DIB.from_bytes_async(CommunicationDirection.MASTER_TO_SLAVE, get_next_bytes)

        assert isinstance(dib, ReadoutSelectionDIB)

    @pytest.mark.parametrize(
        ("dif_code", "expected_type", "direction", "expected_more_records"),
        [
            (TEST_SPECIAL_DIF_MANUFACTURER, ManufacturerDIB, CommunicationDirection.SLAVE_TO_MASTER, False),
            (TEST_SPECIAL_DIF_MORE_RECORDS, ManufacturerDIB, CommunicationDirection.SLAVE_TO_MASTER, True),
            (TEST_SPECIAL_DIF_IDLE_FILLER, IdleFillerDIB, CommunicationDirection.SLAVE_TO_MASTER, None),
            (TEST_SPECIAL_DIF_GLOBAL_READOUT, GlobalReadoutDIB, CommunicationDirection.MASTER_TO_SLAVE, None),
        ],
        ids=["manufacturer", "more_records", "idle_filler", "global_readout"],
    )
    async def test_parse_special_dib(
        self,
        dif_code: int,
        expected_type: type[SpecialDIB],
        direction: CommunicationDirection,
        expected_more_records: bool | None,
    ) -> None:
        """Test parsing SpecialDIB subclasses."""
        byte_sequence = [dif_code]
        call_count = 0
        max_calls = len(byte_sequence)

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            assert call_count < max_calls
            result = bytes([byte_sequence[call_count]])
            call_count += 1
            return result

        dib = await DIB.from_bytes_async(direction, get_next_bytes)

        assert isinstance(dib, expected_type)
        if hasattr(dib, "more_records_follow"):
            assert isinstance(dib, ManufacturerDIB)
            assert dib.more_records_follow is expected_more_records

    async def test_insufficient_bytes_raises(self) -> None:
        """Test that insufficient bytes raises ValueError from DIF parsing."""
        byte_sequence: list[list[int]] = [[]]  # Empty bytes
        call_count = 0
        max_calls = len(byte_sequence)

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert n == 1
            assert call_count < max_calls
            result = bytes(byte_sequence[call_count])
            call_count += 1
            return result

        # Should raise from DIF.from_bytes_async()
        with pytest.raises(ValueError, match="Expected exactly one byte for DIF"):
            await DIB.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)
