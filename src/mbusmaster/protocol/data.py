"""Data type definitions and decoding logic for M-Bus protocol.

This module implements the M-Bus data type system according to EN 13757-3:2018.
It provides:

Classes:
    - DataType: Enum of all M-Bus data types with validation and matching
    - LVARType: Enum of variable-length data type interpretations
    - Data: Container for decoded M-Bus data with type information

The data type system:
    Fixed-length types (A-K): Each has a specific byte length and decoder
    Variable-length types (L, M, LVAR): Length determined by LVAR byte or context

    DataType uses 32-bit flag encoding to support type validation:
    - DIF specifies source type (e.g., B_4 = 32-bit integer from DIF)
    - VIF specifies allowed target types (e.g., F_4|I_6|J_3 for datetime)
    - Validation: dif_type & vif_allowed_types returns matched type

Reference: EN 13757-3:2018
    - Annex A: Data types and encoding
    - Table 4 (page 13): Data type codes
    - Table 5 (page 13): LVAR interpretation
"""

from __future__ import annotations

import struct
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, NamedTuple, Self

from .value import BooleanArrayValue, FloatValue, IntegerValue, StringValue, TemporalValue, Value

# =============================================================================
# Numeric Data Type Decoders
# =============================================================================


def _decode_type_a(data: bytes) -> IntegerValue:
    """Decode Type A: Unsigned BCD (Binary Coded Decimal).

    Each nibble (4 bits) represents a decimal digit (0-9).
    Bytes are in little-endian order (least significant digit first).

    Special values:
        - Nibbles A-E: Invalid/error marker (returns None)
        - Nibble F in MSB position: Negative number marker

    Reference: EN 13757-3:2018, Annex A, Table A.1; Annex B, Table 4

    Args:
        data: Raw bytes in BCD encoding (little-endian)

    Returns:
        Decoded integer (can be negative), or None if invalid BCD digits found
    """
    value = int.from_bytes(data, byteorder="little")

    result = 0
    multiplier = 1

    while value > 0:
        digit = value & 0x0F
        value >>= 4

        if digit > 9:
            if value == 0 and digit == 0x0F:
                result = -result
                break

            return IntegerValue(False)

        result += digit * multiplier
        multiplier *= 10

    return IntegerValue(True, result)


def _decode_type_b(data: bytes) -> IntegerValue:
    """Decode Type B: Signed binary integer (two's complement).

    Bytes are in little-endian order.
    The most negative value for the given bit width is reserved as an invalid marker.

    Two's complement representation:
    - MSB (bit 7/15/31/63) is the sign bit (0=positive, 1=negative)
    - Negative values use two's complement encoding
    - Invalid marker: -2^(bits-1) where bits = len(data) * 8
      Used to signal sensor errors, overflow, or uninitialized values

    Reference: EN 13757-3:2018, Annex A, Table A.2, Table 4

    Args:
        data: Raw bytes in little-endian order

    Returns:
        Decoded signed integer, or None if value is the invalid marker
        (e.g., -128 for 1 byte, -32768 for 2 bytes)
    """
    value = int.from_bytes(data, byteorder="little", signed=True)

    if value == -(1 << (len(data) * 8 - 1)):
        return IntegerValue(False)

    return IntegerValue(True, value)


def _decode_type_c(data: bytes) -> IntegerValue:
    """Decode Type C: Unsigned binary integer.

    Bytes are in little-endian order.
    The maximum value for the given bit width is reserved as an invalid marker.

    Invalid marker: 2^bits - 1 where bits = len(data) * 8
    Used to signal sensor errors, overflow, or uninitialized values
    (e.g., 0xFF for 1 byte, 0xFFFF for 2 bytes)

    Reference: EN 13757-3:2018, Annex A, Table A.3, Table 4

    Args:
        data: Raw bytes in little-endian order

    Returns:
        Decoded unsigned integer, or None if value is the invalid marker
    """
    value = int.from_bytes(data, byteorder="little")

    if value == (1 << (len(data) * 8)) - 1:
        return IntegerValue(False)

    return IntegerValue(True, value)


def _decode_type_h(data: bytes) -> FloatValue:
    """Decode Type H: IEEE 754 floating point (4 bytes).

    Bytes are in little-endian order.
    NaN (Not a Number) is reserved as an invalid marker, used to signal
    sensor errors, out of range, or uninitialized values.

    Reference: EN 13757-3:2018, Annex A, Table A.7

    Args:
        data: Raw bytes (4 bytes)

    Returns:
        Decoded floating point value, or None if value is NaN (invalid marker)

    Raises:
        ValueError: If data is not exactly 4 bytes
    """
    if len(data) != 4:
        raise ValueError(f"Invalid data length for float: {len(data)} bytes (expected 4)")

    value: float = struct.unpack("<f", data)[0]

    # Check for NaN (invalid marker)
    # NaN is the only value where x != x is True (IEEE 754 standard)
    if value != value:
        return FloatValue(False)

    return FloatValue(True, value)


