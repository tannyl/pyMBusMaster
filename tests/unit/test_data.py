"""Unit tests for Data classes, enums, and decoder functions.

This module contains comprehensive tests for the M-Bus data type system including:
- Numeric decoders (BCD, signed/unsigned integers, floats)
- Boolean/bit array decoders
- Date/time decoders
- LVAR (variable-length) decoders
- DataType and LVARType enums
- DataRules validation system
- Data class initialization and async parsing
"""

from __future__ import annotations

import math

import pytest

from src.mbusmaster.protocol.data import (
    Data,
    DataRules,
    DataType,
    LVARType,
    _decode_lvar_binary,
    _decode_lvar_negative_bcd,
    _decode_lvar_positive_bcd,
    _decode_lvar_text_8859_1,
    _decode_type_a,
    _decode_type_b,
    _decode_type_c,
    _decode_type_d,
    _decode_type_f,
    _decode_type_g,
    _decode_type_h,
    _decode_type_i,
    _decode_type_j,
    _decode_type_k,
    _decode_type_l,
    _decode_type_m,
)
from src.mbusmaster.protocol.value import (
    BooleanArrayValue,  # noqa: F401 - Used in parametrize decorators
    FloatValue,  # noqa: F401 - Used in parametrize decorators
    IntegerValue,
    StringValue,  # noqa: F401 - Used in parametrize decorators
)

# =============================================================================
# Numeric Data Type Decoder Tests
# =============================================================================


class TestDecodeTypeA:
    """Tests for _decode_type_a (BCD decoder)."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_value"),
        [
            # Valid BCD values
            (b"\x12", IntegerValue(True, 12)),
            (b"\x34\x12", IntegerValue(True, 1234)),
            (b"\x56\x34\x12", IntegerValue(True, 123456)),
            (b"\x00", IntegerValue(True, 0)),
            (b"\x99\x99", IntegerValue(True, 9999)),
            # Negative BCD (F-nibble in MSB position)
            (b"\xf1", IntegerValue(True, -1)),
            (b"\x34\xf1", IntegerValue(True, -134)),
            (b"\x99\x99\x99\xf9", IntegerValue(True, -9999999)),
            # Invalid BCD (A-E nibbles)
            (b"\xaa", IntegerValue(False)),
            (b"\x1a", IntegerValue(False)),
            (b"\xba", IntegerValue(False)),
            (b"\x12\x3e", IntegerValue(False)),
            # Edge cases - leading zeros
            (b"\x01\x00", IntegerValue(True, 1)),
            (b"\x00\x00", IntegerValue(True, 0)),
        ],
        ids=[
            "single_byte_12",
            "two_bytes_1234",
            "three_bytes_123456",
            "zero",
            "max_two_bytes_9999",
            "negative_1",
            "negative_134",
            "negative_9999999",
            "invalid_aa_nibble",
            "invalid_a_nibble",
            "invalid_b_nibble",
            "invalid_e_nibble",
            "leading_zero_01_00",
            "leading_zeros_00_00",
        ],
    )
    def test_decode_valid_and_invalid_bcd(self, input_bytes: bytes, expected_value: IntegerValue) -> None:
        """Test BCD decoding with valid, negative, invalid, and edge case values."""
        result = _decode_type_a(input_bytes)
        assert result.is_valid is expected_value.is_valid
        assert result == expected_value


class TestDecodeTypeB:
    """Tests for _decode_type_b (signed integer decoder)."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_value"),
        [
            # Positive values
            (b"\x00", IntegerValue(True, 0)),
            (b"\x01", IntegerValue(True, 1)),
            (b"\x7f", IntegerValue(True, 127)),
            (b"\x00\x01", IntegerValue(True, 256)),
            (b"\xff\x7f", IntegerValue(True, 32767)),
            # Negative values (two's complement)
            (b"\xff", IntegerValue(True, -1)),
            (b"\x81", IntegerValue(True, -127)),
            (b"\xff\xff", IntegerValue(True, -1)),
            (b"\x01\x80", IntegerValue(True, -32767)),
            # Invalid markers (most negative value for bit width)
            (b"\x80", IntegerValue(False)),  # -128 for 1 byte
            (b"\x00\x80", IntegerValue(False)),  # -32768 for 2 bytes
            (b"\x00\x00\x80", IntegerValue(False)),  # -2^23 for 3 bytes
            (b"\x00\x00\x00\x80", IntegerValue(False)),  # -2^31 for 4 bytes
            # Edge cases - leading zeros
            (b"\x01\x00", IntegerValue(True, 1)),  # Positive with leading zero
            (b"\x00\x00", IntegerValue(True, 0)),  # Zero with leading zero
            (b"\xff\xff\xff", IntegerValue(True, -1)),  # Negative with sign extension
        ],
        ids=[
            "zero",
            "positive_1",
            "positive_127",
            "positive_256",
            "positive_32767",
            "negative_1_one_byte",
            "negative_127",
            "negative_1_two_bytes",
            "negative_32767",
            "invalid_marker_1_byte",
            "invalid_marker_2_bytes",
            "invalid_marker_3_bytes",
            "invalid_marker_4_bytes",
            "leading_zero_positive",
            "leading_zero_zero",
            "sign_extension_negative",
        ],
    )
    def test_decode_signed_integers(self, input_bytes: bytes, expected_value: IntegerValue) -> None:
        """Test signed integer decoding with positive, negative, invalid, and edge case values."""
        result = _decode_type_b(input_bytes)
        assert result.is_valid is expected_value.is_valid
        assert result == expected_value


