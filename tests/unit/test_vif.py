"""Unit tests for VIF/VIFE classes and helper functions."""

from collections import deque

import pytest

from src.mbusmaster.protocol import CommunicationDirection
from src.mbusmaster.protocol.data import DataRules
from src.mbusmaster.protocol.value import (
    ValueDescription,
    ValueDescriptionTransformer,
    ValueTransformer,
    ValueUnit,
    ValueUnitTransformer,
)
from src.mbusmaster.protocol.vif import (
    VIF,
    VIFE,
    ActionVIFE,
    CombinableVIFE,
    ErrorVIFE,
    ExtensionCombinableVIFE,
    ExtensionVIF,
    ExtensionVIFE,
    ManufacturerVIF,
    ManufacturerVIFE,
    PlainTextVIF,
    ReadoutAnyVIF,
    TrueVIF,
    TrueVIFE,
    _CombinableExtensionFieldTable,
    _CombinableOrthogonalFieldTable,
    _decode_ascii_unit,
    _encode_ascii_unit,
    _find_field_descriptor,
    _FirstExtensionFieldTable,
    _PrimaryFieldTable,
    _SecondExtensionFieldTable,
    _SecondExtensionSecondLevelFieldTable,
)

# =============================================================================
# Test Constants - Duplicated from src for test isolation
# =============================================================================
# If these values change in production code, tests will fail and alert us

# Maximum VIFE chain length
TEST_VIFE_MAXIMUM_CHAIN_LENGTH = 10  # Must match VIFE_MAXIMUM_CHAIN_LENGTH in vif.py

# From _PrimaryFieldTable
TEST_VIF_PRIMARY_ENERGY_WH = 0b00000000
TEST_VIF_PRIMARY_ENERGY_WH_EXT = 0b10000000
TEST_VIF_PRIMARY_POWER_W = 0b00101000
TEST_VIF_PRIMARY_VOLUME_FLOW_MIN = 0b01000000
TEST_VIF_PRIMARY_DATE_TIME = 0b01101101
TEST_VIF_PRIMARY_HCA_UNITS = 0b01101110
TEST_VIF_PRIMARY_EXTENSION_FB_EXT = 0b11111011
TEST_VIF_PRIMARY_EXTENSION_FD_EXT = 0b11111101
TEST_VIF_PRIMARY_PLAIN_TEXT = 0b01111100
TEST_VIF_PRIMARY_PLAIN_TEXT_EXT = 0b11111100
TEST_VIF_PRIMARY_MANUFACTURER = 0b01111111
TEST_VIF_PRIMARY_MANUFACTURER_EXT = 0b11111111
TEST_VIF_PRIMARY_READOUT_ANY = 0b01111110
TEST_VIF_PRIMARY_READOUT_ANY_EXT = 0b11111110

# From _FirstExtensionFieldTable
TEST_VIFE_FIRST_EXTENSION_ENERGY_MWH = 0b00000000
TEST_VIFE_FIRST_EXTENSION_VOLUME_M3 = 0b00010000
TEST_VIFE_FIRST_EXTENSION_REACTIVE_POWER_KVAR = 0b00010100

# From _SecondExtensionFieldTable
TEST_VIFE_SECOND_EXTENSION_CREDIT = 0b00000000
TEST_VIFE_SECOND_EXTENSION_SECOND_LEVEL_EXT = 0b11111101

# From _SecondExtensionSecondLevelFieldTable
TEST_VIFE_SECOND_EXT_SECOND_LEVEL_APP = 0b00000000
TEST_VIFE_SECOND_EXT_SECOND_LEVEL_APP_EXT = 0b10000000

# From _CombinableOrthogonalFieldTable
TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_WRITE = 0b00000000
TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_ADD = 0b00000001
TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_SUBTRACT = 0b00000010
TEST_VIFE_COMBINABLE_ORTHOGONAL_ERROR_NONE = 0b00000000
TEST_VIFE_COMBINABLE_ORTHOGONAL_ERROR_TOO_MANY_DIFES = 0b00000001
TEST_VIFE_COMBINABLE_ORTHOGONAL_ERROR_TOO_MANY_VIFES = 0b00001011
TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000 = 0b01111101
TEST_VIFE_COMBINABLE_ORTHOGONAL_INCREMENT_INPUT_PULSE = 0b00101000
TEST_VIFE_COMBINABLE_ORTHOGONAL_ADD_CORR = 0b01111000
TEST_VIFE_COMBINABLE_ORTHOGONAL_EXT_COMBINABLE_EXT = 0b11111100
TEST_VIFE_COMBINABLE_ORTHOGONAL_MANUFACTURER = 0b01111111

# From _CombinableExtensionFieldTable
TEST_VIFE_COMBINABLE_EXTENSION_PHASE_L1 = 0b00000001