# =============================================================================
# Boolean/Bit Array Data Type Decoder
# =============================================================================


def _decode_type_d(data: bytes) -> BooleanArrayValue:
    """Decode Type D: Boolean bit array.

    Each bit represents a boolean value (0=False, 1=True).
    Bit 0 is LSB of first byte.

    Reference: EN 13757-3:2018, Annex A, Table A.4, Table 4

    Args:
        data: Raw bytes

    Returns:
        List of boolean values (one per bit)
    """
    bits: list[bool] = []
    for byte_val in data:
        for bit_pos in range(8):
            bits.append(bool((byte_val >> bit_pos) & 1))

    return BooleanArrayValue(True, tuple(bits))


# =============================================================================
# Date/Time Data Type Decoders
# =============================================================================


def _decode_type_g(data: bytes) -> TemporalValue:
    """Decode Type G: Date CP16 (2 bytes).

    Encodes date with support for recurring patterns (every day/month/year).
    Year is offset from 2000 (0-99 for years 2000-2099).

    Special values:
        - 0xFFFF: Invalid (returns None)
        - day=0, month=15, year=127: Recurring patterns

    Reference: EN 13757-3:2018, Annex A, Table A.6

    Args:
        data: Raw bytes (2 bytes, little-endian)

    Returns:
        Tuple (year, month, day) or None if invalid

    Raises:
        ValueError: If data is not 2 bytes or contains invalid date values
    """
    if len(data) != 2:
        raise ValueError(f"Invalid data length for date: {len(data)} bytes (expected 2)")

    if data[0] == 0b11111111 and data[1] == 0b11111111:
        return TemporalValue(False)

    day = data[0] & 0b00011111  # Bits 0-4
    month = data[1] & 0b00001111  # Bits 5-8
    year = ((data[1] >> 1) & 0b01111000) | (data[0] >> 5)  # Bits 12-15 and 5-7

    # Validate month (15 = "every month" is allowed)
    if month != 15 and not 1 <= month <= 12:
        raise ValueError(f"Invalid month: {month}")

    # Validate year (127 = "every year" is allowed)
    if year != 127 and not 0 <= year <= 99:
        raise ValueError(f"Invalid year: {year}")

    return TemporalValue(True)  # TODO Add all values to TemporalValue


def _decode_type_f(data: bytes) -> TemporalValue:
    """Decode Type F: Date and Time CP32 (4 bytes).

    Encodes date, time, century, and summer time flag with support for
    recurring patterns (every minute/hour/day/month/year).
    Year: 1900 + 100*hundred_year + year (range 1900-2299).

    Special values:
        - IV bit=1: Invalid (returns None)
        - minute=63, hour=31, day=0, month=15, year=127: Recurring patterns

    Reference: EN 13757-3:2018, Annex A, Table A.5

    Args:
        data: Raw bytes (4 bytes, little-endian)

    Returns:
        Tuple (hundred_year, year, month, day, hour, minute, summertime) or None if invalid

    Raises:
        ValueError: If data is not 4 bytes or contains invalid time/date values
    """
    if len(data) != 4:
        raise ValueError(f"Invalid data length for datetime: {len(data)} bytes (expected 4)")

    # Check invalid flag early (bit 7 of byte 0)
    if data[0] & 0b10000000:
        return TemporalValue(False)

    minute = data[0] & 0b00111111  # Bits 0-5
    hour = data[1] & 0b00011111  # Bits 0-4 of byte 1 (bits 8-12 of 32-bit)
    hundred_year = (data[1] >> 5) & 0b00000011  # Bits 5-6 of byte 1 (bits 13-14 of 32-bit)
    summertime = bool(data[1] & 0b10000000)  # Bit 7 of byte 1 (bit 15 of 32-bit)
    day = data[2] & 0b00011111  # Bits 0-4 of byte 2 (bits 16-20 of 32-bit)
    month = data[3] & 0b00001111  # Bits 0-3 of byte 3 (bits 24-27 of 32-bit)
    year = ((data[3] >> 1) & 0b01111000) | (data[2] >> 5)  # Bits 5-7 of byte 2 and 4-7 of byte 3

    if minute != 63 and not 0 <= minute <= 59:
        raise ValueError(f"Invalid minute: {minute}")

    if hour != 31 and not 0 <= hour <= 23:
        raise ValueError(f"Invalid hour: {hour}")

    if month != 15 and not 1 <= month <= 12:
        raise ValueError(f"Invalid month: {month}")

    if year != 127 and not 0 <= year <= 99:
        raise ValueError(f"Invalid year: {year}")

    return TemporalValue(True)  # TODO Add all values to TemporalValue