class TestDecodeTypeC:
    """Tests for _decode_type_c (unsigned integer decoder)."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_value"),
        [
            # Valid unsigned values
            (b"\x00", IntegerValue(True, 0)),
            (b"\x01", IntegerValue(True, 1)),
            (b"\xfe", IntegerValue(True, 254)),
            (b"\x00\x01", IntegerValue(True, 256)),
            (b"\xfe\xff", IntegerValue(True, 65534)),
            # Invalid markers (all bits set = max value for bit width)
            (b"\xff", IntegerValue(False)),  # 255 for 1 byte
            (b"\xff\xff", IntegerValue(False)),  # 65535 for 2 bytes
            (b"\xff\xff\xff", IntegerValue(False)),  # 2^24-1 for 3 bytes
            (b"\xff\xff\xff\xff", IntegerValue(False)),  # 2^32-1 for 4 bytes
            # Edge cases - leading zeros
            (b"\x01\x00", IntegerValue(True, 1)),  # Positive with leading zero
            (b"\x00\x00", IntegerValue(True, 0)),  # Zero with leading zero
        ],
        ids=[
            "zero",
            "one",
            "254",
            "256",
            "65534",
            "invalid_marker_1_byte",
            "invalid_marker_2_bytes",
            "invalid_marker_3_bytes",
            "invalid_marker_4_bytes",
            "leading_zero_01_00",
            "leading_zeros_00_00",
        ],
    )
    def test_decode_unsigned_integers(self, input_bytes: bytes, expected_value: IntegerValue) -> None:
        """Test unsigned integer decoding with valid, invalid, and edge case values."""
        result = _decode_type_c(input_bytes)
        assert result.is_valid is expected_value.is_valid
        assert result == expected_value


class TestDecodeTypeH:
    """Tests for _decode_type_h (IEEE 754 float decoder)."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_value"),
        [
            # Valid float values
            (b"\x00\x00\x00\x00", FloatValue(True, 0.0)),
            (b"\x00\x00\x80\x3f", FloatValue(True, 1.0)),
            (b"\x00\x00\x80\xbf", FloatValue(True, -1.0)),
            (b"\x79\xe9\xf6\x42", FloatValue(True, 123.456)),
            (b"\xf0\xff\x79\xc4", FloatValue(True, -999.999)),
            # Special float values (infinity)
            (b"\x00\x00\x80\x7f", FloatValue(True, float("inf"))),
            (b"\x00\x00\x80\xff", FloatValue(True, float("-inf"))),
            # Invalid marker (NaN)
            (b"\x00\x00\xc0\x7f", FloatValue(False)),
        ],
        ids=[
            "zero",
            "one",
            "negative_one",
            "positive_float",
            "negative_float",
            "positive_infinity",
            "negative_infinity",
            "nan_invalid",
        ],
    )
    def test_decode_float_values(self, input_bytes: bytes, expected_value: FloatValue) -> None:
        """Test IEEE 754 float decoding with valid and invalid values."""
        result = _decode_type_h(input_bytes)
        assert result.is_valid is expected_value.is_valid
        if math.isfinite(expected_value):
            assert math.isfinite(result)
            assert math.isclose(result, expected_value, rel_tol=1e-6)
        elif math.isinf(expected_value):
            assert math.isinf(result)
            assert (result > 0) is (expected_value > 0)
        else:
            assert math.isnan(result)

    def test_decode_invalid_length(self) -> None:
        """Test that wrong byte length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid data length for float: 2 bytes"):
            _decode_type_h(b"\x00\x00")


# =============================================================================
# Boolean/Bit Array Decoder Tests
# =============================================================================


class TestDecodeTypeD:
    """Tests for _decode_type_d (boolean bit array decoder)."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_bits"),
        [
            # Single byte patterns
            (
                b"\x00",
                (
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                ),
            ),
            (
                b"\xff",
                (
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                ),
            ),
            (
                b"\x01",
                (
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                ),
            ),
            (
                b"\x80",
                (
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                ),
            ),
            (
                b"\xaa",
                (
                    False,
                    True,
                    False,
                    True,
                    False,
                    True,
                    False,
                    True,
                ),
            ),
            (
                b"\x55",
                (
                    True,
                    False,
                    True,
                    False,
                    True,
                    False,
                    True,
                    False,
                ),
            ),
            # Multi-byte patterns
            (
                b"\x00\xff",
                (
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                    True,
                ),
            ),
            (
                b"\x01\x02",
                (
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                ),
            ),
        ],
        ids=[
            "all_zeros",
            "all_ones",
            "bit_0_set",
            "bit_7_set",
            "alternating_aa",
            "alternating_55",
            "two_bytes_00_ff",
            "two_bytes_01_02",
        ],
    )
    def test_decode_bit_arrays(self, input_bytes: bytes, expected_bits: tuple[bool, ...]) -> None:
        """Test boolean bit array decoding with various patterns."""
        result = _decode_type_d(input_bytes)
        assert result.is_valid
        assert result.boolean_array_value == expected_bits


# =============================================================================
# Date/Time Decoder Tests
# =============================================================================


class TestDecodeTypeG:
    """Tests for _decode_type_g (Date CP16 decoder)."""

    def test_decode_valid_date(self) -> None:
        """Test decoding valid date values."""
        # Date: 2023-12-25 (day=25, month=12, year=23)
        # Encoding: bits 0-4: day, bits 5-8: month low nibble, bits 9-15: year + month high bit
        data = b"\x19\x6c"  # Binary calculation for Dec 25, 2023
        result = _decode_type_g(data)
        assert result.is_valid
        # TODO: Verify actual date values when TemporalValue is complete

    def test_decode_invalid_marker(self) -> None:
        """Test that 0xFFFF invalid marker is detected."""
        result = _decode_type_g(b"\xff\xff")
        assert not result.is_valid

    def test_decode_invalid_month(self) -> None:
        """Test that invalid month raises ValueError."""
        # Month = 13 (invalid, not 15 which is allowed)
        with pytest.raises(ValueError, match="Invalid month"):
            _decode_type_g(b"\x00\x0d")

    def test_decode_invalid_year(self) -> None:
        """Test that invalid year raises ValueError."""
        # Year = 100 (invalid, not 127 which is allowed), month=1, day=1
        with pytest.raises(ValueError, match="Invalid year"):
            _decode_type_g(b"\x81\xc1")

    def test_decode_wrong_length(self) -> None:
        """Test that wrong byte length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid data length for date: 1 bytes"):
            _decode_type_g(b"\x00")


class TestDecodeTypeF:
    """Tests for _decode_type_f (DateTime CP32 decoder)."""

    def test_decode_valid_datetime(self) -> None:
        """Test decoding valid date/time values."""
        # Sample valid datetime
        data = b"\x1e\x0c\x19\x6c"  # minute=30, hour=12, day=25, month=12, year=23
        result = _decode_type_f(data)
        assert result.is_valid
        # TODO: Verify actual datetime values when TemporalValue is complete

    def test_decode_invalid_bit_set(self) -> None:
        """Test that IV bit (bit 7 of byte 0) marks data invalid."""
        data = b"\x9e\x00\x00\x00"  # IV bit set
        result = _decode_type_f(data)
        assert not result.is_valid

    def test_decode_invalid_minute(self) -> None:
        """Test that invalid minute raises ValueError."""
        # Minute = 60 (invalid, not 63 which is allowed)
        with pytest.raises(ValueError, match="Invalid minute"):
            _decode_type_f(b"\x3c\x00\x00\x00")

    def test_decode_invalid_hour(self) -> None:
        """Test that invalid hour raises ValueError."""
        # Hour = 24 (invalid, not 31 which is allowed)
        with pytest.raises(ValueError, match="Invalid hour"):
            _decode_type_f(b"\x00\x18\x00\x00")

    def test_decode_wrong_length(self) -> None:
        """Test that wrong byte length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid data length for datetime: 3 bytes"):
            _decode_type_f(b"\x00\x00\x00")


