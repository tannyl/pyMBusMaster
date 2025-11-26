"""VIF (Value Information Field) type system and interpretation logic.

This module contains the semantic type system for VIF/VIFE codes, including:
- VIF class that represents a single VIF/VIFE byte with chaining support
- _FieldDescriptor metadata structure for complete VIF information
- VIF/VIFE table enums with range-based lookup
- Value transformation functions
- Automatic table selection for VIF/VIFE chains
- Data type rules for VIF/VIFE constraints

Reference: EN 13757-3:2018, Tables 10-16
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import lru_cache

# Import from protocol package
from .common import CommunicationDirection
from .data import DataRules
from .value import (
    ValueDescription,
    ValueDescriptionTransformer,
    ValueTransformer,
    ValueUnit,
    ValueUnitTransformer,
)

# ============================================================================
# VIF Constants
# ============================================================================


VIFE_MAXIMUM_CHAIN_LENGTH = 10  # Maximum number of chained VIFE bytes

VIF_EXTENSION_BIT_MASK = 0b10000000  # Bit 7: extension bit (more VIFE bytes follow)


# =============================================================================
# VIF Descriptor
# =============================================================================


@dataclass(frozen=True, kw_only=True)
class _AbstractFieldDescriptor(ABC):
    """Base class for VIF/VIFE field descriptors.

    Field descriptors contain metadata for VIF/VIFE codes, including the code value,
    bit mask for pattern matching, and communication direction constraints.
    """

    code: int  # Actual VIF/VIFE code value
    mask: int = 0b01111111  # Bit mask for pattern matching (default: strip extension bit)

    direction: CommunicationDirection = CommunicationDirection.BIDIRECTIONAL


@dataclass(frozen=True, kw_only=True)
class _TrueFieldDescriptor(_AbstractFieldDescriptor):
    """Descriptor for VIF/VIFE codes that define unit and value semantics.

    Used for codes that directly specify physical units, value descriptions,
    and data type requirements.
    """

    data_rules: DataRules.Requires = DataRules.Requires.DEFAULT_ABHLVAR

    value_description: ValueDescription | None = None  # Human-readable description of the value

    value_unit: ValueUnit | None = None  # Physical unit (Wh, m³, °C, etc.) or empty for non-physical

    value_transformer: ValueTransformer | None = None


@dataclass(frozen=True, kw_only=True)
class _PlainTextFieldDescriptor(_TrueFieldDescriptor):
    """Descriptor for plain text VIF (code 0x7C).

    Indicates that the data field contains an ASCII string describing the unit.
    """


@dataclass(frozen=True, kw_only=True)
class _ManufacturerFieldDescriptor(_AbstractFieldDescriptor):
    """Descriptor for manufacturer-specific VIF/VIFE (code 0x7F/0xFF).

    Indicates that data interpretation is manufacturer-specific.
    """


@dataclass(frozen=True, kw_only=True)
class _ReadoutAnyFieldDescriptor(_AbstractFieldDescriptor):
    """Descriptor for global readout request VIF (code 0x7E).

    Used by master to request readout of all data from slave.
    """


@dataclass(frozen=True, kw_only=True)
class _CombinableFieldDescriptor(_AbstractFieldDescriptor):
    """Descriptor for combinable (orthogonal) VIFE codes.

    Used for VIFE codes that modify or extend the preceding VIF/VIFE,
    such as multipliers, time divisors, phase information, etc.
    """

    data_rules: DataRules.Requires | None = None  # Allowed data types for this VIF/VIFE

    value_description_transformer: ValueDescriptionTransformer | None = None

    value_unit_transformer: ValueUnitTransformer | None = None

    value_transformer: ValueTransformer | None = None


@dataclass(frozen=True, kw_only=True)
class _ActionFieldDescriptor(_AbstractFieldDescriptor):
    """Descriptor for object action VIFE codes (master to slave).

    Used for VIFE codes that specify operations like write, add, subtract, etc.
    """

    direction: CommunicationDirection = CommunicationDirection.MASTER_TO_SLAVE

    action: str


@dataclass(frozen=True, kw_only=True)
class _ErrorFieldDescriptor(_AbstractFieldDescriptor):
    """Descriptor for record error VIFE codes (slave to master).

    Used for VIFE codes that indicate errors in DIF, VIF, or data processing.
    """

    direction: CommunicationDirection = CommunicationDirection.SLAVE_TO_MASTER

    error: str

    error_group: str


@dataclass(frozen=True, kw_only=True)
class _ExtensionFieldDescriptor(_AbstractFieldDescriptor):
    """Descriptor for VIF/VIFE codes that point to extension tables.

    Used for codes like 0xFB and 0xFD that require the next VIFE to be
    looked up in a different table.
    """

    mask: int = 0b11111111  # Bit mask for pattern matching (default: match full byte)

    extension_table: tuple[_AbstractFieldDescriptor, ...]  # Which extension table must follow this VIF/VIFE


# _CombinableExtensionFieldTable
_CombinableExtensionFieldTable: tuple[_AbstractFieldDescriptor, ...] = (
    # ==========================================================================
    # Phase Information (E000 0xxx)
    # ==========================================================================
    # E000 0000: Reserved
    # E000 0001: At phase L1
    _CombinableFieldDescriptor(  # AT_PHASE_L1
        code=0b00000001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 0010: At phase L2
    _CombinableFieldDescriptor(  # AT_PHASE_L2
        code=0b00000010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 0011: At phase L3
    _CombinableFieldDescriptor(  # AT_PHASE_L3
        code=0b00000011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 0100: At neutral (N)
    _CombinableFieldDescriptor(  # AT_NEUTRAL
        code=0b00000100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 0101: Between phase L1 and L2
    _CombinableFieldDescriptor(  # BETWEEN_PHASE_L1_L2
        code=0b00000101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 0110: Between phase L2 and L3
    _CombinableFieldDescriptor(  # BETWEEN_PHASE_L2_L3
        code=0b00000110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 0111: Between phase L3 and L1
    _CombinableFieldDescriptor(  # BETWEEN_PHASE_L3_L1
        code=0b00000111,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Quadrant Information (E000 1xxx)
    # ==========================================================================
    # E000 1000: At quadrant Q1
    _CombinableFieldDescriptor(  # AT_QUADRANT_Q1
        code=0b00001000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 1001: At quadrant Q2
    _CombinableFieldDescriptor(  # AT_QUADRANT_Q2
        code=0b00001001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 1010: At quadrant Q3
    _CombinableFieldDescriptor(  # AT_QUADRANT_Q3
        code=0b00001010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 1011: At quadrant Q4
    _CombinableFieldDescriptor(  # AT_QUADRANT_Q4
        code=0b00001011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E000 1100: Delta between import and export
    _CombinableFieldDescriptor(  # DELTA_IMPORT_EXPORT
        code=0b00001100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # 0x0D-0x0F: Reserved
    # ==========================================================================
    # Data Presentation and Direction (E001 xxxx)
    # ==========================================================================
    # E001 0000: Accumulation of absolute value
    _CombinableFieldDescriptor(  # ACCUMULATION_ABSOLUTE_BOTH
        code=0b00010000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E001 0001: Data presented with type C
    _CombinableFieldDescriptor(  # DATA_TYPE_C
        code=0b00010001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        data_rules=DataRules.Requires.UNSIGNED_C,  # Forces unsigned interpretation (all valid sizes)
    ),
    # E001 0010: Data presented with type D
    _CombinableFieldDescriptor(  # DATA_TYPE_D
        code=0b00010010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        data_rules=DataRules.Requires.BOOLEAN_D,  # Forces boolean interpretation (all valid sizes)
    ),
    # 0x13: Reserved
    # E001 0100: Direction: from communication partner to meter
    _CombinableFieldDescriptor(  # DIRECTION_TO_METER
        code=0b00010100,
    ),
    # E001 0101: Direction: from meter to communication partner
    _CombinableFieldDescriptor(  # DIRECTION_FROM_METER
        code=0b00010101,
    ),
    # 0x16-0x7F: Reserved for future use
)


# _CombinableOrthogonalFieldTable
_CombinableOrthogonalFieldTable: tuple[_AbstractFieldDescriptor, ...] = (
    # ==========================================================================
    # Object Actions (E000 xxxx) - Master to Slave
    # Reference: EN 13757-3:2018, Table 17, page 26
    # ==========================================================================
    # E000 0000: Write (replace)
    _ActionFieldDescriptor(  # ACTION_WRITE
        code=0b00000000,
        action="Write (replace)",
    ),
    # E000 0001: Add value
    _ActionFieldDescriptor(  # ACTION_ADD
        code=0b00000001,
        action="Add value",
    ),
    # E000 0010: Subtract value
    _ActionFieldDescriptor(  # ACTION_SUBTRACT
        code=0b00000010,
        action="Subtract value",
    ),
    # E000 0011: OR (set bits)
    _ActionFieldDescriptor(  # ACTION_OR
        code=0b00000011,
        action="OR (set bits)",
    ),
    # E000 0100: AND
    _ActionFieldDescriptor(  # ACTION_AND
        code=0b00000100,
        action="AND",
    ),
    # E000 0101: XOR (toggle bits)
    _ActionFieldDescriptor(  # ACTION_XOR
        code=0b00000101,
        action="XOR (toggle bits)",
    ),
    # E000 0110: AND NOT (clear bits)
    _ActionFieldDescriptor(  # ACTION_AND_NOT
        code=0b00000110,
        action="AND NOT (clear bits)",
    ),
    # E000 0111: Clear
    _ActionFieldDescriptor(  # ACTION_CLEAR
        code=0b00000111,
        action="Clear",
    ),
    # E000 1000: Add entry
    _ActionFieldDescriptor(  # ACTION_ADD_ENTRY
        code=0b00001000,
        action="Add entry",
    ),
    # E000 1001: Delete entry
    _ActionFieldDescriptor(  # ACTION_DELETE_ENTRY
        code=0b00001001,
        action="Delete entry",
    ),
    # E000 1010: Delayed action
    _ActionFieldDescriptor(  # ACTION_DELAYED
        code=0b00001010,
        action="Delayed action",
    ),
    # E000 1011: Freeze data
    _ActionFieldDescriptor(  # ACTION_FREEZE_DATA
        code=0b00001011,
        action="Freeze data",
    ),
    # E000 1100: Add to readout-list
    _ActionFieldDescriptor(  # ACTION_ADD_TO_READOUT
        code=0b00001100,
        action="Add to readout-list",
    ),
    # E000 1101: Delete from readout-list
    _ActionFieldDescriptor(  # ACTION_DELETE_FROM_READOUT
        code=0b00001101,
        action="Delete from readout-list",
    ),
    # 0x0E-0x0F: Reserved
    # ==========================================================================
    # Record Error Codes (E000 0xxx - E000 1xxx) - Slave to Master
    # Reference: EN 13757-3:2018, Table 18, page 27
    # Note: Same codes as actions but different direction (slave to master vs master to slave)
    # ==========================================================================
    # DIF errors group
    # E000 0000: None
    _ErrorFieldDescriptor(  # ERROR_NONE
        code=0b00000000,
        error="None",
        error_group="DIF errors",
    ),
    # E000 0001: Too many DIFEs
    _ErrorFieldDescriptor(  # ERROR_TOO_MANY_DIFES
        code=0b00000001,
        error="Too many DIFEs",
        error_group="DIF errors",
    ),
    # E000 0010: Storage number not implemented
    _ErrorFieldDescriptor(  # ERROR_STORAGE_NOT_IMPLEMENTED
        code=0b00000010,
        error="Storage number not implemented",
        error_group="DIF errors",
    ),
    # E000 0011: Unit number not implemented
    _ErrorFieldDescriptor(  # ERROR_UNIT_NOT_IMPLEMENTED
        code=0b00000011,
        error="Unit number not implemented",
        error_group="DIF errors",
    ),
    # E000 0100: Tariff number not implemented
    _ErrorFieldDescriptor(  # ERROR_TARIFF_NOT_IMPLEMENTED
        code=0b00000100,
        error="Tariff number not implemented",
        error_group="DIF errors",
    ),
    # E000 0101: Function not implemented
    _ErrorFieldDescriptor(  # ERROR_FUNCTION_NOT_IMPLEMENTED
        code=0b00000101,
        error="Function not implemented",
        error_group="DIF errors",
    ),
    # E000 0110: Data class not implemented
    _ErrorFieldDescriptor(  # ERROR_DATA_CLASS_NOT_IMPLEMENTED
        code=0b00000110,
        error="Data class not implemented",
        error_group="DIF errors",
    ),
    # E000 0111: Data size not implemented
    _ErrorFieldDescriptor(  # ERROR_DATA_SIZE_NOT_IMPLEMENTED
        code=0b00000111,
        error="Data size not implemented",
        error_group="DIF errors",
    ),
    # E000 1000 to E000 1001: Reserved
    # E000 1010: Reserved
    # VIF errors group
    # E000 1011: Too many VIFEs
    _ErrorFieldDescriptor(  # ERROR_TOO_MANY_VIFES
        code=0b00001011,
        error="Too many VIFEs",
        error_group="VIF errors",
    ),
    # E000 1100: Illegal VIF-Group
    _ErrorFieldDescriptor(  # ERROR_ILLEGAL_VIF_GROUP
        code=0b00001100,
        error="Illegal VIF-Group",
        error_group="VIF errors",
    ),
    # E000 1101: Illegal VIF-Exponent
    _ErrorFieldDescriptor(  # ERROR_ILLEGAL_VIF_EXPONENT
        code=0b00001101,
        error="Illegal VIF-Exponent",
        error_group="VIF errors",
    ),
    # E000 1110: VIF/DIF mismatch
    _ErrorFieldDescriptor(  # ERROR_VIF_DIF_MISMATCH
        code=0b00001110,
        error="VIF/DIF mismatch",
        error_group="VIF errors",
    ),
    # E000 1111: Unimplemented action
    _ErrorFieldDescriptor(  # ERROR_UNIMPLEMENTED_ACTION
        code=0b00001111,
        error="Unimplemented action",
        error_group="VIF errors",
    ),
    # E001 0000 to E001 0001: Reserved
    # 0x10-0x11: Not used for record errors
    # ==========================================================================
    # Special Data Types (E001 00xx)
    # ==========================================================================
    # E001 0010: Average value
    _CombinableFieldDescriptor(  # AVERAGE_VALUE
        code=0b00010010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E001 0011: Inverse compact profile
    _CombinableFieldDescriptor(  # INVERSE_COMPACT_PROFILE
        code=0b00010011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E001 0100: Relative deviation
    _CombinableFieldDescriptor(  # RELATIVE_DEVIATION
        code=0b00010100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Record Error Codes (E001 0101 - E001 1100) - Slave to Master
    # Reference: EN 13757-3:2018, Table 18, page 27 (continued)
    # ==========================================================================
    # Data errors group
    # E001 0101: No data available (undefined value)
    _ErrorFieldDescriptor(  # ERROR_NO_DATA_AVAILABLE
        code=0b00010101,
        error="No data available (undefined value)",
        error_group="Data errors",
    ),
    # E001 0110: Data overflow
    _ErrorFieldDescriptor(  # ERROR_DATA_OVERFLOW
        code=0b00010110,
        error="Data overflow",
        error_group="Data errors",
    ),
    # E001 0111: Data underflow
    _ErrorFieldDescriptor(  # ERROR_DATA_UNDERFLOW
        code=0b00010111,
        error="Data underflow",
        error_group="Data errors",
    ),
    # E001 1000: Data error
    _ErrorFieldDescriptor(  # ERROR_DATA_ERROR
        code=0b00011000,
        error="Data error",
        error_group="Data errors",
    ),
    # E001 1001 to E001 1011: Reserved
    # Other errors group
    # E001 1100: Premature end of record
    _ErrorFieldDescriptor(  # ERROR_PREMATURE_END_OF_RECORD
        code=0b00011100,
        error="Premature end of record",
        error_group="Other errors",
    ),
    # ==========================================================================
    # Special Data Types (E001 11xx) - Slave to Master
    # ==========================================================================
    # E001 1101: Standard conform data content
    _CombinableFieldDescriptor(  # STANDARD_CONFORM_DATA
        code=0b00011101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E001 1110: Compact profile with register numbers
    _CombinableFieldDescriptor(  # COMPACT_PROFILE_WITH_REGISTER
        code=0b00011110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E001 1111: Compact profile
    _CombinableFieldDescriptor(  # COMPACT_PROFILE
        code=0b00011111,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Time Modifiers (E010 0xxx)
    # ==========================================================================
    # E010 0000: Per second
    _CombinableFieldDescriptor(  # PER_SECOND
        code=0b00100000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 0001: Per minute
    _CombinableFieldDescriptor(  # PER_MINUTE
        code=0b00100001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 0010: Per hour
    _CombinableFieldDescriptor(  # PER_HOUR
        code=0b00100010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 0011: Per day
    _CombinableFieldDescriptor(  # PER_DAY
        code=0b00100011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 0100: Per week
    _CombinableFieldDescriptor(  # PER_WEEK
        code=0b00100100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 0101: Per month
    _CombinableFieldDescriptor(  # PER_MONTH
        code=0b00100101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 0110: Per year
    _CombinableFieldDescriptor(  # PER_YEAR
        code=0b00100110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 0111: Per revolution/measurement
    _CombinableFieldDescriptor(  # PER_REVOLUTION
        code=0b00100111,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Pulse Increments (E010 10p, E010 101p)
    # p = channel number (0 or 1)
    # ==========================================================================
    # E010 100p: Increment per input pulse on input channel number p (covers 0x28-0x29, 0xA8-0xA9)
    _CombinableFieldDescriptor(  # INCREMENT_INPUT_PULSE
        code=0b00101000,
        mask=0b01111110,  # Extension bit + 1-bit variable (p = channel 0 or 1)
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        data_rules=DataRules.Requires.ANY,  # Calibration factors can use any numeric type
    ),
    # E010 101p: Increment per output pulse on output channel number p (covers 0x2A-0x2B, 0xAA-0xAB)
    _CombinableFieldDescriptor(  # INCREMENT_OUTPUT_PULSE
        code=0b00101010,
        mask=0b01111110,  # Extension bit + 1-bit variable (p = channel 0 or 1)
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        data_rules=DataRules.Requires.ANY,  # Calibration factors can use any numeric type
    ),
    # ==========================================================================
    # Divisors (E010 11xx)
    # ==========================================================================
    # E010 1100: Per litre
    _CombinableFieldDescriptor(  # PER_LITRE
        code=0b00101100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 1101: Per m³
    _CombinableFieldDescriptor(  # PER_M3
        code=0b00101101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 1110: Per kg
    _CombinableFieldDescriptor(  # PER_KG
        code=0b00101110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E010 1111: Per K (Kelvin)
    _CombinableFieldDescriptor(  # PER_KELVIN
        code=0b00101111,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # More Divisors (E011 0xxx)
    # ==========================================================================
    # E011 0000: Per kWh
    _CombinableFieldDescriptor(  # PER_KWH
        code=0b00110000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 0001: Per GJ
    _CombinableFieldDescriptor(  # PER_GJ
        code=0b00110001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 0010: Per kW
    _CombinableFieldDescriptor(  # PER_KW
        code=0b00110010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 0011: Per (K·l) (Kelvin·litre)
    _CombinableFieldDescriptor(  # PER_KELVIN_LITRE
        code=0b00110011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 0100: Per V (volt)
    _CombinableFieldDescriptor(  # PER_VOLT
        code=0b00110100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 0101: Per A (ampere)
    _CombinableFieldDescriptor(  # PER_AMPERE
        code=0b00110101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Multipliers (E011 01xx)
    # ==========================================================================
    # E011 0110: Multiplied by s
    _CombinableFieldDescriptor(  # MULTIPLIED_SECS
        code=0b00110110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 0111: Multiplied by s/V
    _CombinableFieldDescriptor(  # MULTIPLIED_SECS_V
        code=0b00110111,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 1000: Multiplied by s/A
    _CombinableFieldDescriptor(  # MULTIPLIED_SECS_A
        code=0b00111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Data Characteristics (E011 1xxx)
    # ==========================================================================
    # E011 1001: Start date(/time) of
    _CombinableFieldDescriptor(  # START_DATE_TIME
        code=0b00111001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        data_rules=DataRules.Requires.TEMPORAL_FGIJM,  # Date/Time types
    ),
    # E011 1010: VIF contains uncorrected unit or value at metering conditions
    _CombinableFieldDescriptor(  # UNCORRECTED_UNIT
        code=0b00111010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 1011: Accumulation only if positive contributions
    _CombinableFieldDescriptor(  # ACCUMULATION_POSITIVE
        code=0b00111011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 1100: Accumulation of abs value only if negative contributions
    _CombinableFieldDescriptor(  # ACCUMULATION_ABS_NEGATIVE
        code=0b00111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 1101: Used for alternate non-metric unit system
    _CombinableFieldDescriptor(  # NON_METRIC_UNIT
        code=0b00111101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 1110: Value at base conditions
    _CombinableFieldDescriptor(  # VALUE_BASE_CONDITIONS
        code=0b00111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E011 1111: OBIS-declaration
    _CombinableFieldDescriptor(  # OBIS_DECLARATION
        code=0b00111111,
    ),
    # ==========================================================================
    # Limit Values (E100 u000, E100 u001, E100 uf1b)
    # u = 0: lower, u = 1: upper
    # f = 0: first, f = 1: last
    # b = 0: begin, b = 1: end
    # ==========================================================================
    # E100 u000: Limit value (covers 0x40, 0x48)
    # u = 0: lower, u = 1: upper
    _CombinableFieldDescriptor(  # LIMIT_VALUE
        code=0b01000000,
        mask=0b01110111,  # 1-bit variable (u), strip extension bit
    ),
    # E100 u001: Number of exceeds of limit (covers 0x41, 0x49)
    # u = 0: lower, u = 1: upper
    _CombinableFieldDescriptor(  # LIMIT_EXCEED_COUNT
        code=0b01000001,
        mask=0b01110111,  # 1-bit variable (u), strip extension bit
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E100 uf1b: Date(/time) of limit exceed (covers 0x42-0x43, 0x46-0x47, 0x4A-0x4B, 0x4E-0x4F)
    # u = 0: lower, u = 1: upper
    # f = 0: first, f = 1: last
    # b = 0: begin, b = 1: end
    # Note: 0x44-0x45 and 0x4C-0x4D are reserved
    _CombinableFieldDescriptor(  # DATE_LIMIT_EXCEED
        code=0b01000010,
        mask=0b01110011,  # 3-bit variable (u, f, b), but b=10 is reserved, strip extension bit
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Duration of Limit Exceed (E101 ufnn)
    # u = 0: lower, u = 1: upper
    # f = 0: first, f = 1: last
    # nn = 00: seconds, 01: minutes, 10: hours, 11: days
    # ==========================================================================
    # E101 ufnn: Duration of limit exceed (covers 0x50-0x5F)
    _CombinableFieldDescriptor(  # DURATION_LIMIT_EXCEED
        code=0b01010000,
        mask=0b01110000,  # 4-bit variable (u, f, nn), strip extension bit
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Duration (E110 0fnn, E110 1f1b)
    # f = 0: first, f = 1: last
    # nn = 00: seconds, 01: minutes, 10: hours, 11: days
    # b = 0: begin, b = 1: end
    # ==========================================================================
    # E110 0fnn: Duration (covers 0x60-0x67)
    _CombinableFieldDescriptor(  # DURATION
        code=0b01100000,
        mask=0b01111000,  # 3-bit variable (f, nn), strip extension bit
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E110 1u00: Value during limit exceed (covers 0x68, 0x6C)
    # u = 0: lower, u = 1: upper
    _CombinableFieldDescriptor(  # VALUE_DURING_LIMIT_EXCEED
        code=0b01101000,
        mask=0b01110111,  # 1-bit variable (u), strip extension bit
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E110 1001: Leakage values
    _CombinableFieldDescriptor(  # LEAKAGE_VALUES
        code=0b01101001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # 0x6A: Reserved
    # E110 1101: Overflow values
    _CombinableFieldDescriptor(  # OVERFLOW_VALUES
        code=0b01101101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E110 1f1b: Date(/time) of (covers 0x6E-0x6F)
    # f = 0: first, f = 1: last
    # b = 0: begin, b = 1: end
    _CombinableFieldDescriptor(  # DATE_TIME_OF
        code=0b01101110,
        mask=0b01111101,  # 2-bit variable (f, b), strip extension bit
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # ==========================================================================
    # Multiplicative Correction (E111 0nnn)
    # nnn = 0-7: 10^(nnn-6)
    # ==========================================================================
    # E111 0nnn: Multiplicative correction factor (covers 0x70-0x77)
    _CombinableFieldDescriptor(  # MULTIPLICATIVE_CORRECTION
        code=0b01110000,
        mask=0b01111000,  # 3-bit variable (nnn), strip extension bit
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_6,
    ),
    # ==========================================================================
    # Additive Correction (E111 10nn)
    # nn = 0-3: 10^(nn-3) × unit of VIF
    # ==========================================================================
    # E111 10nn: Additive correction constant (covers 0x78-0x7B)
    _CombinableFieldDescriptor(  # ADDITIVE_CORRECTION
        code=0b01111000,
        mask=0b01111100,  # 2-bit variable (nn), strip extension bit
        value_transformer=ValueTransformer.ADD_10_POW_NN_MINUS_3,
    ),
    # ==========================================================================
    # Extension and Special Codes (E111 11xx)
    # ==========================================================================
    # E111 1100: Extension of combinable (orthogonal) VIFE-Code
    _ExtensionFieldDescriptor(  # EXTENSION_COMBINABLE
        code=0b11111100,
        extension_table=_CombinableExtensionFieldTable,
    ),
    # E111 1101: Multiplicative correction factor 10³
    _CombinableFieldDescriptor(  # MULTIPLICATIVE_CORRECTION_1000
        code=0b01111101,
        value_transformer=ValueTransformer.MULT_1000,
    ),
    # E111 1110: Future value
    _CombinableFieldDescriptor(  # FUTURE_VALUE
        code=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E111 1111: Next VIFEs and data of this block are manufacturer specific
    _ManufacturerFieldDescriptor(  # MANUFACTURER_SPECIFIC_VIFE
        code=0b01111111,
    ),
)


# _SecondExtensionSecondLevelFieldTable
_SecondExtensionSecondLevelFieldTable: tuple[_AbstractFieldDescriptor, ...] = (
    # E000 0000: Currently selected application (single value, no range)
    _TrueFieldDescriptor(  # CURRENTLY_SELECTED_APPLICATION
        code=0b00000000,
        mask=0b01111111,  # Default: exact match, strip extension bit
        # The identifier
        value_description=ValueDescription.CURRENTLY_SELECTED_APPLICATION,
    ),
    # 0x01 reserved
    # Remaining battery lifetime (covers 0x02-0x03: months to years)
    # E000 001p where p: 0=months, 1=years
    # This uses 1-bit encoding instead of the typical 2-bit (nn) encoding
    _TrueFieldDescriptor(  # REMAINING_BATTERY_LIFETIME
        code=0b00000010,
        mask=0b01111110,  # Range: 1-bit variable (p), strip extension bit
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.REMAINING_BATTERY_LIFETIME,
    ),
    # 0x04-0x7F: Reserved
)


# _SecondExtensionFieldTable
_SecondExtensionFieldTable: tuple[_AbstractFieldDescriptor, ...] = (
    # ==========================================================================
    # Currency Units (E000 00nn, E000 01nn)
    # ==========================================================================
    # Credit of 10^(nn-3) local currency units (covers 0x00-0x03)
    # E000 00nn: 10^(nn-3) currency
    _TrueFieldDescriptor(  # CREDIT
        code=0b00000000,
        mask=0b01111100,  # Range: 2-bit variable (nn), strip extension bit
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.CREDIT,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # Debit of 10^(nn-3) local currency units (covers 0x04-0x07)
    # E000 01nn: 10^(nn-3) currency
    _TrueFieldDescriptor(  # DEBIT
        code=0b00000100,
        mask=0b01111100,  # Range: 2-bit variable (nn), strip extension bit
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DEBIT,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # ==========================================================================
    # Enhanced Identification (E000 1xxx)
    # ==========================================================================
    _TrueFieldDescriptor(  # UNIQUE_MESSAGE_ID
        code=0b00001000,
        # Protocol metadata
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.UNIQUE_MESSAGE_ID,
    ),
    _TrueFieldDescriptor(  # DEVICE_TYPE
        code=0b00001001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DEVICE_TYPE,
    ),
    _TrueFieldDescriptor(  # MANUFACTURER
        code=0b00001010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.MANUFACTURER,
    ),
    _TrueFieldDescriptor(  # PARAMETER_SET_ID
        code=0b00001011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.PARAMETER_SET_ID,
    ),
    _TrueFieldDescriptor(  # MODEL_VERSION
        code=0b00001100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.MODEL_VERSION,
    ),
    _TrueFieldDescriptor(  # HARDWARE_VERSION
        code=0b00001101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.HARDWARE_VERSION,
    ),
    _TrueFieldDescriptor(  # FIRMWARE_VERSION
        code=0b00001110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.FIRMWARE_VERSION,
    ),
    _TrueFieldDescriptor(  # SOFTWARE_VERSION
        code=0b00001111,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.SOFTWARE_VERSION,
    ),
    # ==========================================================================
    # Improved Selection / Configuration (E001 xxxx)
    # ==========================================================================
    _TrueFieldDescriptor(  # CUSTOMER_LOCATION
        code=0b00010000,
        value_description=ValueDescription.CUSTOMER_LOCATION,
    ),
    _TrueFieldDescriptor(  # CUSTOMER
        code=0b00010001,
        value_description=ValueDescription.CUSTOMER,
    ),
    _TrueFieldDescriptor(  # ACCESS_CODE_USER
        code=0b00010010,
        value_description=ValueDescription.ACCESS_CODE,
    ),
    _TrueFieldDescriptor(  # ACCESS_CODE_OPERATOR
        code=0b00010011,
        value_description=ValueDescription.ACCESS_CODE,
    ),
    _TrueFieldDescriptor(  # ACCESS_CODE_SYSTEM_OPERATOR
        code=0b00010100,
        value_description=ValueDescription.ACCESS_CODE,
    ),
    _TrueFieldDescriptor(  # ACCESS_CODE_DEVELOPER
        code=0b00010101,
        value_description=ValueDescription.ACCESS_CODE,
    ),
    _TrueFieldDescriptor(  # PASSWORD
        code=0b00010110,
        value_description=ValueDescription.PASSWORD,
    ),
    _TrueFieldDescriptor(  # ERROR_FLAGS
        code=0b00010111,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ERROR_FLAGS,
        data_rules=DataRules.Requires.BOOLEAN_D,  # Type B → Type D (Boolean bit array, all valid sizes)
    ),
    _TrueFieldDescriptor(  # ERROR_MASK
        code=0b00011000,
        value_description=ValueDescription.ERROR_MASK,
    ),
    _TrueFieldDescriptor(  # SECURITY_KEY
        code=0b00011001,
        value_description=ValueDescription.SECURITY_KEY,
    ),
    _TrueFieldDescriptor(  # DIGITAL_OUTPUT
        code=0b00011010,
        value_description=ValueDescription.DIGITAL_OUTPUT,
        data_rules=DataRules.Requires.BOOLEAN_D,  # Type B → Type D (Boolean bit array, all valid sizes)
    ),
    _TrueFieldDescriptor(  # DIGITAL_INPUT
        code=0b00011011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DIGITAL_INPUT,
        data_rules=DataRules.Requires.BOOLEAN_D,  # Type B → Type D (Boolean bit array, all valid sizes)
    ),
    _TrueFieldDescriptor(  # BAUDRATE
        code=0b00011100,
        # Protocol metadata
        value_description=ValueDescription.BAUDRATE,
    ),
    _TrueFieldDescriptor(  # RESPONSE_DELAY
        code=0b00011101,
        # Protocol metadata
        value_description=ValueDescription.RESPONSE_DELAY,
    ),
    _TrueFieldDescriptor(  # RETRY
        code=0b00011110,
        # Protocol metadata
        value_description=ValueDescription.RETRY,
    ),
    _TrueFieldDescriptor(  # REMOTE_CONTROL
        code=0b00011111,
        value_description=ValueDescription.REMOTE_CONTROL,
        data_rules=DataRules.Requires.BOOLEAN_D,  # Type B → Type D (Boolean bit array, all valid sizes)
    ),
    # ==========================================================================
    # Storage Management (E010 00xx)
    # ==========================================================================
    _TrueFieldDescriptor(  # FIRST_STORAGE_NUMBER
        code=0b00100000,
        value_description=ValueDescription.STORAGE_NUMBER,
    ),
    _TrueFieldDescriptor(  # LAST_STORAGE_NUMBER
        code=0b00100001,
        value_description=ValueDescription.STORAGE_NUMBER,
    ),
    _TrueFieldDescriptor(  # SIZE_STORAGE_BLOCK
        code=0b00100010,
        value_description=ValueDescription.STORAGE_BLOCK_SIZE,
    ),
    _TrueFieldDescriptor(  # TARIFF_SUBUNIT_DESCRIPTOR
        code=0b00100011,
        # Billing domain
        value_description=ValueDescription.TARIFF_DESCRIPTOR,
    ),
    # Storage interval (covers 0x24-0x27: seconds to days)
    # E010 01nn where nn: 00=sec, 01=min, 10=hour, 11=day
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # STORAGE_INTERVAL
        code=0b00100100,
        mask=0b01111100,
        # Time domain
        value_description=ValueDescription.STORAGE_INTERVAL,
    ),
    # Individual month/year values (not part of nn range)
    _TrueFieldDescriptor(  # STORAGE_INTERVAL_MONTHS
        code=0b00101000,
        # Time domain
        value_description=ValueDescription.STORAGE_INTERVAL,
    ),
    _TrueFieldDescriptor(  # STORAGE_INTERVAL_YEARS
        code=0b00101001,
        # Time domain
        value_description=ValueDescription.STORAGE_INTERVAL,
    ),
    _TrueFieldDescriptor(  # OPERATOR_SPECIFIC_DATA
        code=0b00101010,
        value_description=ValueDescription.OPERATOR_DATA,
    ),
    _TrueFieldDescriptor(  # TIME_POINT_SECOND
        code=0b00101011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.TIME_POINT,
    ),
    # Duration since last readout (covers 0x2C-0x2F: seconds to days)
    # E010 11nn where nn: 00=sec, 01=min, 10=hour, 11=day
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # DURATION_SINCE_READOUT
        code=0b00101100,
        mask=0b01111100,
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DURATION_SINCE_READOUT,
    ),
    # ==========================================================================
    # Tariff Management (E011 xxxx)
    # ==========================================================================
    _TrueFieldDescriptor(  # START_DATE_TIME_TARIFF
        code=0b00110000,
        value_description=ValueDescription.TARIFF_START,
        data_rules=DataRules.Requires.TEMPORAL_FGIJM,  # Date/Time types
    ),
    # Duration of tariff (covers 0x31-0x33: minutes to days, nn=01 to 11)
    # E011 00nn where nn: 01=min, 10=hour, 11=day (00 is START_DATE_TIME above)
    # Note: Spec says "nn = 01 to 11", so 0x30 is separate
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # DURATION_TARIFF
        code=0b00110001,
        mask=0b01111100,
        # Time domain
        value_description=ValueDescription.TARIFF_DURATION,
    ),
    # Period of tariff (covers 0x34-0x37: seconds to days)
    # E011 01nn where nn: 00=sec, 01=min, 10=hour, 11=day
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # PERIOD_TARIFF
        code=0b00110100,
        mask=0b01111100,
        # Time domain
        value_description=ValueDescription.TARIFF_PERIOD,
    ),
    # Individual month/year values (not part of nn range)
    _TrueFieldDescriptor(  # PERIOD_TARIFF_MONTHS
        code=0b00111000,
        # Time domain
        value_description=ValueDescription.TARIFF_PERIOD,
    ),
    _TrueFieldDescriptor(  # PERIOD_TARIFF_YEARS
        code=0b00111001,
        # Time domain
        value_description=ValueDescription.TARIFF_PERIOD,
    ),
    _TrueFieldDescriptor(  # DIMENSIONLESS
        code=0b00111010,
        # Provides measurement
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DIMENSIONLESS,
    ),
    _TrueFieldDescriptor(  # DATA_CONTAINER_WIRELESS
        code=0b00111011,
        # Contains data
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DATA_CONTAINER_WIRELESS,
    ),
    # Period of nominal transmissions (covers 0x3C-0x3F: seconds to days)
    # E011 11nn where nn: 00=sec, 01=min, 10=hour, 11=day
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # TRANSMISSION_PERIOD
        code=0b00111100,
        mask=0b01111100,
        # Time domain
        value_description=ValueDescription.TRANSMISSION_PERIOD,
    ),
    # ==========================================================================
    # Electrical Units (E100 nnnn, E101 nnnn)
    # ==========================================================================
    # Voltage 10^(nnnn-9) volts (covers 0x40-0x4F)
    # E100 nnnn: 10^(nnnn-9) V
    # Formula: 10^(nnnn-9) = 10^-9 to 10^6 V (1 nV to 1 MV)
    _TrueFieldDescriptor(  # VOLTAGE
        code=0b01000000,
        mask=0b01110000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLTAGE,
        value_unit=ValueUnit.V,
        value_transformer=ValueTransformer.MULT_10_POW_NNNN_MINUS_9,
    ),
    # Current 10^(nnnn-12) amperes (covers 0x50-0x5F)
    # E101 nnnn: 10^(nnnn-12) A
    # Formula: 10^(nnnn-12) = 10^-12 to 10^3 A (1 pA to 1 kA)
    _TrueFieldDescriptor(  # CURRENT
        code=0b01010000,
        mask=0b01110000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.CURRENT,
        value_unit=ValueUnit.A,
        value_transformer=ValueTransformer.MULT_10_POW_NNNN_MINUS_12,
    ),
    # ==========================================================================
    # Counters and Control (E110 0xxx)
    # ==========================================================================
    _TrueFieldDescriptor(  # RESET_COUNTER
        code=0b01100000,
        # The count
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.RESET_COUNTER,
    ),
    _TrueFieldDescriptor(  # CUMULATION_COUNTER
        code=0b01100001,
        # The count
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.CUMULATION_COUNTER,
    ),
    _TrueFieldDescriptor(  # CONTROL_SIGNAL
        code=0b01100010,
        # The status
        value_description=ValueDescription.CONTROL_SIGNAL,
    ),
    _TrueFieldDescriptor(  # DAY_OF_WEEK
        code=0b01100011,
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DAY_OF_WEEK,
    ),
    _TrueFieldDescriptor(  # WEEK_NUMBER
        code=0b01100100,
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.WEEK_NUMBER,
    ),
    _TrueFieldDescriptor(  # TIME_POINT_DAY_CHANGE
        code=0b01100101,
        # Time domain
        value_description=ValueDescription.TIME_POINT_DAY_CHANGE,
        data_rules=DataRules.Requires.TEMPORAL_FGIJM,  # Date/Time types
    ),
    _TrueFieldDescriptor(  # STATE_PARAMETER_ACTIVATION
        code=0b01100110,
        # The state
        value_description=ValueDescription.PARAMETER_ACTIVATION,
    ),
    _TrueFieldDescriptor(  # SPECIAL_SUPPLIER_INFO
        code=0b01100111,
        # The info
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.SUPPLIER_INFO,
    ),
    # Duration since last cumulation (covers 0x68-0x6B: hours to years)
    # E110 10pp where pp: 00=hour, 01=day, 10=month, 11=year
    # Note: Unit is variable based on pp bits - decoded at runtime
    _TrueFieldDescriptor(  # DURATION_SINCE_CUMULATION
        code=0b01101000,
        mask=0b01111100,
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DURATION_SINCE_CUMULATION,
    ),
    # Operating time battery (covers 0x6C-0x6F: hours to years)
    # E110 11pp where pp: 00=hour, 01=day, 10=month, 11=year
    # Note: Unit is variable based on pp bits - decoded at runtime
    _TrueFieldDescriptor(  # BATTERY_LIFETIME
        code=0b01101100,
        mask=0b01111100,
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.BATTERY_LIFETIME,
    ),
    # ==========================================================================
    # Battery and RF Monitoring (E111 0xxx)
    # ==========================================================================
    _TrueFieldDescriptor(  # DATE_TIME_BATTERY_CHANGE
        code=0b01110000,
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.BATTERY_CHANGE_DATE,
        data_rules=DataRules.Requires.TEMPORAL_FGIJM,  # Date/Time types
    ),
    _TrueFieldDescriptor(  # RF_LEVEL
        code=0b01110001,
        # RF/electrical domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.RF_LEVEL,
        value_unit=ValueUnit.DBM,
    ),
    _TrueFieldDescriptor(  # DAYLIGHT_SAVING
        code=0b01110010,
        # Time domain
        value_description=ValueDescription.DAYLIGHT_SAVING,
        data_rules=DataRules.Requires.TEMPORAL_K,  # Type K_4 (Daylight savings)
    ),
    _TrueFieldDescriptor(  # LISTENING_WINDOW
        code=0b01110011,
        # Time domain
        value_description=ValueDescription.LISTENING_WINDOW,
        data_rules=DataRules.Requires.TEMPORAL_L,  # Type LVAR → Type L (Listening window), LVAR=EBh (88 bytes)
    ),
    _TrueFieldDescriptor(  # REMAINING_BATTERY_DAYS
        code=0b01110100,
        # Time domain
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.REMAINING_BATTERY_LIFETIME,
    ),
    _TrueFieldDescriptor(  # METER_STOPPED_COUNT
        code=0b01110101,
        # The count
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.METER_STOPPED_COUNT,
    ),
    _TrueFieldDescriptor(  # DATA_CONTAINER_MANUFACTURER
        code=0b01110110,
        # Contains data
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DATA_CONTAINER_MANUFACTURER,
    ),
    # 0x77-0x7C: Reserved
    # ==========================================================================
    # Extension Pointer
    # ==========================================================================
    _ExtensionFieldDescriptor(  # SECOND_LEVEL_EXTENSION
        code=0b11111101,
        extension_table=_SecondExtensionSecondLevelFieldTable,
    ),
    # 0x7E-0x7F: Reserved
)


# _FirstExtensionFieldTable
_FirstExtensionFieldTable: tuple[_AbstractFieldDescriptor, ...] = (
    # ==========================================================================
    # Energy - Extended Range (normalized to base units)
    # ==========================================================================
    # Energy in Wh (2 values, n = lower bit)
    # E000 000n: 10^(n+5) Wh (covers 0x00-0x01)
    # Spec: 10^(n-1) MWh, normalized: 1 MWh = 10^6 Wh
    _TrueFieldDescriptor(  # ENERGY_MWH
        code=0b00000000,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ENERGY,
        value_unit=ValueUnit.WH,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_5,
    ),
    # Reactive energy in varh (2 values, n = lower bit)
    # E000 001n: 10^(n+3) varh (covers 0x02-0x03)
    # Spec: 10^n kvarh, normalized: 1 kvarh = 10^3 varh
    _TrueFieldDescriptor(  # REACTIVE_ENERGY_KVARH
        code=0b00000010,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.REACTIVE_ENERGY,
        value_unit=ValueUnit.VARH,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_2,
    ),
    # Apparent energy in VAh (2 values, n = lower bit)
    # E000 010n: 10^(n+3) VAh (covers 0x04-0x05)
    # Spec: 10^n kVAh, normalized: 1 kVAh = 10^3 VAh
    _TrueFieldDescriptor(  # APPARENT_ENERGY_KVAH
        code=0b00000100,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.APPARENT_ENERGY,
        value_unit=ValueUnit.VAH,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_2,
    ),
    # 0x06-0x07: Reserved
    # Energy in J (2 values, n = lower bit)
    # E000 100n: 10^(n+8) J (covers 0x08-0x09)
    # Spec: 10^(n-1) GJ, normalized: 1 GJ = 10^9 J
    _TrueFieldDescriptor(  # ENERGY_GJ
        code=0b00001000,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ENERGY,
        value_unit=ValueUnit.J,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_8,
    ),
    # 0x0A-0x0B: Reserved
    # Energy in cal (4 values, nn = lower 2 bits)
    # E000 11nn: 10^(nn+5) cal (covers 0x0C-0x0F)
    # Spec: 10^(nn-1) MCal, normalized: 1 MCal = 10^6 cal
    _TrueFieldDescriptor(  # ENERGY_MCAL
        code=0b00001100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ENERGY,
        value_unit=ValueUnit.CAL,
        value_transformer=ValueTransformer.MULT_10_POW_NN_PLUS_5,
    ),
    # ==========================================================================
    # Volume and Mass - Extended Range (normalized to base units)
    # ==========================================================================
    # Volume in m³ (2 values, n = lower bit)
    # E001 000n: 10^(n+2) m³ (covers 0x10-0x11)
    _TrueFieldDescriptor(  # VOLUME_M3
        code=0b00010000,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLUME,
        value_unit=ValueUnit.M3,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_2,
    ),
    # 0x12-0x13: Reserved
    # Reactive power in VAR (4 values, nn = lower 2 bits)
    # E001 01nn: 10^nn VAR (covers 0x14-0x17)
    # Spec: 10^(nn-3) kVAR, normalized: 1 kVAR = 10^3 VAR
    _TrueFieldDescriptor(  # REACTIVE_POWER_KVAR
        code=0b00010100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.REACTIVE_POWER,
        value_unit=ValueUnit.VAR,
        value_transformer=ValueTransformer.MULT_10_POW_NN,
    ),
    # Mass in kg (2 values, n = lower bit)
    # E001 100n: 10^(n+5) kg (covers 0x18-0x19)
    # Spec: 10^(n+2) t, normalized: 1 t = 10^3 kg
    _TrueFieldDescriptor(  # MASS_T
        code=0b00011000,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.MASS,
        value_unit=ValueUnit.KG,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_5,
    ),
    # Relative humidity (2 values, n = lower bit)
    # E001 101n: 10^(n-1) % (covers 0x1A-0x1B)
    _TrueFieldDescriptor(  # RELATIVE_HUMIDITY
        code=0b00011010,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.RELATIVE_HUMIDITY,
        value_unit=ValueUnit.PERCENT,
        value_transformer=ValueTransformer.MULT_10_POW_N_MINUS_1,
    ),
    # 0x1C-0x1F: Reserved
    # ==========================================================================
    # Non-Metric Units
    # ==========================================================================
    # E010 0000: Volume feet³ (single value, no exponent)
    _TrueFieldDescriptor(  # VOLUME_FEET3
        code=0b00100000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLUME,
        value_unit=ValueUnit.FEET3,
        value_transformer=ValueTransformer.MULT_1,
    ),
    # E010 0001: Volume 0.1 feet³ (single value, no exponent)
    _TrueFieldDescriptor(  # VOLUME_01FEET3
        code=0b00100001,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLUME,
        value_unit=ValueUnit.FEET3,
        value_transformer=ValueTransformer.MULT_0_1,
    ),
    # 0x22-0x27: Reserved
    # ==========================================================================
    # Power - Extended Range (normalized to base units)
    # ==========================================================================
    # Power in W (2 values, n = lower bit)
    # E010 100n: 10^(n+5) W (covers 0x28-0x29)
    # Spec: 10^(n-1) MW, normalized: 1 MW = 10^6 W
    _TrueFieldDescriptor(  # POWER_MW
        code=0b00101000,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.POWER,
        value_unit=ValueUnit.W,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_5,
    ),
    # Phase angles (single values, no exponent)
    # E010 1010: Phase U-U (voltage to voltage) 0.1°
    _TrueFieldDescriptor(  # PHASE_U_U
        code=0b00101010,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.PHASE_ANGLE_U_U,
        value_unit=ValueUnit.DEGREE,
        value_transformer=ValueTransformer.MULT_0_1,
    ),
    # E010 1011: Phase U-I (voltage to current) 0.1°
    _TrueFieldDescriptor(  # PHASE_U_I
        code=0b00101011,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.PHASE_ANGLE_U_I,
        value_unit=ValueUnit.DEGREE,
        value_transformer=ValueTransformer.MULT_0_1,
    ),
    # Frequency in Hz (4 values, nn = lower 2 bits)
    # E010 11nn: 10^(nn-3) Hz (covers 0x2C-0x2F)
    _TrueFieldDescriptor(  # FREQUENCY_HZ
        code=0b00101100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.FREQUENCY,
        value_unit=ValueUnit.HZ,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # Power in J/h (2 values, n = lower bit)
    # E011 000n: 10^(n+8) J/h (covers 0x30-0x31)
    # Spec: 10^(n-1) GJ/h, normalized: 1 GJ = 10^9 J
    _TrueFieldDescriptor(  # POWER_GJH
        code=0b00110000,
        mask=0b01111110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.POWER,
        value_unit=ValueUnit.J_H,
        value_transformer=ValueTransformer.MULT_10_POW_N_PLUS_8,
    ),
    # 0x32-0x33: Reserved
    # Apparent power in VA (4 values, nn = lower 2 bits)
    # E011 01nn: 10^nn VA (covers 0x34-0x37)
    # Spec: 10^(nn-3) kVA, normalized: 1 kVA = 10^3 VA
    _TrueFieldDescriptor(  # APPARENT_POWER_KVA
        code=0b00110100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.APPARENT_POWER,
        value_unit=ValueUnit.VA,
        value_transformer=ValueTransformer.MULT_10_POW_NN,
    ),
    # 0x38-0x57: Reserved
    # 0x58-0x67: Reserved
    # ==========================================================================
    # HCA Rating Factors
    # ==========================================================================
    # E110 1000: Resulting rating factor, K (single value, no exponent)
    _TrueFieldDescriptor(  # RATING_FACTOR_K
        code=0b01101000,
        value_description=ValueDescription.RATING_FACTOR_K,
        value_transformer=ValueTransformer.MULT_2_POW_MINUS_12,
    ),
    # E110 1001: Thermal output rating factor, Kq (single value, no exponent)
    _TrueFieldDescriptor(  # RATING_FACTOR_KQ
        code=0b01101001,
        value_description=ValueDescription.RATING_FACTOR_KQ,
        value_transformer=ValueTransformer.MULT_1,
    ),
    # E110 1010: Thermal coupling rating factor overall, Kc (single value, no exponent)
    _TrueFieldDescriptor(  # RATING_FACTOR_KC
        code=0b01101010,
        value_description=ValueDescription.RATING_FACTOR_KC,
        value_transformer=ValueTransformer.MULT_2_POW_MINUS_12,
    ),
    # E110 1011: Thermal coupling rating factor room side, Kcr (single value, no exponent)
    _TrueFieldDescriptor(  # RATING_FACTOR_KCR
        code=0b01101011,
        value_description=ValueDescription.RATING_FACTOR_KCR,
        value_transformer=ValueTransformer.MULT_2_POW_MINUS_12,
    ),
    # E110 1100: Thermal coupling rating factor heater side, Kch (single value, no exponent)
    _TrueFieldDescriptor(  # RATING_FACTOR_KCH
        code=0b01101100,
        value_description=ValueDescription.RATING_FACTOR_KCH,
        value_transformer=ValueTransformer.MULT_2_POW_MINUS_12,
    ),
    # E110 1101: Low temperature rating factor, Kt (single value, no exponent)
    _TrueFieldDescriptor(  # RATING_FACTOR_KT
        code=0b01101101,
        value_description=ValueDescription.RATING_FACTOR_KT,
        value_transformer=ValueTransformer.MULT_2_POW_MINUS_12,
    ),
    # E110 1110: Display output scaling factor, KD (single value, no exponent)
    _TrueFieldDescriptor(  # RATING_FACTOR_KD
        code=0b01101110,
        value_description=ValueDescription.RATING_FACTOR_KD,
        value_transformer=ValueTransformer.MULT_2_POW_MINUS_12,
    ),
    # 0x6F: Reserved
    # 0x70-0x73: Reserved (E111 00nn),
    # ==========================================================================
    # Temperature Limit
    # ==========================================================================
    # Cold/warm temperature limit (4 values, nn = lower 2 bits)
    # E111 01nn: 10^(nn-3) °C (covers 0x74-0x77)
    _TrueFieldDescriptor(  # TEMPERATURE_LIMIT
        code=0b01110100,
        mask=0b01111100,
        value_description=ValueDescription.TEMPERATURE_LIMIT,
        value_unit=ValueUnit.CELSIUS,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # ==========================================================================
    # Cumulative Maximum Power
    # ==========================================================================
    # Cumulative maximum power (8 values, nnn = lower 3 bits)
    # E111 1nnn: 10^(nnn-3) W (covers 0x78-0x7F)
    _TrueFieldDescriptor(  # CUM_MAX_POWER_W
        code=0b01111000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.CUMULATIVE_MAX_POWER,
        value_unit=ValueUnit.W,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_3,
    ),
)


# =============================================================================
# VIF Lookup Tables (EN 13757-3:2018, Tables 10-16)
# =============================================================================

# _PrimaryFieldTable
_PrimaryFieldTable: tuple[_AbstractFieldDescriptor, ...] = (
    # ==========================================================================
    # Cumulative Quantities
    # ==========================================================================
    # Energy ranges (8 values, nnn = lower 3 bits)
    # E000 0nnn: 10^(nnn-3) Wh (covers 0x00-0x07)
    _TrueFieldDescriptor(  # ENERGY_WH
        code=0b00000000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ENERGY,
        value_unit=ValueUnit.WH,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_3,
    ),
    # E000 1nnn: 10^(nnn) J (covers 0x08-0x0F)
    _TrueFieldDescriptor(  # ENERGY_J
        code=0b00001000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ENERGY,
        value_unit=ValueUnit.J,
        value_transformer=ValueTransformer.MULT_10_POW_NNN,
    ),
    # Volume (8 values, nnn = lower 3 bits)
    # E001 0nnn: 10^(nnn-6) m³ (covers 0x10-0x17)
    _TrueFieldDescriptor(  # VOLUME
        code=0b00010000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLUME,
        value_unit=ValueUnit.M3,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_6,
    ),
    # Mass (8 values, nnn = lower 3 bits)
    # E001 1nnn: 10^(nnn-3) kg (covers 0x18-0x1F)
    _TrueFieldDescriptor(  # MASS
        code=0b00011000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.MASS,
        value_unit=ValueUnit.KG,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_3,
    ),
    # ==========================================================================
    # Temporal - Durations (Optimized with nn unit encoding)
    # ==========================================================================
    # E010 00nn: On time (4 values, nn encodes unit: 00=s, 01=min, 10=h, 11=d)
    # Covers 0x20-0x23
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # ON_TIME
        code=0b00100000,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ON_TIME,
    ),
    # E010 01nn: Operating time (4 values, nn encodes unit)
    # Covers 0x24-0x27
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # OPERATING_TIME
        code=0b00100100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.OPERATING_TIME,
    ),
    # ==========================================================================
    # Instantaneous - Power
    # ==========================================================================
    # Power (8 values, nnn = lower 3 bits)
    # E010 1nnn: 10^(nnn-3) W (covers 0x28-0x2F)
    _TrueFieldDescriptor(  # POWER_W
        code=0b00101000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.POWER,
        value_unit=ValueUnit.W,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_3,
    ),
    # E011 0nnn: 10^(nnn) J/h (covers 0x30-0x37)
    _TrueFieldDescriptor(  # POWER_JH
        code=0b00110000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.POWER,
        value_unit=ValueUnit.J_H,
        value_transformer=ValueTransformer.MULT_10_POW_NNN,
    ),
    # ==========================================================================
    # Instantaneous - Flow
    # ==========================================================================
    # Volume flow (8 values, nnn = lower 3 bits)
    # E011 1nnn: 10^(nnn-6) m³/h (covers 0x38-0x3F)
    # Spec: 10^(nnn-6) m³/h, normalized: 1 m³/h = (1/3600) m³/s
    _TrueFieldDescriptor(  # VOLUME_FLOW
        code=0b00111000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLUME_FLOW,
        value_unit=ValueUnit.M3_S,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_6_DIV_3600,
    ),
    # E100 0nnn: 10^(nnn-7) m³/min (covers 0x40-0x47)
    # Spec: 10^(nnn-7) m³/min, normalized: 1 m³/min = (1/60) m³/s
    _TrueFieldDescriptor(  # VOLUME_FLOW_MIN
        code=0b01000000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLUME_FLOW,
        value_unit=ValueUnit.M3_S,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_7_DIV_60,
    ),
    # E100 1nnn: 10^(nnn-9) m³/s (covers 0x48-0x4F)
    _TrueFieldDescriptor(  # VOLUME_FLOW_SEC
        code=0b01001000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.VOLUME_FLOW,
        value_unit=ValueUnit.M3_S,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_9,
    ),
    # Mass flow (8 values, nnn = lower 3 bits)
    # E101 0nnn: 10^(nnn-3) kg/h (covers 0x50-0x57)
    # Spec: 10^(nnn-3) kg/h, normalized: 1 kg/h = (1/3600) kg/s
    _TrueFieldDescriptor(  # MASS_FLOW
        code=0b01010000,
        mask=0b01111000,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.MASS_FLOW,
        value_unit=ValueUnit.KG_S,
        value_transformer=ValueTransformer.MULT_10_POW_NNN_MINUS_3_DIV_3600,
    ),
    # ==========================================================================
    # Instantaneous - Temperature
    # ==========================================================================
    # Temperature (4 values, nn = lower 2 bits)
    # E101 10nn: 10^(nn-3) °C (covers 0x58-0x5B)
    _TrueFieldDescriptor(  # FLOW_TEMPERATURE
        code=0b01011000,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.FLOW_TEMPERATURE,
        value_unit=ValueUnit.CELSIUS,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # E101 11nn: 10^(nn-3) °C (covers 0x5C-0x5F)
    _TrueFieldDescriptor(  # RETURN_TEMPERATURE
        code=0b01011100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.RETURN_TEMPERATURE,
        value_unit=ValueUnit.CELSIUS,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # E110 00nn: 10^(nn-3) K (covers 0x60-0x63)
    _TrueFieldDescriptor(  # TEMPERATURE_DIFF
        code=0b01100000,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.TEMPERATURE_DIFFERENCE,
        value_unit=ValueUnit.KELVIN,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # E110 01nn: 10^(nn-3) °C (covers 0x64-0x67)
    _TrueFieldDescriptor(  # EXTERNAL_TEMPERATURE
        code=0b01100100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.EXTERNAL_TEMPERATURE,
        value_unit=ValueUnit.CELSIUS,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # ==========================================================================
    # Instantaneous - Pressure
    # ==========================================================================
    # Pressure (4 values, nn = lower 2 bits)
    # E110 10nn: 10^(nn-3) bar (covers 0x68-0x6B)
    _TrueFieldDescriptor(  # PRESSURE
        code=0b01101000,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.PRESSURE,
        value_unit=ValueUnit.BAR,
        value_transformer=ValueTransformer.MULT_10_POW_NN_MINUS_3,
    ),
    # ==========================================================================
    # Temporal - Date/Time
    # ==========================================================================
    # E110 1100: Date (single value, no range)
    _TrueFieldDescriptor(  # DATE
        code=0b01101100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DATE,
        data_rules=DataRules.Requires.TEMPORAL_G,  # Type G_2 (Date CP16)
    ),
    # E110 1101: Date and time (single value, no range)
    # Note: Actual format depends on DIF data field type (type F, I, J, or M)
    _TrueFieldDescriptor(  # DATE_TIME
        code=0b01101101,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.DATE_TIME,
        data_rules=DataRules.Requires.TEMPORAL_FIJM,  # Date/Time types (no G_2)
    ),
    # ==========================================================================
    # HCA
    # ==========================================================================
    # E110 1110: Units for HCA (single value, no range)
    _TrueFieldDescriptor(  # HCA_UNITS
        code=0b01101110,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.UNITS_FOR_HCA,
    ),
    # ==========================================================================
    # Temporal - Durations (Continued with nn unit encoding)
    # ==========================================================================
    # E111 00nn: Averaging duration (4 values, nn encodes unit)
    # Covers 0x70-0x73
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # AVERAGING_DURATION
        code=0b01110000,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.AVERAGING_DURATION,
    ),
    # E111 01nn: Actuality duration (4 values, nn encodes unit)
    # Covers 0x74-0x77
    # Note: Unit is variable based on nn bits - decoded at runtime
    _TrueFieldDescriptor(  # ACTUALITY_DURATION
        code=0b01110100,
        mask=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ACTUALITY_DURATION,
    ),
    # ==========================================================================
    # Identification
    # ==========================================================================
    # E111 1000: Fabrication no (single value, no range)
    _TrueFieldDescriptor(  # FABRICATION_NO
        code=0b01111000,
        # Not a physical measurement
        # NO ALLOWS_* flags - identifiers are immutable, can't be modified
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.FABRICATION_NO,
    ),
    # E111 1001: Enhanced identification (single value, no range)
    _TrueFieldDescriptor(  # ENHANCED_ID
        code=0b01111001,
        # Not a physical measurement
        # NO ALLOWS_* flags - identifiers are immutable
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ENHANCED_IDENTIFICATION,
    ),
    # E111 1010: Address (single value, no range)
    _TrueFieldDescriptor(  # ADDRESS
        code=0b01111010,
        # Not a physical measurement
        # NO ALLOWS_* flags - identifiers are immutable
        direction=CommunicationDirection.SLAVE_TO_MASTER,
        value_description=ValueDescription.ADDRESS,
        data_rules=DataRules.Requires.ADDRESS_C,  # Wired M-Bus: 1 byte unsigned address
    ),
    # ==========================================================================
    # Special and Extension Codes
    # ==========================================================================
    # E111 1011: First extension table (Table 14) - only 0xFB
    # Extension pointer - requires VIFE to follow with actual VIF code
    _ExtensionFieldDescriptor(  # EXTENSION_FB
        code=0b11111011,
        extension_table=_FirstExtensionFieldTable,
    ),
    # E111 1100: Plain text ASCII string containing unit follows VIB (covers 0x7C)
    _PlainTextFieldDescriptor(  # PLAIN_TEXT
        code=0b01111100,
        direction=CommunicationDirection.SLAVE_TO_MASTER,
    ),
    # E111 1101: Second extension table (Table 12) - only 0xFD
    # Extension pointer - requires VIFE to follow with actual VIF code
    _ExtensionFieldDescriptor(  # EXTENSION_FD
        code=0b11111101,
        extension_table=_SecondExtensionFieldTable,
    ),
    # E110 1111: Third extension table (reserved) - only 0xEF
    # Not implemented - reserved for future use
    # E111 1110: Any VIF (covers 0x7E)
    # TODO: Must only be used with DIF 0x08 (readout selection)
    _ReadoutAnyFieldDescriptor(  # ANY_VIF
        code=0b01111110,
        direction=CommunicationDirection.MASTER_TO_SLAVE,
    ),
    # E111 1111: Manufacturer specific (covers 0x7F)
    _ManufacturerFieldDescriptor(  # MANUFACTURER_SPECIFIC
        code=0b01111111,
    ),
)


# =============================================================================
# VIF/VIFE Helper Functions
# =============================================================================


@lru_cache(maxsize=128)
def _find_field_descriptor(
    direction: CommunicationDirection,
    field_code: int,
    field_table: tuple[_AbstractFieldDescriptor, ...],
) -> _AbstractFieldDescriptor:
    """Find the matching field descriptor for a VIF/VIFE field code.

    Args:
        direction: Communication direction (MASTER_TO_SLAVE or SLAVE_TO_MASTER)
        field_code: The VIF/VIFE byte value (0x00-0xFF)
        field_table: The table to search in

    Returns:
        The matching field descriptor

    Raises:
        ValueError: If no matching descriptor is found in the table
    """
    for field_descriptor in field_table:
        if direction in field_descriptor.direction and (field_code & field_descriptor.mask) == field_descriptor.code:
            return field_descriptor

    raise ValueError(f"VIF/VIFE code 0x{field_code:02X} for direction {direction.name} not found in VIF/VIFE tables")


def _decode_ascii_unit(data: bytes) -> str:
    """Decode reversed ASCII text string (Plain Text VIF format).

    Decodes ASCII text that is transmitted with the rightmost character first,
    as specified for Plain Text VIF (VIF=7Ch/FCh) in M-Bus.

    Reference: EN 13757-3:2018, Annex C.2 (Plain text units)

    Args:
        data: Raw bytes in transmission order (rightmost character first)

    Returns:
        Decoded text string (in correct reading order)

    Raises:
        UnicodeDecodeError: If data contains non-ASCII bytes (≥ 0x80)
    """
    return bytes(reversed(data)).decode("ascii")


def _encode_ascii_unit(text: str) -> tuple[int, ...]:
    """Encode text string to reversed ASCII bytes (Plain Text VIF format).

    Encodes ASCII text for transmission with the rightmost character first,
    as specified for Plain Text VIF (VIF=7Ch/FCh) in M-Bus.

    Reference: EN 13757-3:2018, Annex C.2 (Plain text units)

    Args:
        text: Text string to encode (in correct reading order)

    Returns:
        Tuple of integers in transmission order (rightmost character first)

    Raises:
        UnicodeEncodeError: If text contains non-ASCII characters
    """
    return tuple(reversed(text.encode("ascii")))


# =============================================================================
# VIF/VIFE Class - Main wrapper for VIF/VIFE interpretation
# =============================================================================


class VIF:
    """Base class for Value Information Field (VIF).

    The VIF is the first byte in a VIF/VIFE chain and specifies the unit,
    value description, and data rules for the associated data value.

    This class uses a factory pattern (__new__) to automatically instantiate
    the correct subclass (TrueVIF, PointerVIF, or ManufacturerVIF) based on
    the field_code and its descriptor type.

    Attributes:
        _field_code: The VIF byte value (0x00-0xFF)
        _field_descriptor: The descriptor metadata for this VIF
        direction: Communication direction (MASTER_TO_SLAVE or SLAVE_TO_MASTER)
        _chain_position: Position in chain (0 for VIF)
        prev_field: Previous field in chain (None for VIF)
        next_field: Next VIFE in chain (None if last_field is True)
        last_field: True if extension bit is 0 (no more VIFE bytes follow)

    Reference: EN 13757-3:2018, section 6.4, Tables 10-16
    """

    _field_code: int

    direction: CommunicationDirection

    _chain_position: int = 0
    prev_field: VIF | VIFE | None = None
    next_field: VIFE | None = None

    last_field: bool

    _next_table: tuple[_AbstractFieldDescriptor, ...] | None = None

    def __new__(cls, direction: CommunicationDirection, field_code: int) -> VIF:
        field_descriptor = _find_field_descriptor(direction, field_code, _PrimaryFieldTable)

        if isinstance(field_descriptor, _TrueFieldDescriptor):
            if isinstance(field_descriptor, _PlainTextFieldDescriptor):
                return object.__new__(PlainTextVIF)
            return object.__new__(TrueVIF)

        if isinstance(field_descriptor, _ExtensionFieldDescriptor):
            return object.__new__(ExtensionVIF)

        if isinstance(field_descriptor, _ManufacturerFieldDescriptor):
            return object.__new__(ManufacturerVIF)

        if isinstance(field_descriptor, _ReadoutAnyFieldDescriptor):
            return object.__new__(ReadoutAnyVIF)

        # Should never reach here - field descriptor can only be one of the above types
        raise AssertionError(f"Field descriptor type {type(field_descriptor).__name__} not recognized")

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        if direction is CommunicationDirection.BIDIRECTIONAL:
            raise ValueError("VIF/VIFE communication direction cannot be BIDIRECTIONAL")

        self.direction = direction

        self._field_code = field_code

        self.last_field = self._is_last_field()

    def _is_last_field(self) -> bool:
        """Check if this is the last field in the VIF/VIFE chain.

        Returns:
            True if extension bit (bit 7) is 0, meaning no more VIFE bytes follow.
        """
        return self._field_code & VIF_EXTENSION_BIT_MASK == 0

    def create_next_vife(self, field_code: int) -> VIFE:
        """Create the next VIFE in the chain.

        Args:
            field_code: The VIFE byte value (0x00-0xFF)

        Returns:
            VIFE instance (automatically typed to correct subclass)

        Raises:
            ValueError: If this field is already marked as last_field
        """
        return VIFE(self.direction, field_code, self)

    def to_bytes(self) -> bytes:
        """Convert VIF field to bytes representation.

        Returns:
            Single byte containing the VIF field code
        """
        return bytes([self._field_code])

    @staticmethod
    async def from_bytes_async(
        direction: CommunicationDirection,
        get_next_bytes: Callable[[int], Awaitable[bytes]],
    ) -> tuple[VIF, *tuple[VIFE, ...]]:
        """Parse a complete VIF/VIFE chain from bytes asynchronously.

        Reads one VIF byte, then continues reading VIFE bytes as long as the
        extension bit (bit 7) is set in the current field.

        Args:
            direction: Communication direction for the VIF/VIFE chain
            get_next_bytes: Async function to read the next n bytes from stream

        Returns:
            Tuple of (VIF, *VIFEs) representing the complete chain

        Raises:
            ValueError: If byte reading fails or field descriptor not found
        """
        vif_bytes = await get_next_bytes(1)

        if len(vif_bytes) != 1:
            raise ValueError("Expected exactly one byte for VIF")

        vif: VIF = VIF(direction, vif_bytes[0])

        vife: list[VIFE] = []

        current_field: VIF | VIFE = vif
        while not current_field.last_field:
            vife_bytes = await get_next_bytes(1)

            if len(vife_bytes) != 1:
                raise ValueError("Expected exactly one byte for VIFE")

            current_field = current_field.create_next_vife(vife_bytes[0])
            vife.append(current_field)

        return (vif, *vife)


class TrueVIF(VIF):
    """VIF that defines unit and value description.

    TrueVIF represents a VIF that directly specifies the physical unit,
    value description, and data rules for the associated data value.

    Attributes:
        value_description: Human-readable description of the value
        value_unit: Physical unit (Wh, m³, °C, etc.) or None for dimensionless
        value_transformer: Optional transformer for value conversion
        data_rules: Data type requirements and constraints

    Reference: EN 13757-3:2018, Table 10 (Primary VIFs)
    """

    value_description: ValueDescription | None
    value_unit: ValueUnit | str | None
    value_transformer: ValueTransformer | None
    data_rules: DataRules.Requires

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        super().__init__(direction, field_code)

        field_descriptor = _find_field_descriptor(direction, field_code, _PrimaryFieldTable)

        # VIF.__new__ guarantees descriptor is _TrueFieldDescriptor
        assert isinstance(field_descriptor, _TrueFieldDescriptor), (
            f"TrueVIF used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self.value_description = field_descriptor.value_description

        self.value_unit = field_descriptor.value_unit

        self.value_transformer = field_descriptor.value_transformer

        self.data_rules = field_descriptor.data_rules

        self._next_table = _CombinableOrthogonalFieldTable


class ExtensionVIF(VIF):
    """VIF that points to an extension table.

    ExtensionVIF represents VIF codes like 0xFB and 0xFD that don't directly
    specify a unit/value, but instead point to an extension table where the
    following VIFE will be looked up.

    Reference: EN 13757-3:2018, Table 10 (codes 0xFB, 0xFD)
    """

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        super().__init__(direction, field_code)

        # ExtensionVIF cannot be the last field
        assert self.last_field is False, "ExtensionVIF cannot be the last field"

        field_descriptor = _find_field_descriptor(direction, field_code, _PrimaryFieldTable)

        # VIF.__new__ guarantees descriptor is _ExtensionFieldDescriptor
        assert isinstance(field_descriptor, _ExtensionFieldDescriptor), (
            f"ExtensionVIF used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self._next_table = field_descriptor.extension_table


class PlainTextVIF(TrueVIF):
    """TrueVIF for plain text ASCII string unit (code 0x7C).

    When present, an ASCII string describing the unit of the value
    follows after the VIB bytes in the data record.

    Reference: EN 13757-3:2018, Table 10 (code 0x7C)
    """

    _ascii_sequence: tuple[int, ...] | None = None

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        super().__init__(direction, field_code)

        field_descriptor = _find_field_descriptor(direction, field_code, _PrimaryFieldTable)

        # VIF.__new__ guarantees descriptor is _PlainTextFieldDescriptor
        assert isinstance(field_descriptor, _PlainTextFieldDescriptor), (
            f"PlainTextVIF used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

    def is_ascii_unit_set(self) -> bool:
        """Check if the ASCII unit string has been set."""
        return self._ascii_sequence is not None

    def set_ascii_unit(self, text: str) -> None:
        """Set the ASCII unit string for this PlainTextVIF.

        Args:
            text: Unit string to encode (e.g., "kWh", "m3")

        Raises:
            ValueError: If unit already set or text length not 1-255
            UnicodeEncodeError: If text contains non-ASCII characters
        """
        if self._ascii_sequence is not None:
            raise ValueError("ASCII unit already set in PlainTextVIF")

        ascii_sequence = _encode_ascii_unit(text)

        if not (0 < len(ascii_sequence) <= 255):
            raise ValueError(f"Length of encoded ASCII sequence invalid, is {len(ascii_sequence)}, must be 1-255")

        self._ascii_sequence = ascii_sequence

        self.value_unit = text

    def ascii_unit_to_bytes(self) -> bytes:
        """Convert ASCII unit to bytes for transmission.

        Returns:
            Length byte followed by reversed ASCII bytes

        Raises:
            ValueError: If ASCII unit not set
        """
        if self._ascii_sequence is None:
            raise ValueError("ASCII unit not set in PlainTextVIF")

        ascii_length = len(self._ascii_sequence)

        # Length should always be valid here when _ascii_sequence is set with set_ascii_unit or ascii_unit_from_bytes_async
        assert 0 < ascii_length <= 255, f"Invalid ASCII length, is {ascii_length}, must be 1-255"

        return bytes([ascii_length, *self._ascii_sequence])

    async def ascii_unit_from_bytes_async(self, get_next_bytes: Callable[[int], Awaitable[bytes]]) -> None:
        """Parse ASCII unit from byte stream.

        Args:
            get_next_bytes: Async function to read bytes from stream

        Raises:
            ValueError: If unit already set or invalid length/data
            UnicodeDecodeError: If data contains non-ASCII bytes
        """
        if self._ascii_sequence is not None:
            raise ValueError("ASCII unit already set in PlainTextVIF")

        ascii_length_bytes = await get_next_bytes(1)

        if len(ascii_length_bytes) != 1:
            raise ValueError("Expected exactly one byte for ASCII length")

        ascii_length = ascii_length_bytes[0]

        if not (0 < ascii_length <= 255):
            raise ValueError(f"Invalid ASCII length, is {ascii_length}, must be 1-255")

        ascii_string_bytes = await get_next_bytes(ascii_length)

        if len(ascii_string_bytes) != ascii_length:
            raise ValueError(f"Expected exactly {ascii_length} bytes for ASCII text")

        self.value_unit = _decode_ascii_unit(ascii_string_bytes)

        self._ascii_sequence = tuple(ascii_string_bytes)


class ReadoutAnyVIF(VIF):
    """VIF for global readout request (code 0x7E).

    Used by master to request readout of all data from the slave device.
    This VIF must only be used with DIF code 0x08 (readout selection).

    Reference: EN 13757-3:2018, Table 10 (code 0x7E)
    """

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        super().__init__(direction, field_code)

        field_descriptor = _find_field_descriptor(direction, field_code, _PrimaryFieldTable)

        # VIF.__new__ guarantees descriptor is _ReadoutAnyFieldDescriptor
        assert isinstance(field_descriptor, _ReadoutAnyFieldDescriptor), (
            f"ReadoutAnyVIF used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self._next_table = _CombinableOrthogonalFieldTable


class ManufacturerVIF(VIF):
    """VIF for manufacturer-specific data (code 0x7F).

    Indicates that all following data in the record is manufacturer-specific
    and cannot be interpreted by standard M-Bus parsers.

    Reference: EN 13757-3:2018, Table 10 (code 0x7F)
    """

    def __init__(self, direction: CommunicationDirection, field_code: int) -> None:
        super().__init__(direction, field_code)

        field_descriptor = _find_field_descriptor(direction, field_code, _PrimaryFieldTable)

        # VIF.__new__ guarantees descriptor is _ManufacturerFieldDescriptor
        assert isinstance(field_descriptor, _ManufacturerFieldDescriptor), (
            f"ManufacturerVIF used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )


class VIFE(VIF):
    """Base class for Value Information Field Extension (VIFE).

    VIFE bytes extend or modify the VIF with additional information. VIFEs can:
    - Define a new "true VIF" semantics (after ExtensionVIF)
    - Modify the previous VIF (multipliers, time divisors, etc.)
    - Point to another extension table
    - Provide manufacturer-specific extensions

    This class uses a factory pattern to instantiate the correct subclass
    based on the field_code and the previous field's descriptor type.

    Reference: EN 13757-3:2018, section 6.4, Tables 12-16
    """

    def __new__(cls, direction: CommunicationDirection, field_code: int, prev_field: VIF | VIFE) -> VIFE:
        # Determine which table to use based on previous field
        if isinstance(prev_field, (ManufacturerVIF, ManufacturerVIFE)):
            return object.__new__(ManufacturerVIFE)

        field_descriptor = _find_field_descriptor(direction, field_code, prev_field._next_table)

        if isinstance(prev_field, ExtensionCombinableVIFE):
            if isinstance(field_descriptor, _CombinableFieldDescriptor):
                return object.__new__(CombinableVIFE)

        elif isinstance(prev_field, ExtensionVIF):
            if isinstance(field_descriptor, _TrueFieldDescriptor):
                return object.__new__(TrueVIFE)
            elif isinstance(field_descriptor, _ExtensionFieldDescriptor):
                return object.__new__(ExtensionVIFE)

        elif isinstance(prev_field, ExtensionVIFE):
            if isinstance(field_descriptor, _TrueFieldDescriptor):
                return object.__new__(TrueVIFE)

        else:
            if isinstance(field_descriptor, _CombinableFieldDescriptor):
                return object.__new__(CombinableVIFE)
            elif isinstance(field_descriptor, _ExtensionFieldDescriptor):
                return object.__new__(ExtensionCombinableVIFE)
            elif isinstance(field_descriptor, _ActionFieldDescriptor):
                return object.__new__(ActionVIFE)
            elif isinstance(field_descriptor, _ErrorFieldDescriptor):
                return object.__new__(ErrorVIFE)
            elif isinstance(field_descriptor, _ManufacturerFieldDescriptor):
                return object.__new__(ManufacturerVIFE)

        # Should never reach here - invalid VIFE chain
        raise AssertionError(
            f"Field descriptor type {type(field_descriptor).__name__} not recognized for VIFE after {type(prev_field).__name__}"
        )

    def __init__(self, direction: CommunicationDirection, field_code: int, prev_field: VIF | VIFE) -> None:
        if prev_field.last_field:
            raise ValueError("Cannot extend VIF/VIFE chain past last field")

        if prev_field.next_field is not None:
            raise ValueError("Previous field already has a next field assigned")

        if prev_field._chain_position >= VIFE_MAXIMUM_CHAIN_LENGTH:
            raise ValueError("Exceeded maximum VIFE chain length")

        self.prev_field = prev_field
        self.prev_field.next_field = self

        self._chain_position = self.prev_field._chain_position + 1

        super().__init__(direction, field_code)

        if self.prev_field.direction is not self.direction:
            raise ValueError("VIFE communication direction does not match previous field communication direction")


class TrueVIFE(VIFE):
    """VIFE with "true VIF" semantics.

    TrueVIFE appears after an ExtensionVIF and defines a complete unit/value
    description like a TrueVIF does.

    Attributes:
        value_description: Human-readable description of the value
        value_unit: Physical unit (Wh, m³, °C, etc.) or None for dimensionless
        value_transformer: Optional transformer for value conversion
        data_rules: Data type requirements and constraints

    Reference: EN 13757-3:2018, Tables 12-13 (First/Second extension tables)
    """

    value_description: ValueDescription | None
    value_unit: ValueUnit | None
    value_transformer: ValueTransformer | None
    data_rules: DataRules.Requires

    def __init__(
        self, direction: CommunicationDirection, field_code: int, prev_field: ExtensionVIF | ExtensionVIFE
    ) -> None:
        super().__init__(direction, field_code, prev_field)

        # VIFE.__new__ guarantees prev_field is the correct type
        assert isinstance(self.prev_field, (ExtensionVIF, ExtensionVIFE)), (
            f"TrueVIFE cannot follow {type(self.prev_field).__name__}"
        )

        # Previous field always has a next table defined at this point
        assert self.prev_field._next_table is not None, "Previous field has no next table defined"

        field_descriptor = _find_field_descriptor(direction, field_code, self.prev_field._next_table)

        # VIFE.__new__ guarantees descriptor is _TrueFieldDescriptor
        assert isinstance(field_descriptor, _TrueFieldDescriptor), (
            f"TrueVIFE used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self.value_description = field_descriptor.value_description

        self.value_unit = field_descriptor.value_unit

        self.value_transformer = field_descriptor.value_transformer

        self.data_rules = field_descriptor.data_rules

        self._next_table = _CombinableOrthogonalFieldTable


class ExtensionVIFE(VIFE):
    """VIFE that points to another extension table.

    ExtensionVIFE represents VIFE codes that point to another table for the
    next VIFE in the chain.

    Reference: EN 13757-3:2018, Table 12 (Second extension table, code 0xFD)
    """

    def __init__(self, direction: CommunicationDirection, field_code: int, prev_field: ExtensionVIF) -> None:
        super().__init__(direction, field_code, prev_field)

        # ExtensionVIFE cannot be the last field
        assert self.last_field is False, "ExtensionVIFE cannot be the last field"

        # VIFE.__new__ guarantees prev_field is the correct type
        assert isinstance(self.prev_field, ExtensionVIF), (
            f"ExtensionVIFE cannot follow {type(self.prev_field).__name__}"
        )

        # Previous field always has a next table defined at this point
        assert self.prev_field._next_table is not None, "Previous field has no next table defined"

        field_descriptor = _find_field_descriptor(direction, field_code, self.prev_field._next_table)

        # VIFE.__new__ guarantees descriptor is _ExtensionFieldDescriptor
        assert isinstance(field_descriptor, _ExtensionFieldDescriptor), (
            f"ExtensionVIFE used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self._next_table = field_descriptor.extension_table


class CombinableVIFE(VIFE):
    """VIFE that modifies the TrueVIF.

    CombinableVIFE represents VIFE codes that modify or extend the semantics
    of the previous field (multiplicative factors, time divisors, phase info, etc.).

    Attributes:
        value_description_transformer: Transforms the value description
        value_unit_transformer: Transforms the value unit
        value_transformer: Transforms the value itself
        data_rules: Optional data type constraints

    Reference: EN 13757-3:2018, Tables 14-15 (Combinable orthogonal/extension)
    """

    value_description_transformer: ValueDescriptionTransformer | None
    value_unit_transformer: ValueUnitTransformer | None
    value_transformer: ValueTransformer | None
    data_rules: DataRules.Requires | None

    def __init__(
        self,
        direction: CommunicationDirection,
        field_code: int,
        prev_field: TrueVIF
        | ReadoutAnyVIF
        | TrueVIFE
        | CombinableVIFE
        | ExtensionCombinableVIFE
        | ActionVIFE
        | ErrorVIFE,
    ) -> None:
        super().__init__(direction, field_code, prev_field)

        # VIFE.__new__ guarantees prev_field is the correct type
        assert isinstance(
            self.prev_field,
            (
                TrueVIF,
                ReadoutAnyVIF,
                TrueVIFE,
                CombinableVIFE,
                ExtensionCombinableVIFE,
                ActionVIFE,
                ErrorVIFE,
            ),
        ), f"CombinableVIFE cannot follow {type(self.prev_field).__name__}"

        # Previous field always has a next table defined at this point
        assert self.prev_field._next_table is not None, "Previous field has no next table defined"

        field_descriptor = _find_field_descriptor(direction, field_code, self.prev_field._next_table)

        # VIFE.__new__ guarantees descriptor is _CombinableFieldDescriptor
        assert isinstance(field_descriptor, _CombinableFieldDescriptor), (
            f"CombinableVIFE used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self.value_description_transformer = field_descriptor.value_description_transformer
        self.value_unit_transformer = field_descriptor.value_unit_transformer
        self.value_transformer = field_descriptor.value_transformer
        self.data_rules = field_descriptor.data_rules

        self._next_table = _CombinableOrthogonalFieldTable


class ExtensionCombinableVIFE(VIFE):
    """VIFE that points to an extension table for combinable VIFEs (code 0xFC).

    ExtensionCombinableVIFE appears after a TrueVIF/TrueVIFE and points to
    the combinable extension table (_CombinableExtensionFieldTable).

    Reference: EN 13757-3:2018, Table 14 (code 0x7C/0xFC)
    """

    def __init__(
        self,
        direction: CommunicationDirection,
        field_code: int,
        prev_field: TrueVIF | ReadoutAnyVIF | TrueVIFE | CombinableVIFE | ActionVIFE | ErrorVIFE,
    ) -> None:
        super().__init__(direction, field_code, prev_field)

        # ExtensionCombinableVIFE cannot be the last field
        assert self.last_field is False, "ExtensionCombinableVIFE cannot be the last field"

        # VIFE.__new__ guarantees prev_field is the correct type
        assert isinstance(self.prev_field, (TrueVIF, ReadoutAnyVIF, TrueVIFE, CombinableVIFE, ActionVIFE, ErrorVIFE)), (
            f"ExtensionCombinableVIFE cannot follow {type(self.prev_field).__name__}"
        )

        # Previous field always has a next table defined at this point
        assert self.prev_field._next_table is not None, "Previous field has no next table defined"

        field_descriptor = _find_field_descriptor(direction, field_code, self.prev_field._next_table)

        # VIFE.__new__ guarantees descriptor is _ExtensionFieldDescriptor
        assert isinstance(field_descriptor, _ExtensionFieldDescriptor), (
            f"ExtensionCombinableVIFE used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self._next_table = field_descriptor.extension_table


class ActionVIFE(VIFE):
    """VIFE for object actions (master to slave).

    ActionVIFE specifies operations to perform on the value:
    - Write, Add, Subtract, OR, AND, XOR, AND NOT, Clear
    - Add entry, Delete entry, Delayed action, Freeze data
    - Add to readout-list, Delete from readout-list

    Attributes:
        action: Human-readable description of the action

    Reference: EN 13757-3:2018, Table 17 (page 26)
    """

    action: str

    def __init__(
        self,
        direction: CommunicationDirection,
        field_code: int,
        prev_field: TrueVIF | ReadoutAnyVIF | TrueVIFE | CombinableVIFE | ActionVIFE | ErrorVIFE,
    ) -> None:
        super().__init__(direction, field_code, prev_field)

        # VIFE.__new__ guarantees prev_field is the correct type
        assert isinstance(self.prev_field, (TrueVIF, ReadoutAnyVIF, TrueVIFE, CombinableVIFE, ActionVIFE, ErrorVIFE)), (
            f"ActionVIFE cannot follow {type(self.prev_field).__name__}"
        )

        # Previous field always has a next table defined at this point
        assert self.prev_field._next_table is not None, "Previous field has no next table defined"

        field_descriptor = _find_field_descriptor(direction, field_code, self.prev_field._next_table)

        # VIFE.__new__ guarantees descriptor is _ActionFieldDescriptor
        assert isinstance(field_descriptor, _ActionFieldDescriptor), (
            f"ActionVIFE used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self.action = field_descriptor.action

        self._next_table = _CombinableOrthogonalFieldTable


class ErrorVIFE(VIFE):
    """VIFE for record error codes (slave to master).

    ErrorVIFE indicates errors related to the record:
    - DIF errors: Too many DIFEs, storage/unit/tariff/function not implemented
    - VIF errors: Too many VIFEs, illegal VIF-Group/Exponent, VIF/DIF mismatch
    - Data errors: No data available, overflow, underflow, data error
    - Other errors: Premature end of record

    Attributes:
        error: Human-readable error description
        error_group: Category of error (DIF, VIF, Data, Other)

    Reference: EN 13757-3:2018, Table 18 (page 27)
    """

    error: str
    error_group: str

    def __init__(
        self,
        direction: CommunicationDirection,
        field_code: int,
        prev_field: TrueVIF | ReadoutAnyVIF | TrueVIFE | CombinableVIFE | ActionVIFE | ErrorVIFE,
    ) -> None:
        super().__init__(direction, field_code, prev_field)

        # VIFE.__new__ guarantees prev_field is the correct type
        assert isinstance(self.prev_field, (TrueVIF, ReadoutAnyVIF, TrueVIFE, CombinableVIFE, ActionVIFE, ErrorVIFE)), (
            f"ErrorVIFE cannot follow {type(self.prev_field).__name__}"
        )

        # Previous field always has a next table defined at this point
        assert self.prev_field._next_table is not None, "Previous field has no next table defined"

        field_descriptor = _find_field_descriptor(direction, field_code, self.prev_field._next_table)

        # VIFE.__new__ guarantees descriptor is _ErrorFieldDescriptor
        assert isinstance(field_descriptor, _ErrorFieldDescriptor), (
            f"ErrorVIFE used with incorrect field descriptor type {type(field_descriptor).__name__}"
        )

        self.error = field_descriptor.error
        self.error_group = field_descriptor.error_group

        self._next_table = _CombinableOrthogonalFieldTable


class ManufacturerVIFE(VIFE):
    """VIFE for manufacturer-specific extensions (code 0x7F/0xFF).

    ManufacturerVIFE indicates that this and all following VIFEs in the chain
    are manufacturer-specific and cannot be interpreted by standard M-Bus parsers.

    Reference: EN 13757-3:2018, Table 14 (code 0x7F/0xFF)
    """

    def __init__(
        self,
        direction: CommunicationDirection,
        field_code: int,
        prev_field: TrueVIF | TrueVIFE | CombinableVIFE | ReadoutAnyVIF | ManufacturerVIF | ManufacturerVIFE,
    ) -> None:
        super().__init__(direction, field_code, prev_field)

        # VIFE.__new__ guarantees prev_field is the correct type
        assert isinstance(
            self.prev_field, (TrueVIF, TrueVIFE, CombinableVIFE, ReadoutAnyVIF, ManufacturerVIF, ManufacturerVIFE)
        ), f"ManufacturerVIFE cannot follow {type(self.prev_field).__name__}"
