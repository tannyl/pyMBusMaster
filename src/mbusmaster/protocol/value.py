"""M-Bus temporal value representation.

This module contains the ValueTemporal class for representing all M-Bus
time/date types with support for:
- Component-based representation (Types F, G, I, J)
- Epoch-based representation (Type M)
- Recurring patterns
- Sub-second precision
- Timezone information

Reference: EN 13757-3:2018, Annex A
"""

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, time, timedelta, timezone
from enum import Enum, StrEnum, member


class ValueUnit(StrEnum):
    """SI units used in M-Bus VIF/VIFE values.

    Provides type-safe string constants for all units defined in EN 13757-3.
    Using StrEnum ensures unit strings are validated at definition time and
    provides better IDE support and type checking.

    Reference: EN 13757-3:2018, Tables 10-14
    """

    # Energy units
    WH = "Wh"  # Watt-hour (active energy)
    J = "J"  # Joule (energy)
    VARH = "VARh"  # Var-hour (reactive energy)
    VAH = "VAh"  # Volt-ampere-hour (apparent energy)
    CAL = "cal"  # Calorie

    # Volume units
    M3 = "m³"  # Cubic meter
    FEET3 = "ft³"  # Cubic feet

    # Mass units
    KG = "kg"  # Kilogram

    # Power units
    W = "W"  # Watt
    J_H = "J/h"  # Joule per hour
    VAR = "VAR"  # Var (reactive power)
    VA = "VA"  # Volt-ampere (apparent power)

    # Flow units
    M3_S = "m³/s"  # Cubic meter per second
    KG_S = "kg/s"  # Kilogram per second

    # Temperature units
    CELSIUS = "°C"  # Degrees Celsius
    KELVIN = "K"  # Kelvin (temperature difference)

    # Pressure units
    BAR = "bar"  # Bar

    # Other physical units
    PERCENT = "%"  # Percent (humidity, etc.)
    DEGREE = "°"  # Degree (angle)
    HZ = "Hz"  # Hertz (frequency)

    # Electrical units
    V = "V"  # Volt
    A = "A"  # Ampere

    # Signal strength
    DBM = "dBm"  # Decibel-milliwatts (RF signal level)


class ValueUnitTransformer(Enum):
    METRIC_TO_IMPERIAL = member(lambda unit, _code: "ft³" if unit == "m³" else unit)