# Manufacturer-specific VIFE
TEST_VIFE_MANUFACTURER_SPECIFIC = 0b00000000
TEST_VIFE_MANUFACTURER_SPECIFIC_EXT = 0b10000000


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestFindFieldDescriptor:
    """Tests for _find_field_descriptor helper function."""

    @pytest.mark.parametrize(
        ("field_code", "field_table", "direction"),
        [
            (
                TEST_VIF_PRIMARY_ENERGY_WH,
                _PrimaryFieldTable,
                CommunicationDirection.SLAVE_TO_MASTER,
            ),
            (
                TEST_VIFE_FIRST_EXTENSION_ENERGY_MWH,
                _FirstExtensionFieldTable,
                CommunicationDirection.SLAVE_TO_MASTER,
            ),
            (
                TEST_VIFE_SECOND_EXTENSION_CREDIT,
                _SecondExtensionFieldTable,
                CommunicationDirection.SLAVE_TO_MASTER,
            ),
            (
                TEST_VIFE_SECOND_EXT_SECOND_LEVEL_APP,
                _SecondExtensionSecondLevelFieldTable,
                CommunicationDirection.SLAVE_TO_MASTER,
            ),
            (
                TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_WRITE,
                _CombinableOrthogonalFieldTable,
                CommunicationDirection.MASTER_TO_SLAVE,
            ),
            (
                TEST_VIFE_COMBINABLE_EXTENSION_PHASE_L1,
                _CombinableExtensionFieldTable,
                CommunicationDirection.SLAVE_TO_MASTER,
            ),
        ],
        ids=[
            "primary",
            "first_extension",
            "second_extension",
            "second_extension_second_level",
            "combinable_orthogonal",
            "combinable_extension",
        ],
    )
    def test_find_valid_descriptor(
        self,
        field_code: int,
        field_table: tuple,
        direction: CommunicationDirection,
    ) -> None:
        """Test finding a valid descriptor from all FieldTables."""
        descriptor = _find_field_descriptor(direction, field_code, field_table)
        assert descriptor is not None
        assert (descriptor.code & descriptor.mask) == (field_code & descriptor.mask)

    def test_extension_bit_ignored_in_lookup(self) -> None:
        """Test that extension bit doesn't affect descriptor lookup."""
        # Get descriptor for code without extension bit
        desc_no_ext = _find_field_descriptor(
            CommunicationDirection.SLAVE_TO_MASTER,
            TEST_VIF_PRIMARY_ENERGY_WH,
            _PrimaryFieldTable,
        )
        # Get descriptor for same code with extension bit
        desc_with_ext = _find_field_descriptor(
            CommunicationDirection.SLAVE_TO_MASTER,
            TEST_VIF_PRIMARY_ENERGY_WH_EXT,
            _PrimaryFieldTable,
        )
        # Should be the same descriptor (extension bit masked out)
        assert desc_no_ext is desc_with_ext

    def test_lru_cache_works(self) -> None:
        """Test that LRU cache returns cached results on repeated calls."""
        # Clear cache to start fresh
        _find_field_descriptor.cache_clear()

        # First call - cache miss
        _find_field_descriptor(
            CommunicationDirection.SLAVE_TO_MASTER,
            TEST_VIF_PRIMARY_ENERGY_WH,
            _PrimaryFieldTable,
        )
        cache_info = _find_field_descriptor.cache_info()
        assert cache_info.hits == 0
        assert cache_info.misses == 1

        # Second call with same params - cache hit
        _find_field_descriptor(
            CommunicationDirection.SLAVE_TO_MASTER,
            TEST_VIF_PRIMARY_ENERGY_WH,
            _PrimaryFieldTable,
        )
        cache_info = _find_field_descriptor.cache_info()
        assert cache_info.hits == 1
        assert cache_info.misses == 1

    def test_invalid_code_raises_error(self) -> None:
        """Test that invalid VIF code raises ValueError."""
        # 0b11101111 (0xEF) is reserved and not implemented in PrimaryFieldTable
        invalid_code = 0b11101111
        with pytest.raises(
            ValueError,
            match=r"VIF/VIFE code 0xEF for direction SLAVE_TO_MASTER not found in VIF/VIFE tables",
        ):
            _find_field_descriptor(
                CommunicationDirection.SLAVE_TO_MASTER,
                invalid_code,
                _PrimaryFieldTable,
            )


class TestDecodeAsciiUnit:
    """Tests for _decode_ascii_unit helper function."""

    @pytest.mark.parametrize(
        ("ascii_bytes", "expected_unit"),
        [
            (bytes([0x64, 0x63, 0x62, 0x61]), "abcd"),
            (bytes([0x44, 0x43, 0x42, 0x41]), "ABCD"),
            (bytes([0x33, 0x32, 0x31]), "123"),
            (bytes([0x24, 0x23, 0x40, 0x21]), "!@#$"),
        ],
        ids=["lowercase", "uppercase", "numbers", "special_chars"],
    )
    def test_decode_valid_ascii_unit(
        self,
        ascii_bytes: bytes,
        expected_unit: str,
    ) -> None:
        """Test decoding valid ASCII unit strings."""
        result = _decode_ascii_unit(ascii_bytes)
        assert result == expected_unit

    @pytest.mark.parametrize(
        ("ascii_bytes", "expected_error"),
        [
            (
                bytes([0x41, 0x42, 0x80]),  # Non-ASCII byte first (reversed order)
                r"'ascii' codec can't decode byte 0x80 in position 0: ordinal not in range\(128\)",
            ),
            (
                bytes([0x41, 0x80, 0x42]),  # Non-ASCII byte in middle
                r"'ascii' codec can't decode byte 0x80 in position 1: ordinal not in range\(128\)",
            ),
            (
                bytes([0x80, 0x41, 0x42]),  # Non-ASCII byte last (reversed order)
                r"'ascii' codec can't decode byte 0x80 in position 2: ordinal not in range\(128\)",
            ),
        ],
        ids=[
            "non_ascii_byte_first",
            "non_ascii_byte_middle",
            "non_ascii_byte_last",
        ],
    )
    def test_decode_invalid_ascii_unit_raises_error(self, ascii_bytes: bytes, expected_error: str) -> None:
        """Test that invalid ASCII bytes raise UnicodeDecodeError."""

        with pytest.raises(UnicodeDecodeError, match=expected_error):
            _decode_ascii_unit(ascii_bytes)


class TestEncodeAsciiUnit:
    """Tests for _encode_ascii_unit helper function."""

    @pytest.mark.parametrize(
        ("text", "expected_tuple"),
        [
            ("abcd", (0x64, 0x63, 0x62, 0x61)),
            ("ABCD", (0x44, 0x43, 0x42, 0x41)),
            ("123", (0x33, 0x32, 0x31)),
            ("!@#$", (0x24, 0x23, 0x40, 0x21)),
        ],
        ids=["lowercase", "uppercase", "numbers", "special_chars"],
    )
    def test_encode_valid_ascii_unit(self, text: str, expected_tuple: tuple[int, ...]) -> None:
        """Test encoding valid ASCII unit strings."""
        result = _encode_ascii_unit(text)
        assert result == expected_tuple

    @pytest.mark.parametrize(
        ("text", "expected_error"),
        [
            ("æøå", r"'ascii' codec can't encode character"),
            ("m³", r"'ascii' codec can't encode character"),
            ("°C", r"'ascii' codec can't encode character"),
        ],
        ids=["danish_chars", "superscript", "degree_symbol"],
    )
    def test_encode_invalid_ascii_unit_raises_error(self, text: str, expected_error: str) -> None:
        """Test that non-ASCII characters raise UnicodeEncodeError."""
        with pytest.raises(UnicodeEncodeError, match=expected_error):
            _encode_ascii_unit(text)

    def test_encode_decode_roundtrip(self) -> None:
        """Test that encoding then decoding returns the original string."""
        original = "kWh"
        encoded = _encode_ascii_unit(original)
        decoded = _decode_ascii_unit(bytes(encoded))
        assert decoded == original