def _decode_type_j(data: bytes) -> TemporalValue:
    """Decode Type J: Time CP24 (3 bytes).

    Encodes time with support for recurring patterns (every second/minute/hour).

    Special values:
        - 0xFFFFFF: Invalid (returns None)
        - second=63, minute=63, hour=31: Recurring patterns

    Reference: EN 13757-3:2018, Annex A, Table A.9

    Args:
        data: Raw bytes (3 bytes, little-endian)

    Returns:
        Tuple (hour, minute, second) or None if invalid

    Raises:
        ValueError: If data is not 3 bytes or contains invalid time values
    """
    if len(data) != 3:
        raise ValueError(f"Invalid data length for time: {len(data)} bytes (expected 3)")

    # Check for invalid marker (0xFFFFFF)
    if data[0] == 0b11111111 and data[1] == 0b11111111 and data[2] == 0b11111111:
        return TemporalValue(False)

    second = data[0]  # Bits 0-5 (bits 6-7 must be 0)
    minute = data[1]  # Bits 0-5 of byte 1, bits 8-13 of 24-bit (bits 6-7 must be 0)
    hour = data[2]  # Bits 0-4 of byte 2, bits 16-20 of 24-bit (bits 5-7 must be 0)

    if second != 63 and not 0 <= second <= 59:
        raise ValueError(f"Invalid second: {second}")

    if minute != 63 and not 0 <= minute <= 59:
        raise ValueError(f"Invalid minute: {minute}")

    if hour != 31 and not 0 <= hour <= 23:
        raise ValueError(f"Invalid hour: {hour}")

    return TemporalValue(True)  # TODO Add all values to TemporalValue


def _decode_type_i(data: bytes) -> TemporalValue:
    """Decode Type I: Date and Time CP48 (6 bytes).

    Encodes full date/time with metadata (summer time, leap year, day of week, week number).
    Supports recurring patterns and "not specified" values. Year offset from 2000.
    Summertime deviation: -3 to +3 hours.

    Special values:
        - IV bit=1: Invalid (returns None)
        - second=63, minute=63, hour=31: Recurring patterns
        - day=0, month=0, year=127, day_of_week=0, week=0: Not specified

    Reference: EN 13757-3:2018, Annex A, Table A.8

    Args:
        data: Raw bytes (6 bytes, little-endian)

    Returns:
        Tuple (second, minute, hour, day, month, year, day_of_week, week, summertime, leap_year, summertime_deviation) or None if invalid

    Raises:
        ValueError: If data is not 6 bytes or contains invalid values
    """
    if len(data) != 6:
        raise ValueError(f"Invalid data length for datetime: {len(data)} bytes (expected 6)")

    # Check invalid flag early (bit 15 = bit 7 of byte 1)
    if data[1] & 0b10000000:
        return TemporalValue(False)

    second = data[0] & 0b00111111  # Bits 0-5
    summertime = bool(data[0] & 0b01000000)  # Bit 6
    leap_year = bool(data[0] & 0b10000000)  # Bit 7
    minute = data[1] & 0b00111111  # Bits 0-5 of byte 1 (bits 8-13 of 48-bit)
    summertime_sign = bool(data[1] & 0b01000000)  # Bit 6 of byte 1 (bit 14 of 48-bit)
    # Bit 7 of byte 1 is IV (already checked)
    hour = data[2] & 0b00011111  # Bits 0-4 of byte 2 (bits 16-20 of 48-bit)
    day_of_week = (data[2] >> 5) & 0b00000111  # Bits 5-7 of byte 2 (bits 21-23 of 48-bit)
    day = data[3] & 0b00011111  # Bits 0-4 of byte 3 (bits 24-28 of 48-bit)
    year = ((data[4] >> 4) << 3) | (data[3] >> 5)  # Bits 5-7 of byte 3 and 4-7 of byte 4
    month = data[4] & 0b00001111  # Bits 0-3 of byte 4 (bits 32-35 of 48-bit)
    week = data[5] & 0b00111111  # Bits 0-5 of byte 5 (bits 40-45 of 48-bit)
    summertime_magnitude = (data[5] >> 6) & 0b00000011  # Bits 6-7 of byte 5 (bits 46-47 of 48-bit)

    summertime_deviation = summertime_magnitude if summertime_sign else -summertime_magnitude

    if second != 63 and not 0 <= second <= 59:
        raise ValueError(f"Invalid second: {second}")

    if minute != 63 and not 0 <= minute <= 59:
        raise ValueError(f"Invalid minute: {minute}")

    if hour != 31 and not 0 <= hour <= 23:
        raise ValueError(f"Invalid hour: {hour}")

    if month != 0 and not 1 <= month <= 12:
        raise ValueError(f"Invalid month: {month}")

    if year != 127 and not 0 <= year <= 99:
        raise ValueError(f"Invalid year: {year}")

    if week != 0 and not 1 <= week <= 53:
        raise ValueError(f"Invalid week: {week}")

    return TemporalValue(True)  # TODO Add all values to TemporalValue