class ValueDescription(StrEnum):
    """Human-readable descriptions for VIF/VIFE value types.

    Provides type-safe string constants for all VIF descriptions defined in EN 13757-3.
    Using StrEnum ensures consistency across the codebase and enables type checking.

    Reference: EN 13757-3:2018, Tables 10-14
    """

    # Energy and power
    ENERGY = "Energy"
    POWER = "Power"
    REACTIVE_ENERGY = "Reactive energy"
    REACTIVE_POWER = "Reactive power"
    APPARENT_ENERGY = "Apparent energy"
    APPARENT_POWER = "Apparent power"

    # Volume and flow
    VOLUME = "Volume"
    VOLUME_FLOW = "Volume flow"

    # Mass and mass flow
    MASS = "Mass"
    MASS_FLOW = "Mass flow"

    # Temperature
    FLOW_TEMPERATURE = "Flow temperature"
    RETURN_TEMPERATURE = "Return temperature"
    TEMPERATURE_DIFFERENCE = "Temperature difference"
    EXTERNAL_TEMPERATURE = "External temperature"
    TEMPERATURE_LIMIT = "Temperature limit"

    # Pressure
    PRESSURE = "Pressure"

    # Environmental
    RELATIVE_HUMIDITY = "Relative humidity"

    # Electrical measurements
    PHASE_ANGLE_U_U = "Phase U-U"
    PHASE_ANGLE_U_I = "Phase U-I"
    FREQUENCY = "Frequency"

    # Power (specific types)
    CUMULATIVE_MAX_POWER = "Cumulative max power"

    # HCA rating factors (specific descriptions from EN 13757-3:2018, Table 14)
    RATING_FACTOR_K = "Resulting rating factor, K"
    RATING_FACTOR_KQ = "Thermal output rating factor, Kq"
    RATING_FACTOR_KC = "Thermal coupling rating factor overall, Kc"
    RATING_FACTOR_KCR = "Thermal coupling rating factor room side, Kcr"
    RATING_FACTOR_KCH = "Thermal coupling rating factor heater side, Kch"
    RATING_FACTOR_KT = "Low temperature rating factor, Kt"
    RATING_FACTOR_KD = "Display output scaling factor, KD"

    # Time durations
    ON_TIME = "On time"
    OPERATING_TIME = "Operating time"
    AVERAGING_DURATION = "Averaging duration"
    ACTUALITY_DURATION = "Actuality duration"

    # Date and time
    DATE = "Date"
    DATE_TIME = "Date and time"

    # Identification
    FABRICATION_NO = "Fabrication no"
    ENHANCED_IDENTIFICATION = "(Enhanced) identification"
    ADDRESS = "Address"

    # Special
    UNITS_FOR_HCA = "Units for HCA"

    # Unsupported special codes
    ANY_VIF = "Any VIF"
    MANUFACTURER_SPECIFIC = "Manufacturer specific"
    PLAIN_TEXT = "VIF in following string"

    # Financial (Table 12)
    CREDIT = "Credit"
    DEBIT = "Debit"

    # Electrical measurements (Table 12)
    VOLTAGE = "Voltage"
    CURRENT = "Current"

    # Enhanced identification (Table 12)
    UNIQUE_MESSAGE_ID = "Unique message identification"
    DEVICE_TYPE = "Device type"
    MANUFACTURER = "Manufacturer"
    PARAMETER_SET_ID = "Parameter set identification"
    MODEL_VERSION = "Model/Version"
    HARDWARE_VERSION = "Hardware version"
    FIRMWARE_VERSION = "Firmware version"
    SOFTWARE_VERSION = "Software version"

    # Improved selection (Table 12)
    CUSTOMER_LOCATION = "Customer location"
    CUSTOMER = "Customer"
    ACCESS_CODE = "Access code"
    PASSWORD = "Password"

    # Error and status (Table 12)
    ERROR_FLAGS = "Error flags"
    ERROR_MASK = "Error mask"
    SECURITY_KEY = "Security key"
    DIGITAL_OUTPUT = "Digital output"
    DIGITAL_INPUT = "Digital input"

    # Communication parameters (Table 12)
    BAUDRATE = "Baud rate"
    RESPONSE_DELAY = "Response delay time (bit-times)"
    RETRY = "Retry"
    REMOTE_CONTROL = "Remote control"

    # Storage management (Table 12)
    STORAGE_NUMBER = "Storage number"
    STORAGE_BLOCK_SIZE = "Storage block size"
    TARIFF_DESCRIPTOR = "Tariff descriptor"
    STORAGE_INTERVAL = "Storage interval"

    # Operational data (Table 12)
    OPERATOR_DATA = "Operator specific data"
    TIME_POINT = "Time point second"
    DURATION_SINCE_READOUT = "Duration since last readout"

    # Tariff management (Table 12)
    TARIFF_START = "Start date/time of tariff"
    TARIFF_DURATION = "Duration of tariff"
    TARIFF_PERIOD = "Period of tariff"

    # Special data types (Table 12)
    DIMENSIONLESS = "Dimensionless"
    DATA_CONTAINER_WIRELESS = "Data container for wireless M-Bus"
    DATA_CONTAINER_MANUFACTURER = "Data container for manufacturer specific protocol"
    TRANSMISSION_PERIOD = "Period of nominal transmissions"

    # Counters and control (Table 12)
    RESET_COUNTER = "Reset counter"
    CUMULATION_COUNTER = "Cumulation counter"
    CONTROL_SIGNAL = "Control signal"
    DAY_OF_WEEK = "Day of week"
    WEEK_NUMBER = "Week number"
    TIME_POINT_DAY_CHANGE = "Time point of day change"
    PARAMETER_ACTIVATION = "State of parameter activation"
    SUPPLIER_INFO = "Special supplier information"

    # Duration tracking (Table 12)
    DURATION_SINCE_CUMULATION = "Duration since last cumulation"

    # Battery monitoring (Table 12 and Table 13)
    BATTERY_LIFETIME = "Operating time battery"
    BATTERY_CHANGE_DATE = "Date and time of battery change"
    REMAINING_BATTERY_LIFETIME = "Remaining battery lifetime"

    # RF and communication (Table 12)
    RF_LEVEL = "RF level"
    DAYLIGHT_SAVING = "Daylight saving"
    LISTENING_WINDOW = "Listening window management"
    METER_STOPPED_COUNT = "Number of times meter was stopped"

    # Application selection (Table 13)
    CURRENTLY_SELECTED_APPLICATION = "Currently selected application"

    # ==========================================================================
    # Table 15: Combinable (orthogonal) VIFE codes
    # ==========================================================================

    # Object actions (master to slave) - Table 17
    ACTION_WRITE = "Write"
    ACTION_ADD = "Add value"
    ACTION_SUBTRACT = "Subtract value"
    ACTION_OR = "OR"
    ACTION_AND = "AND"
    ACTION_XOR = "XOR"
    ACTION_AND_NOT = "AND NOT"
    ACTION_CLEAR = "Clear"
    ACTION_ADD_ENTRY = "Add entry"
    ACTION_DELETE_ENTRY = "Delete entry"
    ACTION_DELAYED = "Delayed action"
    ACTION_FREEZE_DATA = "Freeze data"
    ACTION_ADD_TO_READOUT = "Add to readout-list"
    ACTION_DELETE_FROM_READOUT = "Delete from readout-list"

    # Special data types
    AVERAGE_VALUE = "Average value"
    INVERSE_COMPACT_PROFILE = "Inverse compact profile"
    RELATIVE_DEVIATION = "Relative deviation"

    # Record error codes (slave to master) - Table 18
    ERROR_NONE = "None"
    ERROR_TOO_MANY_DIFES = "Too many DIFEs"
    ERROR_STORAGE_NOT_IMPLEMENTED = "Storage number not implemented"
    ERROR_UNIT_NOT_IMPLEMENTED = "Unit number not implemented"
    ERROR_TARIFF_NOT_IMPLEMENTED = "Tariff number not implemented"
    ERROR_FUNCTION_NOT_IMPLEMENTED = "Function not implemented"
    ERROR_DATA_CLASS_NOT_IMPLEMENTED = "Data class not implemented"
    ERROR_DATA_SIZE_NOT_IMPLEMENTED = "Data size not implemented"
    ERROR_TOO_MANY_VIFES = "Too many VIFEs"
    ERROR_ILLEGAL_VIF_GROUP = "Illegal VIF-Group"
    ERROR_ILLEGAL_VIF_EXPONENT = "Illegal VIF-Exponent"
    ERROR_VIF_DIF_MISMATCH = "VIF/DIF mismatch"
    ERROR_UNIMPLEMENTED_ACTION = "Unimplemented action"
    ERROR_NO_DATA_AVAILABLE = "No data available (undefined value)"
    ERROR_DATA_OVERFLOW = "Data overflow"
    ERROR_DATA_UNDERFLOW = "Data underflow"
    ERROR_DATA_ERROR = "Data error"
    ERROR_PREMATURE_END_OF_RECORD = "Premature end of record"

    STANDARD_CONFORM_DATA = "Standard conform data content"
    COMPACT_PROFILE_WITH_REGISTER = "Compact profile with register numbers"
    COMPACT_PROFILE = "Compact profile"

    # Time modifiers
    PER_SECOND = "Per second"
    PER_MINUTE = "Per minute"
    PER_HOUR = "Per hour"
    PER_DAY = "Per day"
    PER_WEEK = "Per week"
    PER_MONTH = "Per month"
    PER_YEAR = "Per year"
    PER_REVOLUTION = "Per revolution/measurement"

    # Pulse increments
    INCREMENT_INPUT_PULSE = "Increment per input pulse on input channel number"
    INCREMENT_OUTPUT_PULSE = "Increment per output pulse on output channel number"

    # Divisors
    PER_LITRE = "Per litre"
    PER_M3 = "Per m³"
    PER_KG = "Per kg"
    PER_KELVIN = "Per K"
    PER_KWH = "Per kWh"
    PER_GJ = "Per GJ"
    PER_KW = "Per kW"
    PER_KELVIN_LITRE = "Per (K·l)"
    PER_VOLT = "Per V"
    PER_AMPERE = "Per A"

    # Multipliers
    MULTIPLIED_SECS = "Multiplied by s"
    MULTIPLIED_SECS_V = "Multiplied by s/V"
    MULTIPLIED_SECS_A = "Multiplied by s/A"

    # Data characteristics
    START_DATE_TIME = "Start date/time of"
    UNCORRECTED_UNIT = "VIF contains uncorrected unit or value at metering conditions"
    ACCUMULATION_POSITIVE = "Accumulation only if positive contributions"
    ACCUMULATION_ABS_NEGATIVE = "Accumulation of abs value only if negative contributions"
    NON_METRIC_UNIT = "Used for alternate non-metric unit system"
    VALUE_BASE_CONDITIONS = "Value at base conditions"
    OBIS_DECLARATION = "OBIS-declaration"

    # Limit values
    LIMIT_VALUE = "Limit value"
    LIMIT_EXCEED_COUNT = "Number of exceeds of limit"
    DATE_LIMIT_EXCEED = "Date/time of limit exceed"
    DURATION_LIMIT_EXCEED = "Duration of limit exceed"

    # Duration and values
    DURATION = "Duration"
    VALUE_DURING_LIMIT_EXCEED = "Value during limit exceed"
    LEAKAGE_VALUES = "Leakage values"
    OVERFLOW_VALUES = "Overflow values"
    DATE_TIME_OF = "Date/time of"

    # Corrections
    MULTIPLICATIVE_CORRECTION = "Multiplicative correction factor"
    ADDITIVE_CORRECTION = "Additive correction constant"

    # Special
    FUTURE_VALUE = "Future value"
    RESERVED = "Reserved"

    # ==========================================================================
    # Table 16: Extension of combinable VIFE codes
    # ==========================================================================

    # Phase information
    AT_PHASE_L1 = "At phase L1"
    AT_PHASE_L2 = "At phase L2"
    AT_PHASE_L3 = "At phase L3"
    AT_NEUTRAL = "At neutral"
    BETWEEN_PHASE_L1_L2 = "Between phase L1 and L2"
    BETWEEN_PHASE_L2_L3 = "Between phase L2 and L3"
    BETWEEN_PHASE_L3_L1 = "Between phase L3 and L1"

    # Quadrant information
    AT_QUADRANT_Q1 = "At quadrant Q1"
    AT_QUADRANT_Q2 = "At quadrant Q2"
    AT_QUADRANT_Q3 = "At quadrant Q3"
    AT_QUADRANT_Q4 = "At quadrant Q4"
    DELTA_IMPORT_EXPORT = "Delta between import and export"

    # Data presentation and direction
    ACCUMULATION_ABSOLUTE_BOTH = "Accumulation of absolute value for both positive and negative contribution"
    DATA_TYPE_C = "Data presented with type C"
    DATA_TYPE_D = "Data presented with type D"
    DIRECTION_TO_METER = "Direction: from communication partner to meter"
    DIRECTION_FROM_METER = "Direction: from meter to communication partner"