# =============================================================================
# VIF Class Tests
# =============================================================================


class TestVIF:
    """Tests for VIF class and its subclasses."""

    @pytest.mark.parametrize(
        ("field_code", "direction", "expected_last_field", "expected_next_table"),
        [
            (
                TEST_VIF_PRIMARY_ENERGY_WH_EXT,
                CommunicationDirection.SLAVE_TO_MASTER,
                False,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIF_PRIMARY_EXTENSION_FB_EXT,
                CommunicationDirection.SLAVE_TO_MASTER,
                False,
                _FirstExtensionFieldTable,
            ),
            (
                TEST_VIF_PRIMARY_MANUFACTURER,
                CommunicationDirection.SLAVE_TO_MASTER,
                True,
                None,
            ),
        ],
        ids=["true_vif", "extension_vif", "manufacturer_vif"],
    )
    def test_initialization(
        self,
        field_code: int,
        direction: CommunicationDirection,
        expected_last_field: bool,
        expected_next_table: tuple | None,
    ) -> None:
        """Test that VIF is initialized correctly with basic attributes."""
        vif = VIF(direction, field_code)

        assert isinstance(vif, VIF)
        assert vif.direction == direction
        assert vif._field_code == field_code
        assert vif._chain_position == 0
        assert vif.prev_field is None
        assert vif.next_field is None
        assert vif.last_field == expected_last_field
        assert vif._next_table is expected_next_table

    @pytest.mark.parametrize(
        ("field_code", "direction", "expected_subclass"),
        [
            (TEST_VIF_PRIMARY_ENERGY_WH, CommunicationDirection.SLAVE_TO_MASTER, TrueVIF),
            (TEST_VIF_PRIMARY_EXTENSION_FB_EXT, CommunicationDirection.SLAVE_TO_MASTER, ExtensionVIF),
            (TEST_VIF_PRIMARY_PLAIN_TEXT, CommunicationDirection.SLAVE_TO_MASTER, PlainTextVIF),
            (TEST_VIF_PRIMARY_MANUFACTURER, CommunicationDirection.SLAVE_TO_MASTER, ManufacturerVIF),
            (TEST_VIF_PRIMARY_READOUT_ANY, CommunicationDirection.MASTER_TO_SLAVE, ReadoutAnyVIF),
        ],
        ids=["true_vif", "extension_vif", "plain_text_vif", "manufacturer_vif", "readout_any_vif"],
    )
    def test_factory_returns_correct_subclass(
        self,
        field_code: int,
        direction: CommunicationDirection,
        expected_subclass: type[VIF],
    ) -> None:
        """Test that VIF factory pattern returns correct subclass."""
        vif = VIF(direction, field_code)

        assert isinstance(vif, expected_subclass)
        assert vif.direction == direction
        assert vif._field_code == field_code

    @pytest.mark.parametrize(
        ("field_code", "expected_last_field"),
        [
            (TEST_VIF_PRIMARY_ENERGY_WH, True),  # No extension bit
            (TEST_VIF_PRIMARY_ENERGY_WH_EXT, False),  # With extension bit
        ],
        ids=["no_extension_bit", "with_extension_bit"],
    )
    def test_last_field_set_correctly(
        self,
        field_code: int,
        expected_last_field: bool,
    ) -> None:
        """Test that last_field is set correctly based on extension bit."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, field_code)

        assert vif.last_field == expected_last_field

    @pytest.mark.parametrize(
        ("field_code", "expected_result"),
        [
            (0b00000000, True),  # No extension bit
            (0b10000000, False),  # With extension bit
            (0b01111111, True),  # Another code without extension bit
            (0b11111111, False),  # Another code with extension bit
        ],
        ids=["0x00_no_ext", "0x80_with_ext", "0x7F_no_ext", "0xFF_with_ext"],
    )
    def test_is_last_field_direct(self, field_code: int, expected_result: bool) -> None:
        """Test _is_last_field method directly by bypassing __new__."""
        # Bypass factory pattern to test _is_last_field directly
        vif = object.__new__(VIF)
        vif._field_code = field_code

        assert vif._is_last_field() is expected_result

    def test_bidirectional_direction_raises_error(self) -> None:
        """Test that BIDIRECTIONAL direction raises ValueError."""
        with pytest.raises(ValueError, match=r"VIF/VIFE communication direction cannot be BIDIRECTIONAL"):
            VIF(CommunicationDirection.BIDIRECTIONAL, TEST_VIF_PRIMARY_EXTENSION_FB_EXT)

    def test_create_next_vife(self) -> None:
        """Test that create_next_vife returns correct VIFE instance."""
        # Use ExtensionVIF (0xFB) which points to _FirstExtensionFieldTable
        # Extension bit is automatically set (bit 7 = 1)
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_EXTENSION_FB_EXT)

        # Use VIFE code from _FirstExtensionFieldTable
        vife_code = TEST_VIFE_FIRST_EXTENSION_ENERGY_MWH
        vife = vif.create_next_vife(vife_code)

        assert isinstance(vife, VIFE)

    @pytest.mark.parametrize(
        "field_code",
        [
            TEST_VIF_PRIMARY_ENERGY_WH,
            TEST_VIF_PRIMARY_POWER_W,
            TEST_VIF_PRIMARY_EXTENSION_FB_EXT,
            TEST_VIF_PRIMARY_PLAIN_TEXT,
        ],
        ids=["energy_wh", "power_w", "extension_fb", "plain_text"],
    )
    def test_to_bytes(self, field_code: int) -> None:
        """Test that to_bytes returns correct bytes representation."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, field_code)

        result = vif.to_bytes()

        assert result == bytes([field_code])