# =============================================================================
# Special Data Type Decoders
# =============================================================================


def _decode_type_k(data: bytes) -> Value:  # TODO Implement decoder
    """Decode Type K: Daylight savings time change (4 bytes).

    Encodes information about daylight savings time transitions including
    date and time of the change, and the time adjustment amount.

    Reference: EN 13757-3:2018, Annex A

    Args:
        data: Raw bytes (4 bytes)

    Returns:
        Decoded daylight savings information

    Raises:
        NotImplementedError: Decoder not yet implemented
    """
    raise NotImplementedError("Type K decoder not implemented yet")


def _decode_type_l(data: bytes) -> Value:  # TODO Implement decoder
    """Decode Type L: Listening window management (variable length).

    Encodes parameters for wireless M-Bus listening window configuration
    including timing information for optimized communication scheduling.

    Reference: EN 13757-3:2018, Annex A

    Args:
        data: Raw bytes (variable length)

    Returns:
        Decoded listening window parameters

    Raises:
        NotImplementedError: Decoder not yet implemented
    """
    raise NotImplementedError("Type L decoder not implemented yet")


def _decode_type_m(data: bytes) -> Value:  # TODO Implement decoder
    """Decode Type M: Date/Time or duration (variable length).

    Encodes either absolute date/time values or duration/time intervals
    with flexible format depending on the VIF specification.

    Reference: EN 13757-3:2018, Annex A

    Args:
        data: Raw bytes (variable length)

    Returns:
        Decoded date/time or duration value

    Raises:
        NotImplementedError: Decoder not yet implemented
    """
    raise NotImplementedError("Type M decoder not implemented yet")


# =============================================================================
# LVAR Decoders
# =============================================================================


def _decode_lvar_text_8859_1(data: bytes) -> StringValue:
    """Decode text string using ISO/IEC 8859-1 (Latin-1) encoding.

    Used for LVAR codes 0x00-0xBF. Supports ASCII (0x00-0x7F) and extended
    Latin characters (0x80-0xFF). Each byte represents one character.
    Bytes are in natural order (first byte = first character).

    Reference: EN 13757-3:2018, Table 5 (LVAR range 0x00-0xBF)

    Args:
        data: Raw bytes to decode

    Returns:
        Decoded text string
    """
    if not data:
        return StringValue(True, "")

    return StringValue(True, data.decode("iso-8859-1"))


def _decode_lvar_positive_bcd(data: bytes) -> IntegerValue:
    """Decode positive BCD number from LVAR data.

    Used for LVAR codes 0xC0-0xC9. Length = (LVAR - 0xC0) bytes.

    Reference: EN 13757-3:2018, Table 5 (LVAR range 0xC0-0xC9)

    Args:
        data: Raw bytes in BCD format (little-endian)

    Returns:
        Decoded positive integer, or None if invalid BCD digits

    Raises:
        ValueError: If BCD value is negative
    """
    bcd_value = _decode_type_a(data)

    if not bcd_value.is_valid:
        return bcd_value

    if bcd_value < 0:
        raise ValueError(f"Expected positive BCD number, got negative value: {bcd_value}")

    return bcd_value


def _decode_lvar_negative_bcd(data: bytes) -> IntegerValue:
    """Decode negative BCD number from LVAR data.

    Used for LVAR codes 0xD0-0xD9. Length = (LVAR - 0xD0) bytes.
    Decodes BCD as positive then negates it.

    Reference: EN 13757-3:2018, Table 5 (LVAR range 0xD0-0xD9)

    Args:
        data: Raw bytes in BCD format (little-endian, without sign marker)

    Returns:
        Decoded negative integer, or None if invalid BCD digits

    Raises:
        ValueError: If BCD value has F-nibble sign marker
    """
    bcd_value = _decode_type_a(data)

    if not bcd_value.is_valid:
        return bcd_value

    if bcd_value < 0:
        raise ValueError(f"LVAR negative BCD should not have F-nibble sign marker, got BCD value: {bcd_value}")

    return IntegerValue(True, -bcd_value)


def _decode_lvar_binary(data: bytes) -> IntegerValue:
    """Decode unsigned binary integer from LVAR data.

    Used for LVAR codes 0xE0-0xEF, 0xF0-0xF6 with variable length.
    Maximum value (all 0xFF) is reserved as invalid marker.

    Reference: EN 13757-3:2018, Table 5 (LVAR ranges 0xE0-0xF6)

    Args:
        data: Raw bytes in little-endian order

    Returns:
        Decoded unsigned integer, or None if invalid (all 0xFF)
    """
    return _decode_type_c(data)