class TestDecodeTypeJ:
    """Tests for _decode_type_j (Time CP24 decoder)."""

    def test_decode_valid_time(self) -> None:
        """Test decoding valid time values."""
        # Time: 12:34:56 (hour=12, minute=34, second=56)
        data = b"\x38\x22\x0c"
        result = _decode_type_j(data)
        assert result.is_valid
        # TODO: Verify actual time values when TemporalValue is complete

    def test_decode_invalid_marker(self) -> None:
        """Test that 0xFFFFFF invalid marker is detected."""
        result = _decode_type_j(b"\xff\xff\xff")
        assert not result.is_valid

    def test_decode_invalid_second(self) -> None:
        """Test that invalid second raises ValueError."""
        # Second = 60 (invalid, not 63 which is allowed)
        with pytest.raises(ValueError, match="Invalid second"):
            _decode_type_j(b"\x3c\x00\x00")

    def test_decode_invalid_minute(self) -> None:
        """Test that invalid minute raises ValueError."""
        # Minute = 60 (invalid, not 63 which is allowed)
        with pytest.raises(ValueError, match="Invalid minute"):
            _decode_type_j(b"\x00\x3c\x00")

    def test_decode_wrong_length(self) -> None:
        """Test that wrong byte length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid data length for time: 2 bytes"):
            _decode_type_j(b"\x00\x00")


class TestDecodeTypeI:
    """Tests for _decode_type_i (DateTime CP48 decoder)."""

    def test_decode_valid_datetime(self) -> None:
        """Test decoding valid full date/time values."""
        # Sample valid datetime with metadata
        data = b"\x38\x22\x0c\x19\x6c\x00"
        result = _decode_type_i(data)
        assert result.is_valid
        # TODO: Verify actual datetime and metadata when TemporalValue is complete

    def test_decode_invalid_bit_set(self) -> None:
        """Test that IV bit (bit 7 of byte 1) marks data invalid."""
        data = b"\x00\x80\x00\x00\x00\x00"  # IV bit set
        result = _decode_type_i(data)
        assert not result.is_valid

    def test_decode_invalid_second(self) -> None:
        """Test that invalid second raises ValueError."""
        # Second = 60 (invalid, not 63 which is allowed)
        with pytest.raises(ValueError, match="Invalid second"):
            _decode_type_i(b"\x3c\x00\x00\x00\x00\x00")

    def test_decode_invalid_week(self) -> None:
        """Test that invalid week raises ValueError."""
        # Week = 54 (invalid, not 0 which is allowed)
        with pytest.raises(ValueError, match="Invalid week"):
            _decode_type_i(b"\x00\x00\x00\x00\x00\x36")

    def test_decode_wrong_length(self) -> None:
        """Test that wrong byte length raises ValueError."""
        with pytest.raises(ValueError, match="Invalid data length for datetime: 5 bytes"):
            _decode_type_i(b"\x00\x00\x00\x00\x00")


# =============================================================================
# Special Data Type Decoder Tests (Stubs for TODO functions)
# =============================================================================


class TestDecodeTypeK:
    """Tests for _decode_type_k (daylight savings decoder).

    TODO: Implement full tests when decoder is complete.
    """

    def test_raises_not_implemented(self) -> None:
        """Test that decoder raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Type K decoder not implemented"):
            _decode_type_k(b"\x00\x00\x00\x00")


class TestDecodeTypeL:
    """Tests for _decode_type_l (listening window decoder).

    TODO: Implement full tests when decoder is complete.
    """

    def test_raises_not_implemented(self) -> None:
        """Test that decoder raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Type L decoder not implemented"):
            _decode_type_l(b"\x00")


class TestDecodeTypeM:
    """Tests for _decode_type_m (date/time or duration decoder).

    TODO: Implement full tests when decoder is complete.
    """

    def test_raises_not_implemented(self) -> None:
        """Test that decoder raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="Type M decoder not implemented"):
            _decode_type_m(b"\x00")


# =============================================================================
# LVAR Decoder Tests
# =============================================================================


class TestDecodeLvarText8859_1:  # noqa: N801
    """Tests for _decode_lvar_text_8859_1 (ISO 8859-1 text decoder)."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_text"),
        [
            # ASCII text
            (b"", ""),
            (b"Hello", "Hello"),
            (b"Test 123", "Test 123"),
            # Extended Latin characters (ISO 8859-1)
            (b"\xc5\xe5\xc6\xe6\xd8\xf8", "ÅåÆæØø"),  # Nordic characters
            (b"\xe9\xe8\xea", "éèê"),  # French accents
            (b"\xfc\xf6\xe4", "üöä"),  # German umlauts
        ],
        ids=[
            "empty_string",
            "ascii_hello",
            "ascii_with_numbers",
            "nordic_characters",
            "french_accents",
            "german_umlauts",
        ],
    )
    def test_decode_text(self, input_bytes: bytes, expected_text: str) -> None:
        """Test ISO 8859-1 text decoding with ASCII and extended characters."""
        result = _decode_lvar_text_8859_1(input_bytes)
        assert result.is_valid
        assert result == expected_text


class TestDecodeLVARPositiveBCD:
    """Tests for _decode_lvar_positive_bcd decoder."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_value"),
        [
            # Valid positive BCD
            (b"\x12", IntegerValue(True, 12)),
            (b"\x34\x12", IntegerValue(True, 1234)),
            (b"\x00", IntegerValue(True, 0)),
            # Invalid BCD
            (b"\xaa", IntegerValue(False)),
        ],
        ids=["bcd_12", "bcd_1234", "bcd_zero", "invalid_bcd"],
    )
    def test_decode_positive_bcd(self, input_bytes: bytes, expected_value: IntegerValue) -> None:
        """Test positive BCD decoding."""
        result = _decode_lvar_positive_bcd(input_bytes)
        assert result.is_valid == expected_value.is_valid
        assert result == expected_value

    def test_negative_bcd_raises_error(self) -> None:
        """Test that negative BCD raises ValueError."""
        with pytest.raises(ValueError, match="Expected positive BCD number"):
            _decode_lvar_positive_bcd(b"\xf1")  # -1 in BCD