# =============================================================================
# TrueVIF Class Tests
# =============================================================================


class TestTrueVIF:
    """Tests for TrueVIF class."""

    @pytest.mark.parametrize(
        (
            "field_code",
            "expected_description",
            "expected_unit",
            "expected_transformer",
            "expected_data_rules",
            "expected_next_table",
        ),
        [
            (
                TEST_VIF_PRIMARY_ENERGY_WH,
                ValueDescription.ENERGY,
                ValueUnit.WH,
                ValueTransformer.MULT_10_POW_NNN_MINUS_3,
                DataRules.Requires.DEFAULT_ABHLVAR,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIF_PRIMARY_VOLUME_FLOW_MIN,
                ValueDescription.VOLUME_FLOW,
                ValueUnit.M3_S,
                ValueTransformer.MULT_10_POW_NNN_MINUS_7_DIV_60,
                DataRules.Requires.DEFAULT_ABHLVAR,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIF_PRIMARY_DATE_TIME,
                ValueDescription.DATE_TIME,
                None,
                None,
                DataRules.Requires.TEMPORAL_FIJM,
                _CombinableOrthogonalFieldTable,
            ),
        ],
        ids=["energy_wh", "volume_flow_min", "date_time"],
    )
    def test_initialization(
        self,
        field_code: int,
        expected_description: ValueDescription | None,
        expected_unit: ValueUnit | None,
        expected_transformer: ValueTransformer | None,
        expected_data_rules: DataRules.Requires,
        expected_next_table: tuple | None,
    ) -> None:
        """Test that TrueVIF is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, field_code)

        assert isinstance(vif, TrueVIF)
        assert vif.value_description == expected_description
        assert vif.value_unit == expected_unit
        assert vif.value_transformer == expected_transformer
        assert vif.data_rules == expected_data_rules
        assert vif._next_table is expected_next_table


# =============================================================================
# ExtensionVIF Class Tests
# =============================================================================


class TestExtensionVIF:
    """Tests for ExtensionVIF class."""

    @pytest.mark.parametrize(
        ("field_code", "expected_next_table"),
        [
            (TEST_VIF_PRIMARY_EXTENSION_FB_EXT, _FirstExtensionFieldTable),
            (TEST_VIF_PRIMARY_EXTENSION_FD_EXT, _SecondExtensionFieldTable),
        ],
        ids=["extension_fb", "extension_fd"],
    )
    def test_initialization(
        self,
        field_code: int,
        expected_next_table: tuple,
    ) -> None:
        """Test that ExtensionVIF is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, field_code)

        assert isinstance(vif, ExtensionVIF)
        assert vif._next_table is expected_next_table


# =============================================================================
# PlainTextVIF Class Tests
# =============================================================================


class TestPlainTextVIF:
    """Tests for PlainTextVIF class."""

    def test_initialization(self) -> None:
        """Test that PlainTextVIF is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)

        assert isinstance(vif, TrueVIF)
        assert isinstance(vif, PlainTextVIF)
        assert vif.value_description is None
        assert vif.value_unit is None
        assert vif.value_transformer is None
        assert vif.data_rules is DataRules.Requires.DEFAULT_ABHLVAR
        assert vif._ascii_sequence is None
        assert vif._next_table is _CombinableOrthogonalFieldTable

    def test_set_ascii_unit_sets_value(self) -> None:
        """Test that set_ascii_unit correctly sets the unit value."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        vif.set_ascii_unit("kWh")

        assert vif.value_unit == "kWh"
        assert vif._ascii_sequence == (0x68, 0x57, 0x6B)  # "hWk" reversed

    def test_set_ascii_unit_already_set_raises_error(self) -> None:
        """Test that set_ascii_unit raises ValueError if unit already set."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)
        vif.set_ascii_unit("kWh")

        with pytest.raises(ValueError, match="ASCII unit already set"):
            vif.set_ascii_unit("m3")

    def test_set_ascii_unit_non_ascii_raises_error(self) -> None:
        """Test that set_ascii_unit raises UnicodeEncodeError for non-ASCII."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        with pytest.raises(UnicodeEncodeError):
            vif.set_ascii_unit("m³")

    @pytest.mark.parametrize(
        "text",
        [
            "",  # Empty string (length 0)
            "a" * 256,  # Too long (length 256)
        ],
        ids=["empty_string", "too_long"],
    )
    def test_set_ascii_unit_invalid_length_raises_error(self, text: str) -> None:
        """Test that set_ascii_unit raises ValueError for invalid length."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        with pytest.raises(ValueError, match="Length of encoded ASCII sequence invalid"):
            vif.set_ascii_unit(text)

    @pytest.mark.parametrize(
        ("set_unit", "expected"),
        [
            (False, False),
            (True, True),
        ],
        ids=["not_set", "set"],
    )
    def test_is_ascii_unit_set(self, set_unit: bool, expected: bool) -> None:
        """Test that is_ascii_unit_set returns correct value."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        if set_unit:
            vif.set_ascii_unit("kWh")

        assert vif.is_ascii_unit_set() is expected

    @pytest.mark.parametrize(
        ("text", "expected_bytes"),
        [
            ("A", bytes([1, 0x41])),
            ("kWh", bytes([3, 0x68, 0x57, 0x6B])),
            ("igal!", bytes([5, 0x21, 0x6C, 0x61, 0x67, 0x69])),
            ("a" * 255, bytes([255] + [0x61] * 255)),
        ],
        ids=["1_char", "3_chars", "5_chars", "255_chars"],
    )
    def test_ascii_unit_to_bytes(self, text: str, expected_bytes: bytes) -> None:
        """Test that ascii_unit_to_bytes returns correct bytes."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)
        vif.set_ascii_unit(text)

        assert vif.ascii_unit_to_bytes() == expected_bytes

    def test_ascii_unit_to_bytes_not_set_raises_error(self) -> None:
        """Test that ascii_unit_to_bytes raises ValueError if unit not set."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        with pytest.raises(ValueError, match="ASCII unit not set"):
            vif.ascii_unit_to_bytes()