class _LVARDescriptor(NamedTuple):
    """Descriptor for LVAR-based variable length data interpretation.

    Reference: EN 13757-3:2018, Table 5 — LVAR interpretation
    """

    code_range: range  # Range of LVAR codes this descriptor handles
    length_calculator: Callable[[int], int]  # Takes LVAR byte value, returns data length in bytes
    decoder: Callable[[bytes], Any]  # Decoder function that takes data bytes and returns decoded value


class LVARType(Enum):
    """LVAR-based data types for variable-length data.

    The LVAR byte determines both data type and length of following data.
    Each member contains code range, length calculator, and decoder function.

    Reference: EN 13757-3:2018, Table 5 (LVAR interpretation)
    """

    # 0x00-0xBF: 8-bit text string (ISO/IEC 8859-1)
    # Length: LVAR value directly (0 to 191 characters)
    TEXT_STRING = _LVARDescriptor(
        code_range=range(0x00, 0xC0),  # 0x00-0xBF (0-191)
        length_calculator=lambda lvar: lvar,  # LVAR value = number of bytes
        decoder=_decode_lvar_text_8859_1,
    )

    # 0xC0-0xC9: Positive BCD number
    # Length: (LVAR - 0xC0) bytes for (LVAR - 0xC0)*2 digits (0 to 18 digits)
    POSITIVE_BCD = _LVARDescriptor(
        code_range=range(0xC0, 0xCA),  # 0xC0-0xC9 (192-201)
        length_calculator=lambda lvar: lvar - 0xC0,  # 0 to 9 bytes
        decoder=_decode_lvar_positive_bcd,
    )

    # 0xD0-0xD9: Negative BCD number
    # Length: (LVAR - 0xD0) bytes for (LVAR - 0xD0)*2 digits (0 to 18 digits)
    NEGATIVE_BCD = _LVARDescriptor(
        code_range=range(0xD0, 0xDA),  # 0xD0-0xD9 (208-217)
        length_calculator=lambda lvar: lvar - 0xD0,  # 0 to 9 bytes
        decoder=_decode_lvar_negative_bcd,
    )

    # 0xE0-0xEF: Binary number
    # Length: (LVAR - 0xE0) bytes (0 to 15 bytes)
    BINARY_SMALL = _LVARDescriptor(
        code_range=range(0xE0, 0xF0),  # 0xE0-0xEF (224-239)
        length_calculator=lambda lvar: lvar - 0xE0,  # 0 to 15 bytes
        decoder=_decode_lvar_binary,
    )

    # 0xF0-0xF4: Large binary numbers
    # Length: 4*(LVAR - 0xEC) bytes (16, 20, 24, 28, 32 bytes)
    BINARY_LARGE = _LVARDescriptor(
        code_range=range(0xF0, 0xF5),  # 0xF0-0xF4 (240-244)
        length_calculator=lambda lvar: 4 * (lvar - 0xEC),  # 16, 20, 24, 28, 32 bytes
        decoder=_decode_lvar_binary,
    )

    # 0xF5: Binary number, fixed 48 bytes
    BINARY_48 = _LVARDescriptor(
        code_range=range(0xF5, 0xF6),  # 0xF5 only (245)
        length_calculator=lambda _: 48,  # Fixed 48 bytes
        decoder=_decode_lvar_binary,
    )

    # 0xF6: Binary number, fixed 64 bytes
    BINARY_64 = _LVARDescriptor(
        code_range=range(0xF6, 0xF7),  # 0xF6 only (246)
        length_calculator=lambda _: 64,  # Fixed 64 bytes
        decoder=_decode_lvar_binary,
    )


