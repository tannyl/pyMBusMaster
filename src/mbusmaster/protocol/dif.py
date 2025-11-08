"""DIF (Data Information Field) type system and interpretation logic.

This module implements the M-Bus DIF/DIFE field interpretation system according
to EN 13757-3:2018. It provides:

Classes:
    - DIF: Base class for Data Information Field (1 byte header)
    - DataDIF: DIF with data type and function information
    - SpecialDIF: DIF with special functions (manufacturer data, idle filler, etc.)
    - DIFE: Base class for Data Information Field Extension
    - DataDIFE: DIFE extending storage number, tariff, and subunit
    - FinalDIFE: Special DIFE (0x00) marking storage number as register number

The DIF/DIFE chain structure:
    DIF (1 byte) + optional DIFEs (0-10 bytes) + optional FinalDIFE (1 byte)

    The extension bit (bit 7) in each field indicates if more DIFE bytes follow.
    FinalDIFE is used for OBIS register number encoding (see section 6.3.5).

Reference: EN 13757-3:2018
    - Table 4 (page 13): Data field encoding
    - Table 6 (page 14): Special function codes
    - Table 7 (page 14): Function field encoding
    - Table 8 (page 14): DIFE encoding
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Flag, auto
from functools import lru_cache

from .common import CommunicationDirection
from .data import DataType
from .value import ValueFunction

# =============================================================================
# DIF Constants (EN 13757-3:2018)
# =============================================================================


DIF_EXTENSION_BIT_MASK = 0b10000000  # Bit 7: extension bit (more DIFE bytes follow)
DIF_FUNCTION_BIT_MASK = 0b00110000  # Bits 4-5: function

DIF_STORAGE_NUMBER_BIT_MASK = 0b01000000  # Bit 6: LSB of storage number
DIF_STORAGE_NUMBER_BIT_SHIFT = 6  # Bit position shift for storage number
DIF_STORAGE_NUMBER_BIT_LENGTH = 1  # Number of bits for storage number in DIF

DIFE_EXTENSION_BIT_MASK = 0b10000000  # Bit 7: extension bit (more DIFE bytes follow)

DIFE_MAXIMUM_CHAIN_LENGTH = 10  # Maximum number of chained DIFE bytes

DIFE_STORAGE_NUMBER_BIT_MASK = 0b00001111  # Bits 0-3: additional storage number bits in DIFE
DIFE_STORAGE_NUMBER_BIT_SHIFT = 0  # Bit position shift for storage number
DIFE_STORAGE_NUMBER_BIT_LENGTH = 4  # Number of bits for storage number in DIFE

DIFE_TARIFF_BIT_MASK = 0b00110000  # Bit 4-5: tariff number in DIFE
DIFE_TARIFF_BIT_SHIFT = 4  # Bit position shift for tariff number
DIFE_TARIFF_BIT_LENGTH = 2  # Number of bits for tariff number in DIFE

DIFE_SUBUNIT_BIT_MASK = 0b01000000  # Bit 6: subunit number in DIFE
DIFE_SUBUNIT_BIT_SHIFT = 6  # Bit position shift for subunit number
DIFE_SUBUNIT_BIT_LENGTH = 1  # Number of bits for subunit number in DIFE

DIFE_FINAL_CODE = 0b00000000  # Final DIFE code indicating storage number is register number

# =============================================================================
# DIF Type Classification
# =============================================================================


class DIFSpecialFunction(Flag):
    MANUFACTURER_DATA_HEADER = auto()
    MORE_RECORDS_FOLLOW = auto()
    IDLE_FILLER = auto()
    GLOBAL_READOUT = auto()


# =============================================================================
# DIF Descriptors
# =============================================================================


@dataclass(frozen=True, kw_only=True)
class _AbstractFieldDescriptor(ABC):
    code: int  # DIF byte value
    mask: int  # Bit mask for pattern matching

    direction: CommunicationDirection = CommunicationDirection.BIDIRECTIONAL


@dataclass(frozen=True, kw_only=True)
class _DataFieldDescriptor(_AbstractFieldDescriptor):
    mask: int = 0b00001111  # Bit mask for pattern matching

    readout_selection: bool = False  # Indicates if data field is a readout selection

    data_type: DataType | None = None  # Data type with length encoded (if applicable)


@dataclass(frozen=True, kw_only=True)
class _SpecialFieldDescriptor(_AbstractFieldDescriptor):
    mask: int = 0b11111111  # Bit mask for pattern matching

    function: DIFSpecialFunction  # Special function type


@dataclass(frozen=True, kw_only=True)
class _FunctionDescriptor:
    code: int
    type: ValueFunction


# =============================================================================
# DIF Lookup Tables (EN 13757-3:2018, Table 4 and 6)
# =============================================================================


_FieldTable: tuple[_AbstractFieldDescriptor, ...] = (
    # ==========================================================================
    # Data types (Data Field 0x00 - 0x0E): Table 4
    # ==========================================================================
    # No data (0x00)
    _DataFieldDescriptor(
        code=0b00000000,
    ),
    # 8 bit integer (0x01)
    _DataFieldDescriptor(
        code=0b00000001,
        data_type=DataType.B_1 | DataType.C_1 | DataType.D_1,  # Can be signed, unsigned, or boolean
    ),
    # 16 bit integer (0x02)
    _DataFieldDescriptor(
        code=0b00000010,
        data_type=DataType.B_2
        | DataType.C_2
        | DataType.D_2
        | DataType.G_2,  # Can be signed, unsigned, boolean, or date
    ),
    # 24 bit integer (0x03)
    _DataFieldDescriptor(
        code=0b00000011,
        data_type=DataType.B_3
        | DataType.C_3
        | DataType.D_3
        | DataType.J_3,  # Can be signed, unsigned, boolean, or time
    ),
    # 32 bit integer (0x04)
    _DataFieldDescriptor(
        code=0b00000100,
        data_type=DataType.B_4
        | DataType.C_4
        | DataType.D_4
        | DataType.F_4
        | DataType.K_4,  # Can be signed, unsigned, boolean, datetime, or DST
    ),
    # 32 bit real (0x05)
    _DataFieldDescriptor(
        code=0b00000101,
        data_type=DataType.H_4,  # Float only (no conversions)
    ),
    # 48 bit integer (0x06)
    _DataFieldDescriptor(
        code=0b00000110,
        data_type=DataType.B_6
        | DataType.C_6
        | DataType.D_6
        | DataType.I_6,  # Can be signed, unsigned, boolean, or full datetime
    ),
    # 64 bit integer (0x07)
    _DataFieldDescriptor(
        code=0b00000111,
        data_type=DataType.B_8 | DataType.C_8 | DataType.D_8,  # Can be signed, unsigned, or boolean
    ),
    # Selection for readout (0x08)
    _DataFieldDescriptor(
        code=0b00001000,
        direction=CommunicationDirection.MASTER_TO_SLAVE,
        readout_selection=True,
    ),
    # 2 digit BCD (0x09)
    _DataFieldDescriptor(
        code=0b00001001,
        data_type=DataType.A_1,
    ),
    # 4 digit BCD (0x0A)
    _DataFieldDescriptor(
        code=0b00001010,
        data_type=DataType.A_2,
    ),
    # 6 digit BCD (0x0B)
    _DataFieldDescriptor(
        code=0b00001011,
        data_type=DataType.A_3,
    ),
    # 8 digit BCD (0x0C)
    _DataFieldDescriptor(
        code=0b00001100,
        data_type=DataType.A_4,
    ),
    # Variable length (0x0D)
    _DataFieldDescriptor(
        code=0b00001101,
        data_type=DataType.LVAR | DataType.L | DataType.M,  # Can be LVAR, listening window, or duration
    ),
    # 12 digit BCD (0x0E)
    _DataFieldDescriptor(
        code=0b00001110,
        data_type=DataType.A_6,
    ),
    # ==========================================================================
    # Data Field 0x0F: Special functions (Table 6)
    # ==========================================================================
    # 0x0F: Manufacturer specific data follows
    _SpecialFieldDescriptor(
        code=0b00001111,
        function=DIFSpecialFunction.MANUFACTURER_DATA_HEADER,
    ),
    # 0x1F: More records follow in next datagram + manufacturer data
    _SpecialFieldDescriptor(
        code=0b00011111,
        function=DIFSpecialFunction.MANUFACTURER_DATA_HEADER | DIFSpecialFunction.MORE_RECORDS_FOLLOW,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # 0x2F: Idle filler (skip this byte)
    _SpecialFieldDescriptor(
        code=0b00101111,
        function=DIFSpecialFunction.IDLE_FILLER,
    ),
    # 0x7F: Global readout request
    _SpecialFieldDescriptor(
        code=0b01111111,
        function=DIFSpecialFunction.GLOBAL_READOUT,
        direction=CommunicationDirection.MASTER_TO_SLAVE,
    ),
)


_FunctionTable: tuple[_FunctionDescriptor, ...] = (
    # ==========================================================================
    # Function codes (Data Field 0x00 - 0x03): Table 7
    # ==========================================================================
    # Instantaneous value (0x00)
    _FunctionDescriptor(
        code=0b00000000,
        type=ValueFunction.INSTANTANEOUS,
    ),
    # Maximum value (0x01)
    _FunctionDescriptor(
        code=0b00010000,
        type=ValueFunction.MAXIMUM,
    ),
    # Minimum value (0x02)
    _FunctionDescriptor(
        code=0b00100000,
        type=ValueFunction.MINIMUM,
    ),
    # Value during error state (0x03)
    _FunctionDescriptor(
        code=0b00110000,
        type=ValueFunction.ERROR,
    ),
)

# =============================================================================
# DIF/DIFE Helper functions
# =============================================================================


@lru_cache(maxsize=32)
def _find_field_descriptor(direction: CommunicationDirection, field_code: int) -> _AbstractFieldDescriptor:
    """Find the matching field descriptor for a DIF/DIFE field code.

    Looks up the field code in the _FieldTable using bit masking to match
    patterns. Cached with LRU cache (max 32 entries) for performance.

    Args:
        direction: Communication direction to match
        field_code: The DIF byte value to look up

    Returns:
        The matching field descriptor (_DataFieldDescriptor or _SpecialFieldDescriptor)

    Raises:
        ValueError: If no matching descriptor is found
    """
    for field_descriptor in _FieldTable:
        if direction in field_descriptor.direction and (field_code & field_descriptor.mask) == field_descriptor.code:
            return field_descriptor

    raise ValueError(
        f"Field descriptor for DIF code 0x{field_code:02X} for direction {direction.name} not found in DIF table"
    )


# =============================================================================
# DIF/DIFE Classes - DIF/DIFE field interpretation
# =============================================================================


class DIF:
    """Base class for Data Information Field (DIF).

    The DIF is the first byte in a DIF/DIFE chain and specifies the data type,
    function, and optionally the first bit of the storage number.

    This class uses a factory pattern (__new__) to automatically instantiate
    the correct subclass (DataDIF or SpecialDIF) based on the field_code.

    Attributes:
        field_code: The DIF byte value (0x00-0xFF)
        direction: Communication direction (MASTER_TO_SLAVE or SLAVE_TO_MASTER)
        chain_position: Position in DIF/DIFE chain (0 for DIF)
        prev_field: Previous field in chain (None for DIF)
        next_field: Next DIFE in chain (None if last_field is True)
        last_field: True if extension bit is 0 (no more DIFE bytes follow)

    Reference: EN 13757-3:2018, section 6.3, Table 4
    """

    field_code: int

    direction: CommunicationDirection

    chain_position: int = 0
    prev_field: DIF | DIFE | None = None
    next_field: DIFE | None = None

    last_field: bool = True

    def __new__(cls, direction: CommunicationDirection, field_code: int) -> DIF:
        field_descriptor = _find_field_descriptor(direction, field_code)

        if isinstance(field_descriptor, _DataFieldDescriptor):
            return object.__new__(DataDIF)

        if isinstance(field_descriptor, _SpecialFieldDescriptor):
            return object.__new__(SpecialDIF)

        raise RuntimeError("DIF field descriptor type not recognized")

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        if direction is CommunicationDirection.BIDIRECTIONAL:
            raise ValueError("DIF/DIFE communication direction cannot be BIDIRECTIONAL")

        self.direction = direction

        self.field_code = field_code

    def create_next_dife(self, field_code: int) -> DIFE:
        """Create the next DIFE in the chain.

        Args:
            field_code: The DIFE byte value (0x00-0xFF)

        Returns:
            DIFE instance (DataDIFE or FinalDIFE based on field_code)

        Raises:
            ValueError: If this field is already marked as last_field
        """
        return DIFE(self.direction, field_code, self)

    @staticmethod
    async def from_bytes_async(
        direction: CommunicationDirection,
        get_next_bytes: Callable[[int], Awaitable[bytes]],
    ) -> tuple[DIF, *tuple[DIFE, ...]]:
        """Parse a complete DIF/DIFE chain from bytes asynchronously.

        Reads one DIF byte, then continues reading DIFE bytes as long as the
        extension bit (bit 7) is set in the current field.

        Args:
            direction: Communication direction for the DIF/DIFE chain
            get_next_bytes: Async function to read the next n bytes from stream

        Returns:
            Tuple of (DIF, *DIFEs) representing the complete chain

        Raises:
            ValueError: If byte reading fails or field descriptor not found
        """
        dif_bytes = await get_next_bytes(1)

        if len(dif_bytes) != 1:
            raise ValueError("Expected exactly one byte for DIF")

        dif: DIF = DIF(direction, dif_bytes[0])

        dife_list: list[DIFE] = []

        current_field: DIF = dif
        while not current_field.last_field:
            dife_bytes = await get_next_bytes(1)

            if len(dife_bytes) != 1:
                raise ValueError("Expected exactly one byte for DIFE")

            current_field = current_field.create_next_dife(dife_bytes[0])
            dife_list.append(current_field)

        return (dif, *dife_list)


class DataDIF(DIF):
    """Data Information Field for data records.

    DataDIF is used for regular data records and encodes:
    - Data type and length (bits 0-3)
    - Function (instantaneous, min, max, error) (bits 4-5)
    - Storage number LSB (bit 6)
    - Extension bit (bit 7)

    Attributes:
        data_type: The data type with length encoding (e.g., DataType.B_4 for 32-bit integer)
        readout_selection: True if this is a readout selection DIF (0x08)
        value_function: Function code (INSTANTANEOUS, MAXIMUM, MINIMUM, ERROR)
        storage_number: LSB of storage number (0 or 1 from DIF bit 6)

    Reference: EN 13757-3:2018, Table 4 (page 13)
    """

    data_type: DataType | None

    readout_selection: bool

    value_function: ValueFunction

    storage_number: int

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        super().__init__(direction, field_code)

        field_descriptor = _find_field_descriptor(self.direction, self.field_code)

        if not isinstance(field_descriptor, _DataFieldDescriptor):
            raise ValueError("Incorrect field descriptor type for DataDIF")

        self.readout_selection = field_descriptor.readout_selection

        self.data_type = field_descriptor.data_type

        self.storage_number = self._extract_storage_number()

        self.value_function = self._extract_function()

        self.last_field = self._is_last_field()

    def _is_last_field(self) -> bool:
        return self.field_code & DIF_EXTENSION_BIT_MASK == 0

    def _extract_storage_number(self) -> int:
        return (self.field_code & DIF_STORAGE_NUMBER_BIT_MASK) >> DIF_STORAGE_NUMBER_BIT_SHIFT

    def _extract_function(self) -> ValueFunction:
        function_code = self.field_code & DIF_FUNCTION_BIT_MASK
        for function_descriptor in _FunctionTable:
            if function_code == function_descriptor.code:
                return function_descriptor.type
        else:
            raise RuntimeError(f"Function code for DataDIF 0x{self.field_code:02X} not found in function table")


class SpecialDIF(DIF):
    """Data Information Field for special functions.

    SpecialDIF is used for special control functions:
    - MANUFACTURER_DATA_HEADER (0x0F): Start of manufacturer-specific data
    - MORE_RECORDS_FOLLOW (0x1F): Continuation in next telegram
    - IDLE_FILLER (0x2F): Padding byte (skip)
    - GLOBAL_READOUT (0x7F): Request all data

    Attributes:
        special_function: The special function type (DIFSpecialFunction flag)

    Reference: EN 13757-3:2018, Table 6 (page 14)
    """

    special_function: DIFSpecialFunction

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        super().__init__(direction, field_code)

        field_descriptor = _find_field_descriptor(self.direction, self.field_code)

        if not isinstance(field_descriptor, _SpecialFieldDescriptor):
            raise ValueError("Incorrect field descriptor type for SpecialDIF")

        self.special_function = field_descriptor.function


class DIFE(DIF):
    """Base class for Data Information Field Extension (DIFE).

    DIFE bytes extend the DIF with additional bits for storage number, tariff,
    and subunit. Up to 10 DIFE bytes can follow a DIF (or 11 with FinalDIFE).

    This class uses a factory pattern to instantiate DataDIFE or FinalDIFE
    based on the field_code (0x00 creates FinalDIFE, others create DataDIFE).

    Reference: EN 13757-3:2018, section 6.3.7, Table 8 (page 14)
    """

    def __new__(cls, direction: CommunicationDirection, field_code: int, prev_field: DIF | DIFE) -> DIFE:
        if field_code == DIFE_FINAL_CODE:
            return object.__new__(FinalDIFE)
        return object.__new__(DataDIFE)

    def __init__(self, direction: CommunicationDirection, field_code: int, prev_field: DIF | DIFE) -> None:
        super().__init__(direction, field_code)

        if prev_field.direction is not self.direction:
            raise ValueError("DIFE communication direction does not match previous field communication direction")

        if prev_field.last_field:
            raise ValueError("Cannot extend DIF/DIFE chain past last field")

        if prev_field.next_field is not None:
            raise ValueError("Previous field already has a next field assigned")

        self.prev_field = prev_field
        self.prev_field.next_field = self

        self.chain_position = self.prev_field.chain_position + 1

        self.last_field = self._is_last_field()

    def _is_last_field(self) -> bool:
        return self.field_code & DIFE_EXTENSION_BIT_MASK == 0


class DataDIFE(DIFE):
    """Data Information Field Extension for extending storage number, tariff, and subunit.

    DataDIFE provides additional bits to extend the range of:
    - Storage number: 4 bits per DIFE (bits 0-3)
    - Tariff: 2 bits per DIFE (bits 4-5)
    - Subunit: 1 bit per DIFE (bit 6)
    - Extension bit: bit 7

    The bits are concatenated based on chain_position to build the full value.
    With 10 DIFEs max, storage number can reach 41 bits (1 from DIF + 40 from DIFEs).

    Attributes:
        storage_number: Contribution to storage number (shifted based on chain position)
        subunit: Contribution to subunit (shifted based on chain position)
        tariff: Contribution to tariff (shifted based on chain position)

    Reference: EN 13757-3:2018, section 6.3.7, Table 8 (page 14)
    """

    storage_number: int

    subunit: int

    tariff: int

    def __init__(self, direction: CommunicationDirection, field_code: int, prev_field: DIF | DIFE) -> None:
        if prev_field.chain_position >= DIFE_MAXIMUM_CHAIN_LENGTH:
            raise ValueError("Exceeded maximum DIFE chain length")

        super().__init__(direction, field_code, prev_field)

        self.storage_number = self._extract_storage_number()

        self.subunit = self._extract_subunit()

        self.tariff = self._extract_tariff()

        if self.last_field and self.storage_number == 0 and self.subunit == 0 and self.tariff == 0:
            raise ValueError(
                "DataDIFE may not have storage number, subunit, tariff all zero and be the last field at the same time"
            )

    def _extract_storage_number(self) -> int:
        raw_bits = (self.field_code & DIFE_STORAGE_NUMBER_BIT_MASK) >> DIFE_STORAGE_NUMBER_BIT_SHIFT
        must_shift = DIFE_STORAGE_NUMBER_BIT_LENGTH * (self.chain_position - 1) + DIF_STORAGE_NUMBER_BIT_LENGTH

        return raw_bits << must_shift

    def _extract_subunit(self) -> int:
        raw_bit = (self.field_code & DIFE_SUBUNIT_BIT_MASK) >> DIFE_SUBUNIT_BIT_SHIFT
        must_shift = DIFE_SUBUNIT_BIT_LENGTH * (self.chain_position - 1)

        return raw_bit << must_shift

    def _extract_tariff(self) -> int:
        raw_bits = (self.field_code & DIFE_TARIFF_BIT_MASK) >> DIFE_TARIFF_BIT_SHIFT
        must_shift = DIFE_TARIFF_BIT_LENGTH * (self.chain_position - 1)

        return raw_bits << must_shift


class FinalDIFE(DIFE):
    """Final DIFE marking storage number as OBIS register number.

    FinalDIFE is a special DIFE with value 0x00 that changes the semantic
    meaning of the storage number from historical time point to OBIS register
    number (value group F).

    When present, the storage number represents a register number in the
    range 0-99 or 101-125 (value 100 is reserved, 255 = current value).

    FinalDIFE must be the last field in the chain and does NOT contribute
    bits to storage/tariff/subunit - it only acts as a marker.

    Usage:
        - Mandatory for "Compact profile with register numbers" (VIFE = 0x1E)
        - Used for OBIS translation (Annex H.2)
        - Can appear after up to 10 regular DIFEs (not counted in the 10 limit)

    Reference: EN 13757-3:2018
        - Section 3.4 (page 8): Final DIFE definition
        - Section 6.3.5 (page 14): Usage with register numbers
        - Section F.2.6 (page 56): Compact profiles
    """

    def __init__(self, direction: CommunicationDirection, field_code: int, prev_field: DIF | DIFE) -> None:
        if prev_field.chain_position > DIFE_MAXIMUM_CHAIN_LENGTH:
            raise ValueError("Exceeded maximum DIFE + final DIFE chain length")

        super().__init__(direction, field_code, prev_field)

        if field_code != DIFE_FINAL_CODE:
            raise ValueError("FinalDIFE must match final DIFE code")