# =============================================================================
# ReadoutAnyVIF Class Tests
# =============================================================================


class TestReadoutAnyVIF:
    """Tests for ReadoutAnyVIF class."""

    def test_initialization(self) -> None:
        """Test that ReadoutAnyVIF is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.MASTER_TO_SLAVE, TEST_VIF_PRIMARY_READOUT_ANY)

        assert isinstance(vif, ReadoutAnyVIF)
        assert vif._next_table is _CombinableOrthogonalFieldTable


# =============================================================================
# ManufacturerVIF Class Tests
# =============================================================================


class TestManufacturerVIF:
    """Tests for ManufacturerVIF class."""

    def test_initialization(self) -> None:
        """Test that ManufacturerVIF is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_MANUFACTURER)

        assert isinstance(vif, ManufacturerVIF)
        assert vif._next_table is None


# =============================================================================
# VIFE Class Tests
# =============================================================================


class TestVIFE:
    """Tests for VIFE class and its subclasses."""

    @pytest.mark.parametrize(
        ("vif_code", "vife_code", "expected_next_table"),
        [
            (
                TEST_VIF_PRIMARY_ENERGY_WH_EXT,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIF_PRIMARY_EXTENSION_FB_EXT,
                TEST_VIFE_FIRST_EXTENSION_ENERGY_MWH,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIF_PRIMARY_MANUFACTURER_EXT,
                TEST_VIFE_MANUFACTURER_SPECIFIC,
                None,
            ),
        ],
        ids=["combinable_vife", "true_vife", "manufacturer_vife"],
    )
    def test_initialization(
        self,
        vif_code: int,
        vife_code: int,
        expected_next_table: tuple | None,
    ) -> None:
        """Test that VIFE is initialized correctly with basic attributes."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, vif_code)

        vife = VIFE(CommunicationDirection.SLAVE_TO_MASTER, vife_code, prev_field=vif)

        assert isinstance(vife, VIFE)
        assert vife.prev_field is vif
        assert vif.next_field is vife
        assert vife._chain_position == 1
        assert vife._next_table is expected_next_table

    @pytest.mark.parametrize(
        ("field_chain", "direction", "next_vife_code", "expected_subclass"),
        [
            # ManufacturerVIF → ManufacturerVIFE
            (
                [TEST_VIF_PRIMARY_MANUFACTURER_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_MANUFACTURER_SPECIFIC,
                ManufacturerVIFE,
            ),
            # ManufacturerVIFE → ManufacturerVIFE
            (
                [TEST_VIF_PRIMARY_MANUFACTURER_EXT, TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_MANUFACTURER_SPECIFIC,
                ManufacturerVIFE,
            ),
            # ExtensionCombinableVIFE → CombinableVIFE
            (
                [TEST_VIF_PRIMARY_ENERGY_WH_EXT, TEST_VIFE_COMBINABLE_ORTHOGONAL_EXT_COMBINABLE_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_EXTENSION_PHASE_L1,
                CombinableVIFE,
            ),
            # ExtensionVIF(0xFB) → TrueVIFE
            (
                [TEST_VIF_PRIMARY_EXTENSION_FB_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_FIRST_EXTENSION_ENERGY_MWH,
                TrueVIFE,
            ),
            # ExtensionVIF(0xFD) → ExtensionVIFE
            (
                [TEST_VIF_PRIMARY_EXTENSION_FD_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_SECOND_EXTENSION_SECOND_LEVEL_EXT,
                ExtensionVIFE,
            ),
            # ExtensionVIFE → TrueVIFE
            (
                [TEST_VIF_PRIMARY_EXTENSION_FD_EXT, TEST_VIFE_SECOND_EXTENSION_SECOND_LEVEL_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_SECOND_EXT_SECOND_LEVEL_APP,
                TrueVIFE,
            ),
            # TrueVIF → CombinableVIFE
            (
                [TEST_VIF_PRIMARY_ENERGY_WH_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
                CombinableVIFE,
            ),
            # TrueVIF → ExtensionCombinableVIFE
            (
                [TEST_VIF_PRIMARY_ENERGY_WH_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_EXT_COMBINABLE_EXT,
                ExtensionCombinableVIFE,
            ),
            # TrueVIF → ManufacturerVIFE
            (
                [TEST_VIF_PRIMARY_ENERGY_WH_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MANUFACTURER,
                ManufacturerVIFE,
            ),
            # PlainTextVIF → CombinableVIFE
            (
                [TEST_VIF_PRIMARY_PLAIN_TEXT_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
                CombinableVIFE,
            ),
            # ReadoutAnyVIF → CombinableVIFE
            (
                [TEST_VIF_PRIMARY_READOUT_ANY_EXT],
                CommunicationDirection.MASTER_TO_SLAVE,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
                CombinableVIFE,
            ),
            # ReadoutAnyVIF → ActionVIFE (master-to-slave)
            (
                [TEST_VIF_PRIMARY_READOUT_ANY_EXT],
                CommunicationDirection.MASTER_TO_SLAVE,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_WRITE,
                ActionVIFE,
            ),
            # TrueVIF → ErrorVIFE (slave-to-master)
            (
                [TEST_VIF_PRIMARY_ENERGY_WH_EXT],
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_WRITE,
                ErrorVIFE,
            ),
        ],
        ids=[
            "manufacturer_vif",
            "manufacturer_vife",
            "extension_combinable_vife",
            "extension_fb_to_true_vife",
            "extension_fd_to_extension_vife",
            "extension_vife_to_true_vife",
            "true_vif_to_combinable",
            "true_vif_to_extension_combinable",
            "true_vif_to_manufacturer",
            "plain_text_vif_to_combinable",
            "readout_any_vif_to_combinable",
            "readout_any_vif_to_action",
            "true_vif_to_error",
        ],
    )
    def test_factory_returns_correct_subclass(
        self,
        field_chain: list[int],
        direction: CommunicationDirection,
        next_vife_code: int,
        expected_subclass: type[VIFE],
    ) -> None:
        """Test that VIFE factory pattern returns correct subclass."""
        vif = VIF(direction, field_chain[0])

        current_field: VIF | VIFE = vif
        for vife_code in field_chain[1:]:
            current_field = current_field.create_next_vife(vife_code)

        vife = current_field.create_next_vife(next_vife_code)

        assert isinstance(vife, expected_subclass)
        assert vife.direction == direction
        assert vife._field_code == next_vife_code

    def test_create_vife_after_last_field_raises_error(self) -> None:
        """Test that creating VIFE after last field raises ValueError."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_ENERGY_WH)

        assert vif.last_field is True

        with pytest.raises(ValueError, match=r"Cannot extend VIF/VIFE chain past last field"):
            VIFE(
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
                prev_field=vif,
            )

    def test_create_vife_when_next_field_already_assigned_raises_error(self) -> None:
        """Test that creating VIFE when previous field already has next field raises ValueError."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_ENERGY_WH_EXT)

        assert vif.last_field is False

        first_vife = VIFE(
            CommunicationDirection.SLAVE_TO_MASTER,
            TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
            prev_field=vif,
        )

        assert vif.next_field is first_vife

        with pytest.raises(ValueError, match=r"Previous field already has a next field assigned"):
            VIFE(
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_WRITE,
                prev_field=vif,
            )

    def test_create_vife_exceeding_maximum_chain_length_raises_error(self) -> None:
        """Test that exceeding maximum VIFE chain length raises ValueError."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_MANUFACTURER_EXT)

        current_field: VIF | VIFE = vif
        for i in range(TEST_VIFE_MAXIMUM_CHAIN_LENGTH):
            current_field = VIFE(
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_MANUFACTURER_SPECIFIC_EXT,
                prev_field=current_field,
            )
            assert current_field._chain_position == i + 1

        assert current_field._chain_position == TEST_VIFE_MAXIMUM_CHAIN_LENGTH

        with pytest.raises(ValueError, match=r"Exceeded maximum VIFE chain length"):
            VIFE(
                CommunicationDirection.SLAVE_TO_MASTER,
                TEST_VIFE_MANUFACTURER_SPECIFIC,
                prev_field=current_field,
            )

    def test_create_vife_with_mismatched_direction_raises_error(self) -> None:
        """Test that creating VIFE with different direction than previous field raises ValueError."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_ENERGY_WH_EXT)

        assert vif.direction is CommunicationDirection.SLAVE_TO_MASTER

        with pytest.raises(
            ValueError, match=r"VIFE communication direction does not match previous field communication direction"
        ):
            VIFE(
                CommunicationDirection.MASTER_TO_SLAVE,
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
                prev_field=vif,
            )


# =============================================================================
# TrueVIFE Class Tests
# =============================================================================


class TestTrueVIFE:
    """Tests for TrueVIFE class."""

    @pytest.mark.parametrize(
        (
            "vife_code",
            "expected_description",
            "expected_unit",
            "expected_transformer",
            "expected_data_rules",
            "expected_next_table",
        ),
        [
            (
                TEST_VIFE_FIRST_EXTENSION_ENERGY_MWH,
                ValueDescription.ENERGY,
                ValueUnit.WH,
                ValueTransformer.MULT_10_POW_N_PLUS_5,
                DataRules.Requires.DEFAULT_ABHLVAR,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIFE_FIRST_EXTENSION_VOLUME_M3,
                ValueDescription.VOLUME,
                ValueUnit.M3,
                ValueTransformer.MULT_10_POW_N_PLUS_2,
                DataRules.Requires.DEFAULT_ABHLVAR,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIFE_FIRST_EXTENSION_REACTIVE_POWER_KVAR,
                ValueDescription.REACTIVE_POWER,
                ValueUnit.VAR,
                ValueTransformer.MULT_10_POW_NN,
                DataRules.Requires.DEFAULT_ABHLVAR,
                _CombinableOrthogonalFieldTable,
            ),
        ],
        ids=["energy_mwh", "volume_m3", "reactive_power_kvar"],
    )
    def test_initialization(
        self,
        vife_code: int,
        expected_description: ValueDescription | None,
        expected_unit: ValueUnit | None,
        expected_transformer: ValueTransformer | None,
        expected_data_rules: DataRules.Requires,
        expected_next_table: tuple | None,
    ) -> None:
        """Test that TrueVIFE is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_EXTENSION_FB_EXT)

        vife = VIFE(CommunicationDirection.SLAVE_TO_MASTER, vife_code, prev_field=vif)

        assert isinstance(vife, TrueVIFE)
        assert vife.value_description == expected_description
        assert vife.value_unit == expected_unit
        assert vife.value_transformer == expected_transformer
        assert vife.data_rules == expected_data_rules
        assert vife._next_table is expected_next_table