class DataType(Enum):
    """M-Bus data types with 32-bit flag encoding for validation.

    Each concrete type (A_1, B_2, etc.) has a unique bit position, enabling
    type validation through bitwise operations between DIF and VIF rules.

    32-bit encoding (one bit per concrete type):
        - Bits 0-4:   A_1, A_2, A_3, A_4, A_6
        - Bits 5-10:  B_1, B_2, B_3, B_4, B_6, B_8
        - Bits 11-16: C_1, C_2, C_3, C_4, C_6, C_8
        - Bits 17-22: D_1, D_2, D_3, D_4, D_6, D_8
        - Bits 23-30: F_4, G_2, H_4, I_6, J_3, K_4, L, M
        - Bit 31:     LVAR

    Validation: dif.data_type & vif.allowed_types returns matched type or None

    Special member:
        - ANY: All bits set (accepts any type), may not be used in | or & operations

    Each member has length (bytes) and decoder (function) properties.

    Reference: EN 13757-3:2018, Annex A, Table 4
    """

    def __new__(cls, value: int | None, *args: Any) -> Self:
        """Create DataType member with length and decoder metadata.

        Args:
            value: Bit pattern for this type
        """
        obj = object.__new__(cls)
        obj._value_ = value
        return obj

    def __init__(
        self, value: int | None, decoder: Callable[[bytes], Value] | None = None, length: int | None = None
    ) -> None:
        """Initialize DataType member with length and decoder metadata.

        Args:
            value: Bit pattern for this type (only used in __new__)
            length: Byte length (None for variable length)
            decoder: Decoding function (None for LVAR/ANY/pseudo-members)
        """
        self._length = length
        self._decoder = decoder

    @property
    def length(self) -> int | None:
        """Byte length for this data type (None for variable length)."""
        return self._length if self.name in DataType.__members__ else None

    @property
    def decoder(self) -> Callable[[bytes], Any] | None:
        """Decoder function for this data type (None for LVAR/ANY/pseudo-members)."""
        return self._decoder if self.name in DataType.__members__ else None

    NONE = 0b100000000000  # No data

    # ==========================================================================
    # Type A: Unsigned BCD (no conversions)
    # ==========================================================================
    A_1 = 0b0000001000000000001, _decode_type_a, 1  # Bit 0, 1 byte
    A_2 = 0b0000010000000000001, _decode_type_a, 2  # Bit 1, 2 bytes
    A_3 = 0b0000100000000000001, _decode_type_a, 3  # Bit 2, 3 bytes
    A_4 = 0b0001000000000000001, _decode_type_a, 4  # Bit 3, 4 bytes
    A_6 = 0b0010000000000000001, _decode_type_a, 6  # Bit 4, 6 bytes

    # ==========================================================================
    # Type B: Signed integer (no conversions - DIF table defines conversions)
    # ==========================================================================
    B_1 = 0b0000001000000000110, _decode_type_b, 1  # Bit 5, 1 byte
    B_2 = 0b0000010000000000110, _decode_type_b, 2  # Bit 6, 2 bytes
    B_3 = 0b0000100000000000110, _decode_type_b, 3  # Bit 7, 3 bytes
    B_4 = 0b0001000000000000110, _decode_type_b, 4  # Bit 8, 4 bytes
    B_6 = 0b0010000000000000110, _decode_type_b, 6  # Bit 9, 6 bytes
    B_8 = 0b0100000000000000110, _decode_type_b, 8  # Bit 10, 8 bytes

    # ==========================================================================
    # Type C: Unsigned integer (no conversions)
    # ==========================================================================
    C_1 = 0b0000001000000000010, _decode_type_c, 1  # Bit 11, 1 byte
    C_2 = 0b0000010000000000010, _decode_type_c, 2  # Bit 12, 2 bytes
    C_3 = 0b0000100000000000010, _decode_type_c, 3  # Bit 13, 3 bytes
    C_4 = 0b0001000000000000010, _decode_type_c, 4  # Bit 14, 4 bytes
    C_6 = 0b0010000000000000010, _decode_type_c, 6  # Bit 15, 6 bytes
    C_8 = 0b0100000000000000010, _decode_type_c, 8  # Bit 16, 8 bytes

    # ==========================================================================
    # Type D: Boolean/bit array (no conversions)
    # ==========================================================================
    D_1 = 0b0000001000000000100, _decode_type_d, 1  # Bit 17, 1 byte
    D_2 = 0b0000010000000000100, _decode_type_d, 2  # Bit 18, 2 bytes
    D_3 = 0b0000100000000000100, _decode_type_d, 3  # Bit 19, 3 bytes
    D_4 = 0b0001000000000000100, _decode_type_d, 4  # Bit 20, 4 bytes
    D_6 = 0b0010000000000000100, _decode_type_d, 6  # Bit 21, 6 bytes
    D_8 = 0b0100000000000000100, _decode_type_d, 8  # Bit 22, 8 bytes

    # ==========================================================================
    # Type F: Date/Time CP32 (no conversions)
    # ==========================================================================
    F_4 = 0b0001000000000001000, _decode_type_f, 4  # Bit 23, 4 bytes

    # ==========================================================================
    # Type G: Date CP16 (no conversions)
    # ==========================================================================
    G_2 = 0b0000010000000010000, _decode_type_g, 2  # Bit 24, 2 bytes

    # ==========================================================================
    # Type H: Floating point IEEE 754 (no conversions)
    # ==========================================================================
    H_4 = 0b0001000000000100000, _decode_type_h, 4  # Bit 25, 4 bytes

    # ==========================================================================
    # Type I: Date/Time CP48 (no conversions)
    # ==========================================================================
    I_6 = 0b0010000000001000000, _decode_type_i, 6  # Bit 26, 6 bytes

    # ==========================================================================
    # Type J: Time CP24 (no conversions)
    # ==========================================================================
    J_3 = 0b0000100000010000000, _decode_type_j, 3  # Bit 27, 3 bytes

    # ==========================================================================
    # Type K: Daylight savings (no conversions)
    # ==========================================================================
    K_4 = 0b0001000000100000000, _decode_type_k, 4  # Bit 28, 4 bytes

    # ==========================================================================
    # Type L: Listening window management (variable length with decoder)
    # ==========================================================================
    L = 0b1000000001000000000, _decode_type_l  # Bit 29, variable length

    # ==========================================================================
    # Type M: Date/Time or duration (variable length with decoder)
    # ==========================================================================
    M = 0b1000000010000000000, _decode_type_m  # Bit 30, variable length

    # ==========================================================================
    # LVAR: Variable length data (no conversions - DIF table defines conversions)
    # ==========================================================================
    LVAR = 0b1000000011000000000  # Bit 31, variable, no decoder