class ValueDescriptionTransformer(Enum):
    APPEND_PER_SECOND = member(lambda description, _code: f"{description} per second")

    def __call__(self, description: str, code: int) -> str:
        return self.value(description, code)


class ValueTransformer(Enum):
    """Value transformation functions for M-Bus VIF/VIFE codes.

    Each member is a function that takes (value, code) and returns the transformed value.
    - value: The raw numeric value to transform
    - code: The VIF/VIFE code byte containing bit-encoded parameters

    Naming convention:
        MULT_10_POW_{bits}_{offset} = Multiplicative: value * 10^((code & mask) + offset)
        ADD_10_POW_{bits}_{offset} = Additive: value + 10^((code & mask) + offset)
        MULT_{base}_POW_{exponent} = Fixed: value * base^exponent

    Examples:
        MULT_10_POW_NNN_MINUS_3 → value * 10^((code & 0x07) - 3)
        ADD_10_POW_NN_MINUS_3 → value + 10^((code & 0x03) - 3)

    Usage:
        transform = _ValueTransformer.MULT_10_POW_NNN_MINUS_3
        result = transform(1042, 0x03)  # Calls the method directly
    """

    # === POWER OF 10: nnn bits (3 bits, mask 0x07) ===
    MULT_10_POW_NNN_MINUS_3 = member(lambda value, code: value * 10 ** ((code & 0x07) - 3))
    MULT_10_POW_NNN = member(lambda value, code: value * 10 ** (code & 0x07))
    MULT_10_POW_NNN_MINUS_6 = member(lambda value, code: value * 10 ** ((code & 0x07) - 6))
    MULT_10_POW_NNN_MINUS_7 = member(lambda value, code: value * 10 ** ((code & 0x07) - 7))
    MULT_10_POW_NNN_MINUS_9 = member(lambda value, code: value * 10 ** ((code & 0x07) - 9))

    # === POWER OF 10: nn bits (2 bits, mask 0x03) ===
    MULT_10_POW_NN_MINUS_3 = member(lambda value, code: value * 10 ** ((code & 0x03) - 3))
    MULT_10_POW_NN = member(lambda value, code: value * 10 ** (code & 0x03))
    MULT_10_POW_NN_PLUS_5 = member(lambda value, code: value * 10 ** ((code & 0x03) + 5))

    # === POWER OF 10: n bit (1 bit, mask 0x01) ===
    MULT_10_POW_N_MINUS_1 = member(lambda value, code: value * 10 ** ((code & 0x01) - 1))
    MULT_10_POW_N = member(lambda value, code: value * 10 ** (code & 0x01))
    MULT_10_POW_N_PLUS_2 = member(lambda value, code: value * 10 ** ((code & 0x01) + 2))
    MULT_10_POW_N_PLUS_5 = member(lambda value, code: value * 10 ** ((code & 0x01) + 5))
    MULT_10_POW_N_PLUS_8 = member(lambda value, code: value * 10 ** ((code & 0x01) + 8))

    # === POWER OF 10: nnnn bits (4 bits, mask 0x0F) ===
    MULT_10_POW_NNNN_MINUS_9 = member(lambda value, code: value * 10 ** ((code & 0x0F) - 9))
    MULT_10_POW_NNNN_MINUS_12 = member(lambda value, code: value * 10 ** ((code & 0x0F) - 12))

    # === POWER OF 10 WITH TIME CONVERSION ===
    MULT_10_POW_NNN_MINUS_6_DIV_3600 = member(lambda value, code: value * 10 ** ((code & 0x07) - 6) / 3600)
    MULT_10_POW_NNN_MINUS_7_DIV_60 = member(lambda value, code: value * 10 ** ((code & 0x07) - 7) / 60)
    MULT_10_POW_NNN_MINUS_3_DIV_3600 = member(lambda value, code: value * 10 ** ((code & 0x07) - 3) / 3600)

    # === POWER OF 2 ===
    MULT_2_POW_MINUS_12 = member(lambda value, _code: value * 2 ** (-12))

    # === FIXED VALUES ===
    MULT_1000 = member(lambda value, _code: value * 1000.0)
    MULT_1 = member(lambda value, _code: value * 1.0)
    MULT_0_1 = member(lambda value, _code: value * 0.1)

    # === ADDITIVE ===
    ADD_10_POW_NN_MINUS_3 = member(lambda value, code: value + 10 ** ((code & 0x03) - 3))

    def __call__(self, value: float, code: int) -> float:
        """Allow calling the enum member directly as a function.

        Args:
            value: The raw numeric value to transform
            code: The VIF/VIFE code byte

        Returns:
            The transformed value
        """
        return float(self.value(value, code))