# =============================================================================
# ExtensionVIFE Class Tests
# =============================================================================


class TestExtensionVIFE:
    """Tests for ExtensionVIFE class."""

    def test_initialization(self) -> None:
        """Test that ExtensionVIFE is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_EXTENSION_FD_EXT)

        vife = VIFE(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIFE_SECOND_EXTENSION_SECOND_LEVEL_EXT, prev_field=vif)

        assert isinstance(vife, ExtensionVIFE)
        assert vife._next_table is _SecondExtensionSecondLevelFieldTable


# =============================================================================
# CombinableVIFE Class Tests
# =============================================================================


class TestCombinableVIFE:
    """Tests for CombinableVIFE class."""

    @pytest.mark.parametrize(
        (
            "vife_code",
            "expected_description_transformer",
            "expected_unit_transformer",
            "expected_transformer",
            "expected_data_rules",
            "expected_next_table",
        ),
        [
            (
                TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000,
                None,
                None,
                ValueTransformer.MULT_1000,
                None,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIFE_COMBINABLE_ORTHOGONAL_INCREMENT_INPUT_PULSE,
                None,
                None,
                None,
                DataRules.Requires.ANY,
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIFE_COMBINABLE_ORTHOGONAL_ADD_CORR,
                None,
                None,
                ValueTransformer.ADD_10_POW_NN_MINUS_3,
                None,
                _CombinableOrthogonalFieldTable,
            ),
        ],
        ids=["mult_corr_1000", "increment_input_pulse", "add_corr"],
    )
    def test_initialization(
        self,
        vife_code: int,
        expected_description_transformer: ValueDescriptionTransformer | None,
        expected_unit_transformer: ValueUnitTransformer | None,
        expected_transformer: ValueTransformer | None,
        expected_data_rules: DataRules.Requires | None,
        expected_next_table: tuple | None,
    ) -> None:
        """Test that CombinableVIFE is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_ENERGY_WH_EXT)

        vife = VIFE(CommunicationDirection.SLAVE_TO_MASTER, vife_code, prev_field=vif)

        assert isinstance(vife, CombinableVIFE)
        assert vife.value_description_transformer == expected_description_transformer
        assert vife.value_unit_transformer == expected_unit_transformer
        assert vife.value_transformer == expected_transformer
        assert vife.data_rules == expected_data_rules
        assert vife._next_table is expected_next_table