class TestDecodeLVARNegativeBCD:
    """Tests for _decode_lvar_negative_bcd decoder."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_value"),
        [
            # Valid BCD (will be negated)
            (b"\x12", IntegerValue(True, -12)),
            (b"\x34\x12", IntegerValue(True, -1234)),
            (b"\x00", IntegerValue(True, 0)),
            # Invalid BCD
            (b"\xaa", IntegerValue(False)),
        ],
        ids=["bcd_12_negated", "bcd_1234_negated", "bcd_zero", "invalid_bcd"],
    )
    def test_decode_negative_bcd(self, input_bytes: bytes, expected_value: IntegerValue) -> None:
        """Test negative BCD decoding (values are negated)."""
        result = _decode_lvar_negative_bcd(input_bytes)
        assert result.is_valid == expected_value.is_valid
        assert result == expected_value

    def test_f_nibble_sign_raises_error(self) -> None:
        """Test that F-nibble sign marker raises ValueError."""
        with pytest.raises(ValueError, match="should not have F-nibble sign marker"):
            _decode_lvar_negative_bcd(b"\xf1")  # Has F-nibble sign


class TestDecodeLVARBinary:
    """Tests for _decode_lvar_binary (unsigned binary decoder)."""

    @pytest.mark.parametrize(
        ("input_bytes", "expected_value"),
        [
            # Valid unsigned values
            (b"\x00", IntegerValue(True, 0)),
            (b"\x01", IntegerValue(True, 1)),
            (b"\xfe", IntegerValue(True, 254)),
            (b"\x00\x01", IntegerValue(True, 256)),
            # Invalid markers (all 0xFF)
            (b"\xff", IntegerValue(False)),
            (b"\xff\xff", IntegerValue(False)),
            (b"\xff\xff\xff\xff", IntegerValue(False)),
        ],
        ids=[
            "zero",
            "one",
            "254",
            "256",
            "invalid_1_byte",
            "invalid_2_bytes",
            "invalid_4_bytes",
        ],
    )
    def test_decode_binary(self, input_bytes: bytes, expected_value: IntegerValue) -> None:
        """Test unsigned binary decoding with various lengths."""
        result = _decode_lvar_binary(input_bytes)
        assert result.is_valid == expected_value.is_valid
        assert result == expected_value


# =============================================================================
# LVARType Enum Tests
# =============================================================================


class TestLVARType:
    """Tests for LVARType enum."""

    @pytest.mark.parametrize(
        ("lvar_type", "first_code", "last_code", "out_of_range_code"),
        [
            (LVARType.TEXT_STRING, 0x00, 0xBF, 0xC0),
            (LVARType.POSITIVE_BCD, 0xC0, 0xC9, 0xCA),
            (LVARType.NEGATIVE_BCD, 0xD0, 0xD9, 0xDA),
            (LVARType.BINARY_SMALL, 0xE0, 0xEF, 0xF0),
            (LVARType.BINARY_LARGE, 0xF0, 0xF4, 0xF5),
            (LVARType.BINARY_48, 0xF5, 0xF5, 0xF6),
            (LVARType.BINARY_64, 0xF6, 0xF6, 0xF7),
        ],
        ids=[
            "text_string",
            "positive_bcd",
            "negative_bcd",
            "binary_small",
            "binary_large",
            "binary_48",
            "binary_64",
        ],
    )
    def test_lvar_code_ranges(
        self, lvar_type: LVARType, first_code: int, last_code: int, out_of_range_code: int
    ) -> None:
        """Test that LVAR types handle their correct code ranges."""
        assert first_code in lvar_type.value.code_range
        assert last_code in lvar_type.value.code_range
        assert out_of_range_code not in lvar_type.value.code_range

    @pytest.mark.parametrize(
        ("lvar_type", "length_samples"),
        [
            (LVARType.TEXT_STRING, [(0x00, 0), (0x05, 5), (0xBF, 191)]),
            (LVARType.POSITIVE_BCD, [(0xC0, 0), (0xC5, 5), (0xC9, 9)]),
            (LVARType.NEGATIVE_BCD, [(0xD0, 0), (0xD5, 5), (0xD9, 9)]),
            (LVARType.BINARY_SMALL, [(0xE0, 0), (0xE5, 5), (0xEF, 15)]),
            (LVARType.BINARY_LARGE, [(0xF0, 16), (0xF1, 20), (0xF4, 32)]),
            (LVARType.BINARY_48, [(0xF5, 48)]),
            (LVARType.BINARY_64, [(0xF6, 64)]),
        ],
        ids=[
            "text_string",
            "positive_bcd",
            "negative_bcd",
            "binary_small",
            "binary_large",
            "binary_48",
            "binary_64",
        ],
    )
    def test_lvar_length_calculators(self, lvar_type: LVARType, length_samples: list[tuple[int, int]]) -> None:
        """Test that LVAR types calculate correct data lengths."""
        for lvar_code, expected_length in length_samples:
            assert lvar_type.value.length_calculator(lvar_code) == expected_length

    def test_all_decoders_callable(self) -> None:
        """Test that all LVAR types have callable decoders."""
        for lvar_type in LVARType:
            assert callable(lvar_type.value.decoder)


# =============================================================================
# DataType Enum Tests
# =============================================================================


class TestDataType:
    """Tests for DataType enum."""

    @pytest.mark.parametrize(
        ("data_type", "expected_length", "has_decoder"),
        [
            # Type A (BCD)
            (DataType.A_1, 1, True),
            (DataType.A_2, 2, True),
            (DataType.A_3, 3, True),
            (DataType.A_4, 4, True),
            (DataType.A_6, 6, True),
            # Type B (Signed)
            (DataType.B_1, 1, True),
            (DataType.B_2, 2, True),
            (DataType.B_3, 3, True),
            (DataType.B_4, 4, True),
            (DataType.B_6, 6, True),
            (DataType.B_8, 8, True),
            # Type C (Unsigned)
            (DataType.C_1, 1, True),
            (DataType.C_2, 2, True),
            (DataType.C_3, 3, True),
            (DataType.C_4, 4, True),
            (DataType.C_6, 6, True),
            (DataType.C_8, 8, True),
            # Type D (Boolean)
            (DataType.D_1, 1, True),
            (DataType.D_2, 2, True),
            (DataType.D_3, 3, True),
            (DataType.D_4, 4, True),
            (DataType.D_6, 6, True),
            (DataType.D_8, 8, True),
            # Date/Time types
            (DataType.F_4, 4, True),
            (DataType.G_2, 2, True),
            (DataType.H_4, 4, True),
            (DataType.I_6, 6, True),
            (DataType.J_3, 3, True),
            (DataType.K_4, 4, True),
            # Variable length types (have decoders)
            (DataType.L, None, True),
            (DataType.M, None, True),
            # Variable length type (no decoder - uses LVAR)
            (DataType.LVAR, None, False),
            # No data type
            (DataType.NONE, None, False),
        ],
        ids=[
            "a_1",
            "a_2",
            "a_3",
            "a_4",
            "a_6",
            "b_1",
            "b_2",
            "b_3",
            "b_4",
            "b_6",
            "b_8",
            "c_1",
            "c_2",
            "c_3",
            "c_4",
            "c_6",
            "c_8",
            "d_1",
            "d_2",
            "d_3",
            "d_4",
            "d_6",
            "d_8",
            "f_4",
            "g_2",
            "h_4",
            "i_6",
            "j_3",
            "k_4",
            "l_variable",
            "m_variable",
            "lvar_variable",
            "none",
        ],
    )
    def test_data_type_properties(self, data_type: DataType, expected_length: int | None, has_decoder: bool) -> None:
        """Test that DataType has correct length and decoder properties."""
        assert data_type.length == expected_length
        if has_decoder:
            assert callable(data_type.decoder)
        else:
            assert data_type.decoder is None


# =============================================================================
# DataRules Tests
# =============================================================================


class TestDataRules:
    """Comprehensive tests for DataRules type matching system."""

    @pytest.mark.parametrize(
        ("supports", "requires", "expected"),
        [
            # === NONE support ===
            (DataRules.Supports.NONE, DataRules.Requires.ANY, DataType.NONE),
            (DataRules.Supports.NONE, DataRules.Requires.NONE, DataType.NONE),
            (DataRules.Supports.NONE, DataRules.Requires.DEFAULT_ABHLVAR, None),
            (DataRules.Supports.NONE, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.NONE, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.NONE, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.NONE, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.NONE, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.NONE, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.NONE, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.NONE, DataRules.Requires.TEMPORAL_L, None),
            # === BCD_1 support (B_1, C_1, D_1) ===
            (DataRules.Supports.BCD_1, DataRules.Requires.ANY, DataType.B_1),
            (DataRules.Supports.BCD_1, DataRules.Requires.NONE, None),
            (DataRules.Supports.BCD_1, DataRules.Requires.DEFAULT_ABHLVAR, DataType.B_1),
            (DataRules.Supports.BCD_1, DataRules.Requires.ADDRESS_C, DataType.C_1),
            (DataRules.Supports.BCD_1, DataRules.Requires.UNSIGNED_C, DataType.C_1),
            (DataRules.Supports.BCD_1, DataRules.Requires.BOOLEAN_D, DataType.D_1),
            (DataRules.Supports.BCD_1, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.BCD_1, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.BCD_1, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.BCD_1, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.BCD_1, DataRules.Requires.TEMPORAL_L, None),
            # === BCDG_2 support (B_2, C_2, D_2, G_2) ===
            (DataRules.Supports.BCDG_2, DataRules.Requires.ANY, DataType.B_2),
            (DataRules.Supports.BCDG_2, DataRules.Requires.NONE, None),
            (DataRules.Supports.BCDG_2, DataRules.Requires.DEFAULT_ABHLVAR, DataType.B_2),
            (DataRules.Supports.BCDG_2, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.BCDG_2, DataRules.Requires.UNSIGNED_C, DataType.C_2),
            (DataRules.Supports.BCDG_2, DataRules.Requires.BOOLEAN_D, DataType.D_2),
            (DataRules.Supports.BCDG_2, DataRules.Requires.TEMPORAL_G, DataType.G_2),
            (DataRules.Supports.BCDG_2, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.BCDG_2, DataRules.Requires.TEMPORAL_FGIJM, DataType.G_2),
            (DataRules.Supports.BCDG_2, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.BCDG_2, DataRules.Requires.TEMPORAL_L, None),
            # === BCDJ_3 support (B_3, C_3, D_3, J_3) ===
            (DataRules.Supports.BCDJ_3, DataRules.Requires.ANY, DataType.B_3),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.NONE, None),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.DEFAULT_ABHLVAR, DataType.B_3),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.UNSIGNED_C, DataType.C_3),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.BOOLEAN_D, DataType.D_3),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.TEMPORAL_FIJM, DataType.J_3),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.TEMPORAL_FGIJM, DataType.J_3),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.BCDJ_3, DataRules.Requires.TEMPORAL_L, None),
            # === BCDFK_4 support (B_4, C_4, D_4, F_4, K_4) ===
            (DataRules.Supports.BCDFK_4, DataRules.Requires.ANY, DataType.B_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.NONE, None),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.DEFAULT_ABHLVAR, DataType.B_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.UNSIGNED_C, DataType.C_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.BOOLEAN_D, DataType.D_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.TEMPORAL_FIJM, DataType.F_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.TEMPORAL_FGIJM, DataType.F_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.TEMPORAL_K, DataType.K_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.TEMPORAL_L, None),
            # === H_4 support (H_4 only) ===
            (DataRules.Supports.H_4, DataRules.Requires.ANY, DataType.H_4),
            (DataRules.Supports.H_4, DataRules.Requires.NONE, None),
            (DataRules.Supports.H_4, DataRules.Requires.DEFAULT_ABHLVAR, DataType.H_4),
            (DataRules.Supports.H_4, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.H_4, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.H_4, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.H_4, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.H_4, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.H_4, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.H_4, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.H_4, DataRules.Requires.TEMPORAL_L, None),
            # === BCDI_6 support (B_6, C_6, D_6, I_6) ===
            (DataRules.Supports.BCDI_6, DataRules.Requires.ANY, DataType.B_6),
            (DataRules.Supports.BCDI_6, DataRules.Requires.NONE, None),
            (DataRules.Supports.BCDI_6, DataRules.Requires.DEFAULT_ABHLVAR, DataType.B_6),
            (DataRules.Supports.BCDI_6, DataRules.Requires.ADDRESS_C, DataType.C_6),
            (DataRules.Supports.BCDI_6, DataRules.Requires.UNSIGNED_C, DataType.C_6),
            (DataRules.Supports.BCDI_6, DataRules.Requires.BOOLEAN_D, DataType.D_6),
            (DataRules.Supports.BCDI_6, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.BCDI_6, DataRules.Requires.TEMPORAL_FIJM, DataType.I_6),
            (DataRules.Supports.BCDI_6, DataRules.Requires.TEMPORAL_FGIJM, DataType.I_6),
            (DataRules.Supports.BCDI_6, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.BCDI_6, DataRules.Requires.TEMPORAL_L, None),
            # === BCD_8 support (B_8, C_8, D_8) ===
            (DataRules.Supports.BCD_8, DataRules.Requires.ANY, DataType.B_8),
            (DataRules.Supports.BCD_8, DataRules.Requires.NONE, None),
            (DataRules.Supports.BCD_8, DataRules.Requires.DEFAULT_ABHLVAR, DataType.B_8),
            (DataRules.Supports.BCD_8, DataRules.Requires.ADDRESS_C, DataType.C_8),
            (DataRules.Supports.BCD_8, DataRules.Requires.UNSIGNED_C, DataType.C_8),
            (DataRules.Supports.BCD_8, DataRules.Requires.BOOLEAN_D, DataType.D_8),
            (DataRules.Supports.BCD_8, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.BCD_8, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.BCD_8, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.BCD_8, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.BCD_8, DataRules.Requires.TEMPORAL_L, None),
            # === A_1 support ===
            (DataRules.Supports.A_1, DataRules.Requires.ANY, DataType.A_1),
            (DataRules.Supports.A_1, DataRules.Requires.NONE, None),
            (DataRules.Supports.A_1, DataRules.Requires.DEFAULT_ABHLVAR, DataType.A_1),
            (DataRules.Supports.A_1, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.A_1, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.A_1, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.A_1, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.A_1, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.A_1, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.A_1, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.A_1, DataRules.Requires.TEMPORAL_L, None),
            # === A_2 support ===
            (DataRules.Supports.A_2, DataRules.Requires.ANY, DataType.A_2),
            (DataRules.Supports.A_2, DataRules.Requires.NONE, None),
            (DataRules.Supports.A_2, DataRules.Requires.DEFAULT_ABHLVAR, DataType.A_2),
            (DataRules.Supports.A_2, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.A_2, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.A_2, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.A_2, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.A_2, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.A_2, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.A_2, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.A_2, DataRules.Requires.TEMPORAL_L, None),
            # === A_3 support ===
            (DataRules.Supports.A_3, DataRules.Requires.ANY, DataType.A_3),
            (DataRules.Supports.A_3, DataRules.Requires.NONE, None),
            (DataRules.Supports.A_3, DataRules.Requires.DEFAULT_ABHLVAR, DataType.A_3),
            (DataRules.Supports.A_3, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.A_3, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.A_3, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.A_3, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.A_3, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.A_3, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.A_3, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.A_3, DataRules.Requires.TEMPORAL_L, None),
            # === A_4 support ===
            (DataRules.Supports.A_4, DataRules.Requires.ANY, DataType.A_4),
            (DataRules.Supports.A_4, DataRules.Requires.NONE, None),
            (DataRules.Supports.A_4, DataRules.Requires.DEFAULT_ABHLVAR, DataType.A_4),
            (DataRules.Supports.A_4, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.A_4, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.A_4, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.A_4, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.A_4, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.A_4, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.A_4, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.A_4, DataRules.Requires.TEMPORAL_L, None),
            # === LMLVAR support (L, M, LVAR) ===
            (DataRules.Supports.LMLVAR, DataRules.Requires.ANY, DataType.LVAR),
            (DataRules.Supports.LMLVAR, DataRules.Requires.NONE, None),
            (DataRules.Supports.LMLVAR, DataRules.Requires.DEFAULT_ABHLVAR, DataType.LVAR),
            (DataRules.Supports.LMLVAR, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.LMLVAR, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.LMLVAR, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.LMLVAR, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.LMLVAR, DataRules.Requires.TEMPORAL_FIJM, DataType.M),
            (DataRules.Supports.LMLVAR, DataRules.Requires.TEMPORAL_FGIJM, DataType.M),
            (DataRules.Supports.LMLVAR, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.LMLVAR, DataRules.Requires.TEMPORAL_L, DataType.L),
            # === A_6 support ===
            (DataRules.Supports.A_6, DataRules.Requires.ANY, DataType.A_6),
            (DataRules.Supports.A_6, DataRules.Requires.NONE, None),
            (DataRules.Supports.A_6, DataRules.Requires.DEFAULT_ABHLVAR, DataType.A_6),
            (DataRules.Supports.A_6, DataRules.Requires.ADDRESS_C, None),
            (DataRules.Supports.A_6, DataRules.Requires.UNSIGNED_C, None),
            (DataRules.Supports.A_6, DataRules.Requires.BOOLEAN_D, None),
            (DataRules.Supports.A_6, DataRules.Requires.TEMPORAL_G, None),
            (DataRules.Supports.A_6, DataRules.Requires.TEMPORAL_FIJM, None),
            (DataRules.Supports.A_6, DataRules.Requires.TEMPORAL_FGIJM, None),
            (DataRules.Supports.A_6, DataRules.Requires.TEMPORAL_K, None),
            (DataRules.Supports.A_6, DataRules.Requires.TEMPORAL_L, None),
            # === Combined Requires with ANY ===
            (DataRules.Supports.BCDG_2, DataRules.Requires.TEMPORAL_G | DataRules.Requires.ANY, DataType.G_2),
            (DataRules.Supports.BCD_1, DataRules.Requires.TEMPORAL_G | DataRules.Requires.ANY, DataType.B_1),
            (DataRules.Supports.H_4, DataRules.Requires.BOOLEAN_D | DataRules.Requires.ANY, DataType.H_4),
            (DataRules.Supports.BCDFK_4, DataRules.Requires.TEMPORAL_K | DataRules.Requires.ANY, DataType.K_4),
            (DataRules.Supports.BCD_1, DataRules.Requires.TEMPORAL_K | DataRules.Requires.ANY, DataType.B_1),
            (DataRules.Supports.LMLVAR, DataRules.Requires.BOOLEAN_D | DataRules.Requires.ANY, DataType.LVAR),
            (DataRules.Supports.NONE, DataRules.Requires.DEFAULT_ABHLVAR | DataRules.Requires.ANY, DataType.NONE),
        ],
        ids=[
            # NONE (11)
            "NONE_ANY",
            "NONE_NONE",
            "NONE_DEFAULT",
            "NONE_ADDRESS_C",
            "NONE_UNSIGNED_C",
            "NONE_BOOLEAN_D",
            "NONE_TEMPORAL_G",
            "NONE_TEMPORAL_FIJM",
            "NONE_TEMPORAL_FGIJM",
            "NONE_TEMPORAL_K",
            "NONE_TEMPORAL_L",
            # BCD_1 (11)
            "BCD1_ANY",
            "BCD1_NONE",
            "BCD1_DEFAULT",
            "BCD1_ADDRESS_C",
            "BCD1_UNSIGNED_C",
            "BCD1_BOOLEAN_D",
            "BCD1_TEMPORAL_G",
            "BCD1_TEMPORAL_FIJM",
            "BCD1_TEMPORAL_FGIJM",
            "BCD1_TEMPORAL_K",
            "BCD1_TEMPORAL_L",
            # BCDG_2 (11)
            "BCDG2_ANY",
            "BCDG2_NONE",
            "BCDG2_DEFAULT",
            "BCDG2_ADDRESS_C",
            "BCDG2_UNSIGNED_C",
            "BCDG2_BOOLEAN_D",
            "BCDG2_TEMPORAL_G",
            "BCDG2_TEMPORAL_FIJM",
            "BCDG2_TEMPORAL_FGIJM",
            "BCDG2_TEMPORAL_K",
            "BCDG2_TEMPORAL_L",
            # BCDJ_3 (11)
            "BCDJ3_ANY",
            "BCDJ3_NONE",
            "BCDJ3_DEFAULT",
            "BCDJ3_ADDRESS_C",
            "BCDJ3_UNSIGNED_C",
            "BCDJ3_BOOLEAN_D",
            "BCDJ3_TEMPORAL_G",
            "BCDJ3_TEMPORAL_FIJM",
            "BCDJ3_TEMPORAL_FGIJM",
            "BCDJ3_TEMPORAL_K",
            "BCDJ3_TEMPORAL_L",
            # BCDFK_4 (11)
            "BCDFK4_ANY",
            "BCDFK4_NONE",
            "BCDFK4_DEFAULT",
            "BCDFK4_ADDRESS_C",
            "BCDFK4_UNSIGNED_C",
            "BCDFK4_BOOLEAN_D",
            "BCDFK4_TEMPORAL_G",
            "BCDFK4_TEMPORAL_FIJM",
            "BCDFK4_TEMPORAL_FGIJM",
            "BCDFK4_TEMPORAL_K",
            "BCDFK4_TEMPORAL_L",
            # H_4 (11)
            "H4_ANY",
            "H4_NONE",
            "H4_DEFAULT",
            "H4_ADDRESS_C",
            "H4_UNSIGNED_C",
            "H4_BOOLEAN_D",
            "H4_TEMPORAL_G",
            "H4_TEMPORAL_FIJM",
            "H4_TEMPORAL_FGIJM",
            "H4_TEMPORAL_K",
            "H4_TEMPORAL_L",
            # BCDI_6 (11)
            "BCDI6_ANY",
            "BCDI6_NONE",
            "BCDI6_DEFAULT",
            "BCDI6_ADDRESS_C",
            "BCDI6_UNSIGNED_C",
            "BCDI6_BOOLEAN_D",
            "BCDI6_TEMPORAL_G",
            "BCDI6_TEMPORAL_FIJM",
            "BCDI6_TEMPORAL_FGIJM",
            "BCDI6_TEMPORAL_K",
            "BCDI6_TEMPORAL_L",
            # BCD_8 (11)
            "BCD8_ANY",
            "BCD8_NONE",
            "BCD8_DEFAULT",
            "BCD8_ADDRESS_C",
            "BCD8_UNSIGNED_C",
            "BCD8_BOOLEAN_D",
            "BCD8_TEMPORAL_G",
            "BCD8_TEMPORAL_FIJM",
            "BCD8_TEMPORAL_FGIJM",
            "BCD8_TEMPORAL_K",
            "BCD8_TEMPORAL_L",
            # A_1 (11)
            "A1_ANY",
            "A1_NONE",
            "A1_DEFAULT",
            "A1_ADDRESS_C",
            "A1_UNSIGNED_C",
            "A1_BOOLEAN_D",
            "A1_TEMPORAL_G",
            "A1_TEMPORAL_FIJM",
            "A1_TEMPORAL_FGIJM",
            "A1_TEMPORAL_K",
            "A1_TEMPORAL_L",
            # A_2 (11)
            "A2_ANY",
            "A2_NONE",
            "A2_DEFAULT",
            "A2_ADDRESS_C",
            "A2_UNSIGNED_C",
            "A2_BOOLEAN_D",
            "A2_TEMPORAL_G",
            "A2_TEMPORAL_FIJM",
            "A2_TEMPORAL_FGIJM",
            "A2_TEMPORAL_K",
            "A2_TEMPORAL_L",
            # A_3 (11)
            "A3_ANY",
            "A3_NONE",
            "A3_DEFAULT",
            "A3_ADDRESS_C",
            "A3_UNSIGNED_C",
            "A3_BOOLEAN_D",
            "A3_TEMPORAL_G",
            "A3_TEMPORAL_FIJM",
            "A3_TEMPORAL_FGIJM",
            "A3_TEMPORAL_K",
            "A3_TEMPORAL_L",
            # A_4 (11)
            "A4_ANY",
            "A4_NONE",
            "A4_DEFAULT",
            "A4_ADDRESS_C",
            "A4_UNSIGNED_C",
            "A4_BOOLEAN_D",
            "A4_TEMPORAL_G",
            "A4_TEMPORAL_FIJM",
            "A4_TEMPORAL_FGIJM",
            "A4_TEMPORAL_K",
            "A4_TEMPORAL_L",
            # LMLVAR (11)
            "LMLVAR_ANY",
            "LMLVAR_NONE",
            "LMLVAR_DEFAULT",
            "LMLVAR_ADDRESS_C",
            "LMLVAR_UNSIGNED_C",
            "LMLVAR_BOOLEAN_D",
            "LMLVAR_TEMPORAL_G",
            "LMLVAR_TEMPORAL_FIJM",
            "LMLVAR_TEMPORAL_FGIJM",
            "LMLVAR_TEMPORAL_K",
            "LMLVAR_TEMPORAL_L",
            # A_6 (11)
            "A6_ANY",
            "A6_NONE",
            "A6_DEFAULT",
            "A6_ADDRESS_C",
            "A6_UNSIGNED_C",
            "A6_BOOLEAN_D",
            "A6_TEMPORAL_G",
            "A6_TEMPORAL_FIJM",
            "A6_TEMPORAL_FGIJM",
            "A6_TEMPORAL_K",
            "A6_TEMPORAL_L",
            # Combined Requires (7)
            "BCDG2_TEMPORAL_G_OR_ANY",
            "BCD1_TEMPORAL_G_OR_ANY",
            "H4_BOOLEAN_D_OR_ANY",
            "BCDFK4_TEMPORAL_K_OR_ANY",
            "BCD1_TEMPORAL_K_OR_ANY",
            "LMLVAR_BOOLEAN_D_OR_ANY",
            "NONE_DEFAULT_OR_ANY",
        ],
    )
    def test_datarules_matching(
        self, supports: DataRules.Supports, requires: DataRules.Requires, expected: DataType | None
    ) -> None:
        """Test DataRules matching with expected DataType or ValueError."""
        if expected is None:
            with pytest.raises(ValueError, match="No valid DataType found"):
                DataRules(supports, requires)
        else:
            result = DataRules(supports, requires)
            assert result == expected  # type: ignore[comparison-overlap]

    def test_or_operator_combines_requirements(self) -> None:
        """Test that OR operator combines requirements."""
        req1 = DataRules.Requires.TEMPORAL_G
        req2 = DataRules.Requires.TEMPORAL_FIJM
        combined = req1 | req2

        assert len(combined.value) == 2
        assert req1.value[0] in combined.value
        assert req2.value[0] in combined.value

    def test_or_operator_with_any(self) -> None:
        """Test that OR with ANY sets any_valid flag."""
        req1 = DataRules.Requires.TEMPORAL_G
        req2 = DataRules.Requires.ANY
        combined = req1 | req2

        assert combined.any_valid is True

    def test_or_operator_with_non_requires_raises(self) -> None:
        """Test that OR with non-Requires raises AssertionError."""
        req1 = DataRules.Requires.TEMPORAL_G
        with pytest.raises(AssertionError, match="Can only combine Requires"):
            req1 | "invalid"  # type: ignore[operator]

    def test_or_operator_maintains_lifo_order(self) -> None:
        """Test that OR operator maintains LIFO (Last In First Out) order."""
        req1 = DataRules.Requires.TEMPORAL_G
        req2 = DataRules.Requires.TEMPORAL_FIJM
        req3 = DataRules.Requires.BOOLEAN_D

        # Two requirements: newest first (LIFO)
        combined_2 = req1 | req2
        assert combined_2._value_ == (req2._value_[0], req1._value_[0])

        # Three requirements: LIFO order maintained
        combined_3 = req1 | req2 | req3
        assert combined_3._value_ == (req3._value_[0], req2._value_[0], req1._value_[0])

    def test_or_operator_any_always_last(self) -> None:
        """Test that ANY is always placed last in the tuple, regardless of position."""
        req1 = DataRules.Requires.TEMPORAL_G
        req2 = DataRules.Requires.TEMPORAL_FIJM

        # ANY at end: stays last
        with_any_end = req1 | req2 | DataRules.Requires.ANY
        assert with_any_end._value_ == (req2._value_[0], req1._value_[0], DataRules.Requires.ANY._value_[0])

        # ANY in middle: moves to last
        with_any_middle = req1 | DataRules.Requires.ANY | req2
        assert with_any_middle._value_ == (req2._value_[0], req1._value_[0], DataRules.Requires.ANY._value_[0])

        # ANY at start: moves to last
        with_any_start = DataRules.Requires.ANY | req1 | req2
        assert with_any_start._value_ == (req2._value_[0], req1._value_[0], DataRules.Requires.ANY._value_[0])


# =============================================================================
# Data Class Tests
# =============================================================================


class TestData:
    """Tests for Data class initialization."""

    def test_init_with_type_a_1(self) -> None:
        """Test Data initialization with Type A_1 (BCD)."""
        data = Data(b"\x12", DataType.A_1, None)
        assert data.decoded_value.is_valid
        assert data.decoded_value == 12  # type: ignore[comparison-overlap]

    def test_init_with_type_b_2(self) -> None:
        """Test Data initialization with Type B_2 (signed integer)."""
        data = Data(b"\xff\xff", DataType.B_2, None)
        assert data.decoded_value.is_valid
        assert data.decoded_value == -1  # type: ignore[comparison-overlap]

    def test_init_with_type_c_4(self) -> None:
        """Test Data initialization with Type C_4 (unsigned integer)."""
        data = Data(b"\x01\x00\x00\x00", DataType.C_4, None)
        assert data.decoded_value.is_valid
        assert data.decoded_value == 1  # type: ignore[comparison-overlap]

    def test_init_with_type_h_4(self) -> None:
        """Test Data initialization with Type H_4 (float)."""
        data = Data(b"\x79\xe9\xf6\x42", DataType.H_4, None)
        assert data.decoded_value.is_valid
        assert math.isclose(data.decoded_value, 123.456, rel_tol=1e-6)  # type: ignore[arg-type]

    def test_init_with_type_d_1(self) -> None:
        """Test Data initialization with Type D_1 (boolean array)."""
        data = Data(b"\xff", DataType.D_1, None)
        assert data.decoded_value.is_valid
        assert data.decoded_value.boolean_array_value == (True,) * 8  # type: ignore[attr-defined]

    def test_init_with_lvar_text_string(self) -> None:
        """Test Data initialization with LVAR TEXT_STRING."""
        lvar_byte = 0x05  # 5 characters
        text_data = b"Hello"
        data = Data(bytes([lvar_byte]) + text_data, DataType.LVAR, LVARType.TEXT_STRING)
        assert data.decoded_value.is_valid
        assert data.decoded_value == "Hello"  # type: ignore[comparison-overlap]

    def test_init_with_lvar_positive_bcd(self) -> None:
        """Test Data initialization with LVAR POSITIVE_BCD."""
        lvar_byte = 0xC2  # 2 bytes of BCD
        bcd_data = b"\x34\x12"
        data = Data(bytes([lvar_byte]) + bcd_data, DataType.LVAR, LVARType.POSITIVE_BCD)
        assert data.decoded_value.is_valid
        assert data.decoded_value == 1234  # type: ignore[comparison-overlap]

    def test_init_with_none_type_raises(self) -> None:
        """Test that DataType.NONE raises ValueError."""
        with pytest.raises(ValueError, match="Data with DataType.NONE is not valid"):
            Data(b"\x00", DataType.NONE, None)

    def test_init_with_empty_bytes_raises(self) -> None:
        """Test that empty data_bytes raises ValueError."""
        with pytest.raises(ValueError, match="data_bytes cannot be empty"):
            Data(b"", DataType.A_1, None)

    def test_init_with_wrong_length_raises(self) -> None:
        """Test that wrong data length raises ValueError."""
        with pytest.raises(ValueError, match="Expected 2 bytes for A_2, got 1 bytes"):
            Data(b"\x12", DataType.A_2, None)

    def test_init_with_missing_lvar_type_raises(self) -> None:
        """Test that missing lvar_type for LVAR raises ValueError."""
        with pytest.raises(ValueError, match="lvar_type must be provided for LVAR"):
            Data(b"\x05Hello", DataType.LVAR, None)

    def test_init_with_invalid_lvar_code_raises(self) -> None:
        """Test that invalid LVAR code raises ValueError."""
        lvar_byte = 0x00  # TEXT_STRING range
        with pytest.raises(ValueError, match="LVAR code 0x00 is not valid for POSITIVE_BCD"):
            Data(bytes([lvar_byte]) + b"\x12", DataType.LVAR, LVARType.POSITIVE_BCD)


class TestDataFromBytesAsync:
    """Tests for Data.from_bytes_async() method."""

    @pytest.mark.asyncio
    async def test_from_bytes_async_fixed_length(self) -> None:
        """Test async parsing for fixed-length data type."""
        call_count = 0
        max_calls = 1  # Should only call once for fixed-length type

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert call_count < max_calls
            call_count += 1
            return b"\x12\x34\x56\x78"[:n]

        data = await Data.from_bytes_async(DataType.B_4, get_next_bytes)
        assert data.decoded_value.is_valid
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_from_bytes_async_lvar_type(self) -> None:
        """Test async parsing for LVAR data type."""
        byte_stream = b"\x05Hello"
        position = 0
        call_count = 0
        max_calls = len(byte_stream)  # Protect against infinite loops

        async def get_next_bytes(n: int) -> bytes:
            nonlocal position, call_count
            assert call_count < max_calls
            call_count += 1
            result = byte_stream[position : position + n]
            position += n
            return result

        data = await Data.from_bytes_async(DataType.LVAR, get_next_bytes)
        assert data.decoded_value.is_valid
        assert data.decoded_value == "Hello"  # type: ignore[comparison-overlap]

    @pytest.mark.asyncio
    async def test_from_bytes_async_with_none_type_raises(self) -> None:
        """Test that DataType.NONE raises ValueError."""
        call_count = 0
        max_calls = 1  # Should fail immediately

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert call_count < max_calls
            call_count += 1
            return b"\x00" * n

        with pytest.raises(ValueError, match="Data with DataType.NONE is not valid"):
            await Data.from_bytes_async(DataType.NONE, get_next_bytes)

    @pytest.mark.asyncio
    async def test_from_bytes_async_invalid_lvar_code_raises(self) -> None:
        """Test that unsupported LVAR code raises ValueError."""
        call_count = 0
        max_calls = 1  # Should fail after reading LVAR byte

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert call_count < max_calls
            call_count += 1
            return b"\xf7"  # Unsupported LVAR code

        with pytest.raises(ValueError, match="Unsupported LVAR code: 0xF7"):
            await Data.from_bytes_async(DataType.LVAR, get_next_bytes)

    @pytest.mark.asyncio
    async def test_from_bytes_async_lvar_byte_length_validation(self) -> None:
        """Test that LVAR byte must be exactly 1 byte."""
        call_count = 0
        max_calls = 1  # Should fail after first empty read

        async def get_next_bytes(n: int) -> bytes:
            nonlocal call_count
            assert call_count < max_calls
            call_count += 1
            return b""  # Empty return

        with pytest.raises(ValueError, match="LVAR byte must be exactly 1 byte"):
            await Data.from_bytes_async(DataType.LVAR, get_next_bytes)


# =============================================================================
# Error Scenario Tests
# =============================================================================


class TestErrorScenarios:
    """Tests for error scenarios and edge cases."""

    def test_data_initialization_with_invalid_marker(self) -> None:
        """Test that invalid markers in data are properly detected."""
        # Type B with invalid marker (-128 for 1 byte)
        data = Data(b"\x80", DataType.B_1, None)
        assert not data.decoded_value.is_valid

        # Type C with invalid marker (0xFF for 1 byte)
        data = Data(b"\xff", DataType.C_1, None)
        assert not data.decoded_value.is_valid

        # Type H with NaN (invalid marker)
        data = Data(b"\x00\x00\xc0\x7f", DataType.H_4, None)
        assert not data.decoded_value.is_valid