class DataRules:
    """Data type validation rules for matching DIF and VIF specifications.

    DataRules provides a factory mechanism to determine the concrete DataType
    from DIF and VIF type specifications using bitwise operations:
    - DIF specifies supported types (e.g., B_4 | C_4 | D_4 for 4-byte data)
    - VIF specifies required types (e.g., B_4 for signed integer values)
    - DataRules(supports, requires) returns the matched concrete type

    The matching algorithm:
        1. For each required type bit pattern
        2. Perform bitwise AND with supported types
        3. Return first match found in DataType registry
        4. Raise ValueError if no valid match exists

    Example:
        supports = DataRules.Supports.BCDFK_4  # DIF: 4-byte data
        requires = DataRules.Requires.DEFAULT_ABHLVAR  # VIF: numeric values
        data_type = DataRules(supports, requires)  # Returns B_4 or C_4

    Reference: EN 13757-3:2018, Table 4 (DIF/VIF type matching)
    """

    def __new__(cls, supports: Supports, requires: Requires) -> DataType | None:  # type: ignore[misc]
        for required_value in requires.value:
            final_value = supports.value & required_value

            if final_value in DataType._value2member_map_:
                return DataType(final_value)

            if not requires.any_valid:
                break

        raise ValueError("No valid DataType found for given Supports and Requires")

    class Supports(Enum):
        """DIF-side type support specification.

        Each member represents the set of data types supported by a specific
        DIF encoding. The bit pattern includes all concrete types that can be
        used for that DIF code.

        Used with DataRules to match DIF supported types against VIF required types.

        Reference: EN 13757-3:2018, Table 4 (DIF data field encoding)
        """

        NONE = 0b0000000100000000000  # No data

        BCD_1 = 0b0000001000000000110  # B_1, C_1, D_1

        BCDG_2 = 0b0000010000000010110  # B_2, C_2, D_2, G_2

        BCDJ_3 = 0b0000100000010000110  # B_3, C_3, D_3, J_3

        BCDFK_4 = 0b0001000000100001110  # B_4, C_4, D_4, F_4, K_4

        H_4 = 0b0001000000000100000  # H_4

        BCDI_6 = 0b0010000000001000110  # B_6, C_6, D_6, I_6

        BCD_8 = 0b0100000000000000110  # B_8, C_8, D_8

        A_1 = 0b0000001000000000001  # A_1

        A_2 = 0b0000010000000000001  # A_2

        A_3 = 0b0000100000000000001  # A_3

        A_4 = 0b0001000000000000001  # A_4

        LMLVAR = 0b1000000011000000000  # L, M, LVAR

        A_6 = 0b0010000000000000001  # A_6

    class Requires(Enum):
        """VIF-side type requirement specification.

        Each member represents the set of data types required or allowed by a
        specific VIF encoding. The bit pattern includes all concrete types that
        are valid for that VIF code.

        Members can be combined using the OR operator (|) to create composite
        requirements that accept multiple type alternatives.

        Special handling:
            - ANY: Accepts all data types (wildcard match)
            - Members can be combined: TEMPORAL_FIJM | TEMPORAL_G

        Used with DataRules to match VIF required types against DIF supported types.

        Reference: EN 13757-3:2018, Table 4 and VIF tables
        """

        _value_: tuple[int, ...]

        def __init__(self, value: int) -> None:
            self.any_valid = value == 0b1111111111000100111
            self._value_ = (value,)

        def __or__(self, other: Self) -> DataRules.Requires:
            assert isinstance(other, DataRules.Requires), "Can only combine Requires with Requires"

            assert other in DataRules.Requires, "Can only combine Requires with defined Requires members"

            obj = object.__new__(DataRules.Requires)

            if other is DataRules.Requires.ANY:
                obj.any_valid = other.any_valid
                obj._value_ = self._value_ + other._value_
            else:
                obj.any_valid = self.any_valid
                obj._value_ = other._value_ + self._value_

            return obj

        ANY = 0b1111111111000100111  # Any type allowed.  also no data

        NONE = 0b0000000100000000000  # No data

        DEFAULT_ABHLVAR = 0b1111111011000100111  # A_1 - A_6, B_1 - B_8, H_4, LVAR

        ADDRESS_C = 0b0110001000000000010  # C_1, C_6, C_8

        UNSIGNED_C = 0b0111111000000000010  # C_1 - C_8

        BOOLEAN_D = 0b0111111000000000100  # D_1 - D_8

        TEMPORAL_G = 0b0000010000000010000  # G_2

        TEMPORAL_FIJM = 0b1011100010011001000  # F_4, I_6, J_3, M

        TEMPORAL_FGIJM = 0b1011110010011011000  # F_4, G_2, I_6, J_3, M

        TEMPORAL_K = 0b0001000000100000000  # K_4

        TEMPORAL_L = 0b1000000001000000000  # L