class ValueFunction(StrEnum):
    INSTANTANEOUS = "instantaneous"
    MAXIMUM = "maximum"
    MINIMUM = "minimum"
    ERROR = "error"


class Value(ABC):
    # Validity (all types)
    is_valid: bool

    @abstractmethod
    def __init__(self, is_valid: bool) -> None:
        self.is_valid = is_valid


class IntegerValue(int, Value):
    def __new__(cls, is_valid: bool, numeric_value: int = 0) -> "IntegerValue":
        # Create int object with the numeric value
        instance = super().__new__(cls, numeric_value)
        return instance

    def __init__(self, is_valid: bool, numeric_value: int = 0) -> None:
        # Don't call int.__init__, call Value.__init__ directly
        Value.__init__(self, is_valid)


class FloatValue(float, Value):
    def __new__(cls, is_valid: bool, numeric_value: float = 0.0) -> "FloatValue":
        # Create float object with the numeric value
        instance = super().__new__(cls, numeric_value)
        return instance

    def __init__(self, is_valid: bool, numeric_value: float = 0.0) -> None:
        # Don't call float.__init__, call Value.__init__ directly
        Value.__init__(self, is_valid)


class StringValue(str, Value):
    def __new__(cls, is_valid: bool, string_value: str = "") -> "StringValue":
        # Create str object with the string value
        instance = super().__new__(cls, string_value)
        return instance

    def __init__(self, is_valid: bool, string_value: str = "") -> None:
        # Don't call str.__init__, call Value.__init__ directly
        Value.__init__(self, is_valid)