# =============================================================================
# ExtensionCombinableVIFE Class Tests
# =============================================================================


class TestExtensionCombinableVIFE:
    """Tests for ExtensionCombinableVIFE class."""

    def test_initialization(self) -> None:
        """Test that ExtensionCombinableVIFE is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_ENERGY_WH_EXT)

        vife = VIFE(
            CommunicationDirection.SLAVE_TO_MASTER,
            TEST_VIFE_COMBINABLE_ORTHOGONAL_EXT_COMBINABLE_EXT,
            prev_field=vif,
        )

        assert isinstance(vife, ExtensionCombinableVIFE)
        assert vife._next_table is _CombinableExtensionFieldTable


# =============================================================================
# ActionVIFE Class Tests
# =============================================================================


class TestActionVIFE:
    """Tests for ActionVIFE class."""

    @pytest.mark.parametrize(
        ("vife_code", "expected_action", "expected_next_table"),
        [
            (TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_WRITE, "Write (replace)", _CombinableOrthogonalFieldTable),
            (TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_ADD, "Add value", _CombinableOrthogonalFieldTable),
            (TEST_VIFE_COMBINABLE_ORTHOGONAL_ACTION_SUBTRACT, "Subtract value", _CombinableOrthogonalFieldTable),
        ],
        ids=["action_write", "action_add", "action_subtract"],
    )
    def test_initialization(self, vife_code: int, expected_action: str, expected_next_table: tuple | None) -> None:
        """Test that ActionVIFE is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.MASTER_TO_SLAVE, TEST_VIF_PRIMARY_READOUT_ANY_EXT)

        vife = VIFE(CommunicationDirection.MASTER_TO_SLAVE, vife_code, prev_field=vif)

        assert isinstance(vife, ActionVIFE)
        assert vife.action == expected_action
        assert vife._next_table is expected_next_table


# =============================================================================
# ErrorVIFE Class Tests
# =============================================================================


class TestErrorVIFE:
    """Tests for ErrorVIFE class."""

    @pytest.mark.parametrize(
        ("vife_code", "expected_error", "expected_error_group", "expected_next_table"),
        [
            (TEST_VIFE_COMBINABLE_ORTHOGONAL_ERROR_NONE, "None", "DIF errors", _CombinableOrthogonalFieldTable),
            (
                TEST_VIFE_COMBINABLE_ORTHOGONAL_ERROR_TOO_MANY_DIFES,
                "Too many DIFEs",
                "DIF errors",
                _CombinableOrthogonalFieldTable,
            ),
            (
                TEST_VIFE_COMBINABLE_ORTHOGONAL_ERROR_TOO_MANY_VIFES,
                "Too many VIFEs",
                "VIF errors",
                _CombinableOrthogonalFieldTable,
            ),
        ],
        ids=["error_none", "error_too_many_difes", "error_too_many_vifes"],
    )
    def test_initialization(
        self, vife_code: int, expected_error: str, expected_error_group: str, expected_next_table: tuple | None
    ) -> None:
        """Test that ErrorVIFE is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_ENERGY_WH_EXT)

        vife = VIFE(CommunicationDirection.SLAVE_TO_MASTER, vife_code, prev_field=vif)

        assert isinstance(vife, ErrorVIFE)
        assert vife.error == expected_error
        assert vife.error_group == expected_error_group
        assert vife._next_table is expected_next_table


# =============================================================================
# ManufacturerVIFE Class Tests
# =============================================================================


class TestManufacturerVIFE:
    """Tests for ManufacturerVIFE class."""

    def test_initialization(self) -> None:
        """Test that ManufacturerVIFE is initialized correctly from descriptor."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_MANUFACTURER_EXT)

        vife = VIFE(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIFE_MANUFACTURER_SPECIFIC, prev_field=vif)

        assert isinstance(vife, ManufacturerVIFE)
        assert vife._next_table is None


# =============================================================================
# VIF.from_bytes_async() Tests
# =============================================================================