class Data:
    """Decoded M-Bus data with type information.

    Represents a decoded data record containing the decoded value with validity
    information. Handles both fixed-length types (A-K) and variable-length types
    (LVAR) with automatic length calculation, validation, and decoding.

    The class performs complete data decoding:
    - Fixed-length types: Direct decoding using DataType.decoder
    - LVAR types: LVAR byte parsing, length calculation, and type-specific decoding
    - Validation: Length verification and invalid marker detection

    Attributes:
        decoded_value: The decoded value with validity flag and type-specific data
            (IntegerValue, FloatValue, StringValue, BooleanArrayValue, or TemporalValue)

    Reference: EN 13757-3:2018, Annex A
    """

    decoded_value: Value

    def __init__(
        self,
        data_bytes: bytes,
        data_type: DataType,
        lvar_type: LVARType | None,
    ) -> None:
        """Initialize Data with raw bytes and type information.

        Args:
            data_bytes: Raw bytes to decode. For LVAR types, this includes the LVAR byte + actual data.
            data_type: M-Bus data type (from DataType enum)
            lvar_type: LVAR type (required if data_type is DataType.LVAR)

        Raises:
            ValueError: If data length doesn't match expected length for fixed-length types
            ValueError: If data length doesn't match LVAR expected length
            ValueError: If lvar_type is missing for DataType.LVAR
            ValueError: If LVAR code in data_bytes is not valid for lvar_type
        """
        if data_type is DataType.NONE:
            raise ValueError("Data with DataType.NONE is not valid")

        if len(data_bytes) == 0:
            raise ValueError("data_bytes cannot be empty")

        decoder = data_type.decoder

        data_length = data_type.length

        if data_length is None:
            if lvar_type is None:
                raise ValueError(f"lvar_type must be provided for {data_type.name}")

            lvar_code: int = data_bytes[0]

            if lvar_code not in lvar_type.value.code_range:
                raise ValueError(
                    f"LVAR code 0x{lvar_code:02X} is not valid for {lvar_type.name} (expected range: 0x{lvar_type.value.code_range.start:02X}-0x{lvar_type.value.code_range.stop - 1:02X})"
                )

            data_bytes = data_bytes[1:]

            data_length = lvar_type.value.length_calculator(lvar_code)

            if decoder is None:
                decoder = lvar_type.value.decoder

        if len(data_bytes) != data_length:
            raise ValueError(f"Expected {data_length} bytes for {data_type.name}, got {len(data_bytes)} bytes")

        # At this point, decoder is defined since all non-LVAR types have decoders and
        # the LVAR path assigns decoder from lvar_type if not already set from data_type.
        assert decoder is not None

        decoded_value = decoder(data_bytes)

        self.decoded_value = decoded_value

    @staticmethod
    async def from_bytes_async(
        data_type: DataType,
        get_next_bytes: Callable[[int], Awaitable[bytes]],
    ) -> Data:
        if data_type is DataType.NONE:
            raise ValueError("Data with DataType.NONE is not valid")

        data_length: int | None = data_type.length

        data_bytes: bytearray = bytearray()

        lvar_type: LVARType | None = None

        if data_length is None:
            lvar_bytes: bytes = await get_next_bytes(1)

            if len(lvar_bytes) != 1:
                raise ValueError("LVAR byte must be exactly 1 byte")

            data_bytes.extend(lvar_bytes)

            lvar_code: int = lvar_bytes[0]

            for lvar_member in LVARType:
                if lvar_code in lvar_member.value.code_range:
                    lvar_type = lvar_member
                    break
            else:
                raise ValueError(f"Unsupported LVAR code: 0x{lvar_code:02X}")

            data_length = lvar_type.value.length_calculator(lvar_code)

        if data_length > 0:
            data_bytes.extend(await get_next_bytes(data_length))

        return Data(bytes(data_bytes), data_type, lvar_type)