class BooleanArrayValue(Value):
    boolean_array_value: tuple[bool, ...]

    def __init__(self, is_valid: bool, boolean_array_value: tuple[bool, ...] = ()) -> None:
        super().__init__(is_valid)
        self.boolean_array_value = boolean_array_value


class TemporalValue(Value):
    """Unified M-Bus temporal value for all types (F, G, I, J, M).

    Supports two representations:

    1. Component-based (Types F, G, I, J):
       - Individual year/month/day/hour/minute/second fields
       - Recurring patterns (special values: 0, 15, 31, 63, 127)
       - year_2digit + year_full for different year ranges

    2. Epoch-based (Type M):
       - epoch_seconds: duration since starting epoch
       - utc_offset_hours: timezone or -16 for duration
       - resolution_seconds: 2, 1, 1/256, or 1/32768 seconds
       - epoch_start: 0=2013-01-01, 1=1970-01-01 (Unix)

    None = field not present or not specified for this type

    Examples:
        Component-based (Type F):
            >>> t = ValueTemporal(
            ...     year_2digit=25, year_full=2025, month=3, day=15,
            ...     hour=14, minute=30, second=None,
            ...     is_valid=True
            ... )
            >>> str(t)
            "2025-03-15 14:30"

        Recurring pattern:
            >>> t = ValueTemporal(
            ...     year_2digit=25, year_full=2025, month=15, day=15,
            ...     hour=14, minute=30, second=None,
            ...     is_valid=True
            ... )
            >>> str(t)
            "2025-*-15 14:30"

        Epoch-based (Type M):
            >>> t = ValueTemporal(
            ...     epoch_seconds=700000000.0,
            ...     utc_offset_hours=1,
            ...     resolution_seconds=1.0,
            ...     epoch_start=1,
            ...     is_valid=True
            ... )
            >>> str(t)
            "1992-03-12 06:46:40+01:00 (UTC+1, res=1.0s)"
    """

    # Component-based fields (Types F, G, I, J)
    year_2digit: int | None
    year_full: int | None
    month: int | None
    day: int | None
    hour: int | None
    minute: int | None
    second: float | None

    # Epoch-based fields (Type M only - None for other types)
    epoch_seconds: float | None
    utc_offset_hours: int | None
    resolution_seconds: float | None
    epoch_start: int | None

    # Metadata (Type F and Type I - None for other types)
    is_summer_time: bool | None
    day_of_week: int | None
    week: int | None
    is_leap_year: bool | None
    daylight_savings_deviation: int | None

    def __init__(
        self,
        # Validity
        is_valid: bool,
        # Component-based fields
        year_2digit: int | None = None,
        year_full: int | None = None,
        month: int | None = None,
        day: int | None = None,
        hour: int | None = None,
        minute: int | None = None,
        second: float | None = None,
        # Epoch-based fields
        epoch_seconds: float | None = None,
        utc_offset_hours: int | None = None,
        resolution_seconds: float | None = None,
        epoch_start: int | None = None,
        # Metadata
        is_summer_time: bool | None = None,
        day_of_week: int | None = None,
        week: int | None = None,
        is_leap_year: bool | None = None,
        daylight_savings_deviation: int | None = None,
    ) -> None:
        """Initialize ValueTemporal.

        Args:
            year_2digit: Raw 2-digit year (0-99, 127=every year)
            year_full: Calculated full year (1900-2299 or 2000-2099)
            month: Month (1-12, 15=every month)
            day: Day (1-31, 0=every day)
            hour: Hour (0-23, 31=every hour)
            minute: Minute (0-59, 63=every minute)
            second: Second with fractional part (0-59.999..., 63=every second)
            epoch_seconds: Duration since epoch (Type M)
            utc_offset_hours: UTC offset (-16=duration, -12 to +14=timezone)
            resolution_seconds: Time resolution (2.0, 1.0, 1/256, 1/32768)
            epoch_start: Epoch start (0=2013-01-01, 1=1970-01-01)
            is_valid: Validity flag
            is_summer_time: Summer time flag
            day_of_week: Day of week (1-7, 0=not specified)
            week: Week number (1-53, 0=not specified)
            is_leap_year: Leap year flag
            daylight_savings_deviation: DST deviation in hours (0-3)
        """
        super().__init__(is_valid)

        self.year_2digit = year_2digit
        self.year_full = year_full
        self.month = month
        self.day = day
        self.hour = hour
        self.minute = minute
        self.second = second

        self.epoch_seconds = epoch_seconds
        self.utc_offset_hours = utc_offset_hours
        self.resolution_seconds = resolution_seconds
        self.epoch_start = epoch_start

        self.is_summer_time = is_summer_time
        self.day_of_week = day_of_week
        self.week = week
        self.is_leap_year = is_leap_year
        self.daylight_savings_deviation = daylight_savings_deviation

    @property
    def is_component_based(self) -> bool:
        """True if using component representation (F, G, I, J)."""
        return self.epoch_seconds is None

    @property
    def is_epoch_based(self) -> bool:
        """True if using epoch representation (M)."""
        return self.epoch_seconds is not None

    @property
    def is_every_year(self) -> bool:
        """True if year represents 'every year' recurring pattern."""
        return self.year_2digit == 127

    @property
    def is_every_month(self) -> bool:
        """True if month represents 'every month' recurring pattern."""
        return self.month == 15

    @property
    def is_every_day(self) -> bool:
        """True if day represents 'every day' recurring pattern."""
        return self.day == 0

    @property
    def is_every_hour(self) -> bool:
        """True if hour represents 'every hour' recurring pattern."""
        return self.hour == 31

    @property
    def is_every_minute(self) -> bool:
        """True if minute represents 'every minute' recurring pattern."""
        return self.minute == 63

    @property
    def is_every_second(self) -> bool:
        """True if second represents 'every second' recurring pattern."""
        if self.is_component_based and self.second is not None:
            return self.second == 63
        return False

    @property
    def has_date(self) -> bool:
        """True if any date component is present."""
        return any(x is not None for x in (self.year_2digit, self.month, self.day))

    @property
    def has_time(self) -> bool:
        """True if any time component is present."""
        return any(x is not None for x in (self.hour, self.minute, self.second))

    @property
    def is_fully_specified(self) -> bool:
        """True if valid and no recurring patterns (component-based only)."""
        if not self.is_valid:
            return False

        if self.is_epoch_based:
            return True  # Epoch is always fully specified if valid

        # Check for recurring patterns
        return not any(
            [
                self.is_every_year,
                self.is_every_month,
                self.is_every_day,
                self.is_every_hour,
                self.is_every_minute,
                self.is_every_second,
            ]
        )

    @property
    def is_duration(self) -> bool:
        """True if epoch-based and represents duration (not absolute time)."""
        return self.is_epoch_based and self.utc_offset_hours == -16

    @property
    def starting_epoch(self) -> datetime | None:
        """Get epoch starting time (UTC) for Type M.

        Returns:
            datetime(2013, 1, 1, 0, 0, 0, tzinfo=UTC) if epoch_start=0
            datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC) if epoch_start=1 (Unix epoch)
            None if not epoch-based or invalid epoch_start
        """
        if not self.is_epoch_based:
            return None

        if self.epoch_start == 0:
            return datetime(2013, 1, 1, 0, 0, 0, tzinfo=UTC)
        elif self.epoch_start == 1:
            return datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC)
        return None

    def to_datetime(self) -> datetime:
        """Convert to Python datetime.

        For component-based: creates datetime from components
        For epoch-based: calculates from epoch + offset

        Returns:
            Python datetime object

        Raises:
            ValueError: If not fully specified, invalid, or is duration
        """
        if not self.is_valid:
            raise ValueError("Cannot convert invalid temporal value")

        if self.is_epoch_based:
            if self.is_duration:
                raise ValueError("Cannot convert duration to datetime")

            # Type narrowing: these must be non-None for epoch-based
            if self.starting_epoch is None or self.epoch_seconds is None or self.utc_offset_hours is None:
                raise ValueError("Missing epoch data")

            # Calculate absolute time from epoch
            dt_utc = self.starting_epoch + timedelta(seconds=self.epoch_seconds)

            # Apply timezone offset
            offset = timezone(timedelta(hours=self.utc_offset_hours))
            return dt_utc.astimezone(offset)

        else:  # Component-based
            if not self.is_fully_specified:
                raise ValueError("Cannot convert: contains recurring patterns")

            if not (self.has_date and self.has_time):
                raise ValueError("Cannot convert: missing date or time components")

            # Type narrowing: these must be non-None and actual values
            if self.year_full is None or self.month is None or self.day is None:
                raise ValueError("Missing date components")
            if self.hour is None or self.minute is None:
                raise ValueError("Missing time components")

            return datetime(
                self.year_full,
                self.month,
                self.day,
                self.hour,
                self.minute,
                int(self.second) if self.second is not None else 0,
                int((self.second % 1) * 1_000_000) if self.second is not None else 0,
            )

    def to_date(self) -> date:
        """Convert to Python date (component-based only).

        Returns:
            Python date object

        Raises:
            ValueError: If not component-based, not fully specified, or missing date
        """
        if not self.is_component_based:
            raise ValueError("Cannot convert epoch-based to date")

        if not self.is_fully_specified or not self.has_date:
            raise ValueError("Cannot convert to date")

        # Type narrowing: these must be non-None
        if self.year_full is None or self.month is None or self.day is None:
            raise ValueError("Missing date components")

        return date(self.year_full, self.month, self.day)

    def to_time(self) -> time:
        """Convert to Python time (component-based only).

        Returns:
            Python time object

        Raises:
            ValueError: If not component-based, not fully specified, or missing time
        """
        if not self.is_component_based:
            raise ValueError("Cannot convert epoch-based to time")

        if not self.is_fully_specified or not self.has_time:
            raise ValueError("Cannot convert to time")

        # Type narrowing: these must be non-None
        if self.hour is None or self.minute is None:
            raise ValueError("Missing time components")

        return time(
            self.hour,
            self.minute,
            int(self.second) if self.second is not None else 0,
            int((self.second % 1) * 1_000_000) if self.second is not None else 0,
        )

    def to_timedelta(self) -> timedelta:
        """Convert to Python timedelta.

        For epoch-based: returns the duration

        Returns:
            Python timedelta object

        Raises:
            ValueError: If not epoch-based or not duration
        """
        if not self.is_epoch_based:
            raise ValueError("Cannot convert component-based to timedelta")

        if not self.is_duration:
            raise ValueError("Cannot convert absolute time to timedelta (use is_duration)")

        # Type narrowing: epoch_seconds must be non-None
        if self.epoch_seconds is None:
            raise ValueError("Missing epoch_seconds")

        return timedelta(seconds=self.epoch_seconds)

    def __str__(self) -> str:
        """Human-readable representation.

        Returns:
            String representation using * for recurring patterns

        Examples:
            "2025-03-15 14:30"       - Fully specified datetime
            "2025-*-15 14:30"        - Every month on the 15th at 14:30
            "1955-01-01 00:00"       - Type F from 1900s
            "2099-12-31"             - Type G date only
            "14:30:45"               - Type J time only
            "?-?-?"                  - All date components not specified
            "Duration: 3600.0s (res=1.0s)" - Type M duration
            "2025-03-15 14:30:00+01:00 (UTC+1, res=1.0s)" - Type M absolute time
        """
        if self.is_epoch_based:
            if self.is_duration:
                return f"Duration: {self.epoch_seconds}s (res={self.resolution_seconds}s)"
            else:
                try:
                    dt = self.to_datetime()
                    return f"{dt.isoformat()} (UTC{self.utc_offset_hours:+d}, res={self.resolution_seconds}s)"
                except (ValueError, TypeError):
                    return "<invalid epoch time>"

        else:  # Component-based
            parts = []

            if self.has_date:
                year_str = "*" if self.is_every_year else (str(self.year_full) if self.year_full is not None else "?")
                month_str = "*" if self.is_every_month else (f"{self.month:02d}" if self.month is not None else "?")
                day_str = "*" if self.is_every_day else (f"{self.day:02d}" if self.day is not None else "?")
                parts.append(f"{year_str}-{month_str}-{day_str}")

            if self.has_time:
                hour_str = "*" if self.is_every_hour else (f"{self.hour:02d}" if self.hour is not None else "?")
                minute_str = "*" if self.is_every_minute else (f"{self.minute:02d}" if self.minute is not None else "?")

                if self.second is not None:
                    if self.is_every_second:
                        second_str = "*"
                    else:
                        # Handle fractional seconds
                        second_str = f"{self.second:06.3f}" if self.second % 1 else f"{int(self.second):02d}"
                    parts.append(f"{hour_str}:{minute_str}:{second_str}")
                else:
                    parts.append(f"{hour_str}:{minute_str}")

            return " ".join(parts) if parts else "<empty>"

    def __repr__(self) -> str:
        """Developer representation showing all fields."""
        if self.is_epoch_based:
            return (
                f"ValueTemporal(epoch_seconds={self.epoch_seconds}, "
                f"utc_offset_hours={self.utc_offset_hours}, "
                f"resolution_seconds={self.resolution_seconds}, "
                f"epoch_start={self.epoch_start}, is_valid={self.is_valid})"
            )
        else:
            return (
                f"ValueTemporal(year_2digit={self.year_2digit}, year_full={self.year_full}, "
                f"month={self.month}, day={self.day}, hour={self.hour}, "
                f"minute={self.minute}, second={self.second}, is_valid={self.is_valid})"
            )