class TestVIFFromBytesAsync:
    """Tests for VIF.from_bytes_async() static method."""

    @pytest.mark.parametrize(
        "byte_sequence",
        [
            deque(
                [
                    [],
                ]
            ),  # Empty bytes
            deque(
                [
                    [TEST_VIF_PRIMARY_ENERGY_WH, TEST_VIF_PRIMARY_ENERGY_WH],
                ]
            ),  # Too many bytes
        ],
        ids=["empty", "too_many"],
    )
    async def test_vif_byte_count_error(self, byte_sequence: deque[list[int]]) -> None:
        """Test ValueError when stream provides wrong number of bytes for VIF."""

        async def get_next_bytes(n: int) -> bytes:
            assert byte_sequence
            return bytes(byte_sequence.popleft())

        with pytest.raises(ValueError, match=r"Expected exactly one byte for VIF"):
            await VIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

    @pytest.mark.parametrize(
        "byte_sequence",
        [
            deque(
                [
                    [TEST_VIF_PRIMARY_ENERGY_WH_EXT],
                    [],
                ]
            ),  # VIF with extension, empty VIFE bytes
            deque(
                [
                    [TEST_VIF_PRIMARY_ENERGY_WH_EXT],
                    [TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000, TEST_VIFE_COMBINABLE_ORTHOGONAL_MULT_CORR_1000],
                ]
            ),  # Too many VIFE bytes
        ],
        ids=["empty", "too_many"],
    )
    async def test_vife_byte_count_error(self, byte_sequence: deque[list[int]]) -> None:
        """Test ValueError when stream provides wrong number of bytes for VIFE."""

        async def get_next_bytes(n: int) -> bytes:
            assert byte_sequence
            return bytes(byte_sequence.popleft())

        with pytest.raises(ValueError, match=r"Expected exactly one byte for VIFE"):
            await VIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

    @pytest.mark.parametrize(
        ("byte_sequence", "expected_types"),
        [
            # Single VIF, no extension (shortest)
            (
                deque(
                    [
                        [TEST_VIF_PRIMARY_ENERGY_WH],
                    ]
                ),
                deque(
                    [
                        TrueVIF,
                    ]
                ),
            ),
            # VIF + 4 VIFEs (medium) - tests multiple VIFE types
            (
                deque(
                    [
                        [TEST_VIF_PRIMARY_EXTENSION_FD_EXT],
                        [TEST_VIFE_SECOND_EXTENSION_SECOND_LEVEL_EXT],
                        [TEST_VIFE_SECOND_EXT_SECOND_LEVEL_APP_EXT],
                        [TEST_VIFE_COMBINABLE_ORTHOGONAL_EXT_COMBINABLE_EXT],
                        [TEST_VIFE_COMBINABLE_EXTENSION_PHASE_L1],
                    ]
                ),
                deque(
                    [
                        ExtensionVIF,
                        ExtensionVIFE,
                        TrueVIFE,
                        ExtensionCombinableVIFE,
                        CombinableVIFE,
                    ]
                ),
            ),
            # VIF + 10 VIFEs (longest - max chain length)
            (
                deque(
                    [
                        [TEST_VIF_PRIMARY_MANUFACTURER_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC_EXT],
                        [TEST_VIFE_MANUFACTURER_SPECIFIC],
                    ]
                ),
                deque(
                    [
                        ManufacturerVIF,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                        ManufacturerVIFE,
                    ]
                ),
            ),
        ],
        ids=["single_vif", "vif_plus_four_vifes", "vif_plus_ten_vifes"],
    )
    async def test_parse_vif_chain(
        self,
        byte_sequence: deque[list[int]],
        expected_types: deque[type],
    ) -> None:
        """Test parsing VIF chains with various VIFE configurations."""

        async def get_next_bytes(n: int) -> bytes:
            assert byte_sequence
            return bytes(byte_sequence.popleft())

        result = await VIF.from_bytes_async(CommunicationDirection.SLAVE_TO_MASTER, get_next_bytes)

        assert not byte_sequence

        current_field: VIF | VIFE = result[0]

        while expected_types:
            assert isinstance(current_field, expected_types.popleft())

            if current_field.next_field is None:
                break

            current_field = current_field.next_field

        assert not expected_types

        assert current_field.next_field is None

        assert current_field.last_field is True


# =============================================================================
# PlainTextVIF.ascii_unit_from_bytes_async() Tests
# =============================================================================


class TestPlainTextVIFAsciiUnitFromBytesAsync:
    """Tests for PlainTextVIF.ascii_unit_from_bytes_async() method."""

    async def test_already_set_raises_error(self) -> None:
        """Test ValueError when ASCII unit is already set."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)
        vif.set_ascii_unit("kWh")

        async def get_next_bytes(n: int) -> bytes:
            return bytes([3, 0x68, 0x57, 0x6B])

        with pytest.raises(ValueError, match="ASCII unit already set"):
            await vif.ascii_unit_from_bytes_async(get_next_bytes)

    @pytest.mark.parametrize(
        ("byte_sequence", "expected_error"),
        [
            (deque([[]]), "Expected exactly one byte for ASCII length"),
            (deque([[1, 2]]), "Expected exactly one byte for ASCII length"),
            (deque([[0]]), "Invalid ASCII length"),
            (deque([[3], [0x68, 0x57]]), "Expected exactly 3 bytes for ASCII text"),
        ],
        ids=["empty_length", "too_many_length", "zero_length", "wrong_text_length"],
    )
    async def test_invalid_bytes_raises_error(self, byte_sequence: deque[list[int]], expected_error: str) -> None:
        """Test ValueError for various invalid byte sequences."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        async def get_next_bytes(n: int) -> bytes:
            assert byte_sequence
            return bytes(byte_sequence.popleft())

        with pytest.raises(ValueError, match=expected_error):
            await vif.ascii_unit_from_bytes_async(get_next_bytes)

    async def test_non_ascii_bytes_raises_error(self) -> None:
        """Test UnicodeDecodeError for non-ASCII bytes."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        byte_sequence = deque([[3], [0x80, 0x41, 0x42]])

        async def get_next_bytes(n: int) -> bytes:
            assert byte_sequence
            return bytes(byte_sequence.popleft())

        with pytest.raises(UnicodeDecodeError):
            await vif.ascii_unit_from_bytes_async(get_next_bytes)

    @pytest.mark.parametrize(
        ("byte_sequence", "expected_unit"),
        [
            (deque([[1], [0x41]]), "A"),
            (deque([[3], [0x68, 0x57, 0x6B]]), "kWh"),
            (deque([[255], [0x61] * 255]), "a" * 255),
        ],
        ids=["1_char", "3_chars", "255_chars"],
    )
    async def test_parse_ascii_unit(self, byte_sequence: deque[list[int]], expected_unit: str) -> None:
        """Test parsing valid ASCII unit byte sequences."""
        vif = VIF(CommunicationDirection.SLAVE_TO_MASTER, TEST_VIF_PRIMARY_PLAIN_TEXT)
        assert isinstance(vif, PlainTextVIF)

        async def get_next_bytes(n: int) -> bytes:
            assert byte_sequence
            return bytes(byte_sequence.popleft())

        await vif.ascii_unit_from_bytes_async(get_next_bytes)

        assert vif.value_unit == expected_unit
        assert vif.is_ascii_unit_set() is True
