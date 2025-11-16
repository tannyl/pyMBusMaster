"""DIB (Data Information Block) type system and interpretation logic.

This module implements the M-Bus DIB parsing system according to EN 13757-3:2018.
A DIB (Data Information Block) consists of a DIF (Data Information Field) and
optionally one or more DIFEs (Data Information Field Extensions).

The module provides:

Classes:
    - DIB: Base class for Data Information Block (DIF + optional DIFEs)
    - DataDIB: DIB for data records with storage/tariff/subunit information
    - ReadoutSelectionDIB: DIB for readout selection (master to slave)
    - SpecialDIB: Base class for special function DIBs
    - ManufacturerDIB: DIB for manufacturer-specific data blocks
    - IdleFillerDIB: DIB for idle filler (padding) bytes
    - GlobalReadoutDIB: DIB for global readout requests

The DIB structure:
    DIB = DIF (1 byte) + optional DIFEs (0-11 bytes)

    The DIB accumulates information from the DIF/DIFE chain:
    - Storage number: accumulated from DIF bit 6 + DIFE bits 0-3
    - Tariff: accumulated from DIFE bits 4-5
    - Subunit: accumulated from DIFE bit 6
    - Register number flag: set if FinalDIFE (0x00) is present

Architecture:
    DIB uses a factory pattern (__new__) to automatically instantiate the correct
    subclass based on the DIF type. It delegates to DIF.from_bytes_async() for
    parsing the DIF/DIFE chain from a byte stream.

Reference: EN 13757-3:2018
    - Section 6.3: Data Information Block structure
    - Table 4 (page 13): Data field encoding
    - Table 6 (page 14): Special function codes
    - Table 8 (page 14): DIFE encoding
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .common import CommunicationDirection
from .data import DataRules
from .dif import (
    DIF,
    DIFE,
    DIFE_MAXIMUM_CHAIN_LENGTH,
    DataDIF,
    DataDIFE,
    FinalDIFE,
    SpecialDIF,
    _SpecialFieldFunction,
)
from .value import ValueFunction

# =============================================================================
# DIB Constants (EN 13757-3:2018)
# =============================================================================

DIB_MAXIMUM_CHAIN_LENGTH = DIFE_MAXIMUM_CHAIN_LENGTH + 1  # Maximum DIF + DIFEs in a chain

DIB_MAXIMUM_REGISTER_NUMBER = 125  # Maximum register number when FinalDIFE is present

# =============================================================================
# DIB Classes - Data Information Block parsing
# =============================================================================


class DIB:
    """Base class for Data Information Block (DIB).

    A DIB represents the complete data information section of an M-Bus data record,
    consisting of a DIF (Data Information Field) and optional DIFE bytes
    (Data Information Field Extensions).

    This class uses a factory pattern (__new__) to automatically instantiate the
    correct subclass based on the DIF type:
    - DataDIF → DataDIB or ReadoutSelectionDIB
    - SpecialDIF → ManufacturerDIB, IdleFillerDIB, or GlobalReadoutDIB

    The DIB validates that:
    - Communication direction is not BIDIRECTIONAL
    - DIF/DIFE chain is consistent (matching direction, correct chain length)
    - All fields in the chain are properly linked

    Attributes:
        direction: Communication direction (MASTER_TO_SLAVE or SLAVE_TO_MASTER)

    Usage:
        # Parse from byte stream
        dib = await DIB.from_bytes_async(direction, get_next_bytes)

        # Or construct manually from DIF/DIFE chain
        dif = DIF(direction, 0x04)  # 32-bit integer
        dib = DIB(direction, dif)

    Reference: EN 13757-3:2018, section 6.3
    """

    _field_chain: tuple[DIF, *tuple[DIFE, ...]]

    direction: CommunicationDirection

    def __new__(cls, direction: CommunicationDirection, dif: DIF, *dife: DIFE) -> DIB:
        if isinstance(dif, DataDIF):
            if dif.readout_selection:
                return object.__new__(ReadoutSelectionDIB)
            return object.__new__(DataDIB)

        if isinstance(dif, SpecialDIF):
            if _SpecialFieldFunction.MANUFACTURER_DATA_HEADER in dif.special_function:
                return object.__new__(ManufacturerDIB)

            if _SpecialFieldFunction.IDLE_FILLER in dif.special_function:
                return object.__new__(IdleFillerDIB)

            if _SpecialFieldFunction.GLOBAL_READOUT in dif.special_function:
                return object.__new__(GlobalReadoutDIB)

        # Should never reach here - DIF factory only returns DataDIF or SpecialDIF
        raise AssertionError(f"DIF type not recognized: {type(dif).__name__}")

    def __init__(self, direction: CommunicationDirection, dif: DIF, *dife: DIFE) -> None:
        if direction is CommunicationDirection.BIDIRECTIONAL:
            raise ValueError("DIB communication direction cannot be BIDIRECTIONAL")

        self.direction = direction

        # DIB.__new__ guarantees dif is DIF for DIB subclasses
        assert isinstance(dif, DIF), "dif must be instance of DIF"

        if dif.direction is not self.direction:
            raise ValueError("DIF/DIFE communication direction does not match DIB communication direction")

        self._field_chain = (dif, *dife)

    def to_bytes(self) -> bytes:
        """Convert DIB to bytes representation.

        Serializes the complete DIF/DIFE chain by calling to_bytes() on each
        field in the chain and concatenating the results.

        Returns:
            Bytes containing the complete DIB (DIF + DIFEs)
        """
        byte_array = bytearray()

        for field in self._field_chain:
            byte_array.extend(field.to_bytes())

        return bytes(byte_array)

    @staticmethod
    async def from_bytes_async(
        direction: CommunicationDirection,
        get_next_bytes: Callable[[int], Awaitable[bytes]],
    ) -> DIB:
        """Parse a complete DIB from bytes asynchronously.

        Reads a DIF byte and any following DIFE bytes from the byte stream,
        then constructs the appropriate DIB subclass based on the DIF type.

        This method delegates to DIF.from_bytes_async() to parse the DIF/DIFE
        chain, then passes the result to the DIB factory for subclass instantiation.

        Args:
            direction: Communication direction for the DIB
            get_next_bytes: Async function to read the next n bytes from stream.
                           Should return exactly n bytes or raise an exception.

        Returns:
            DIB instance (automatically instantiated as correct subclass):
            - DataDIB: for regular data records
            - ReadoutSelectionDIB: for readout selection (DIF 0x08)
            - ManufacturerDIB: for manufacturer data (DIF 0x0F/0x1F)
            - IdleFillerDIB: for idle filler (DIF 0x2F)
            - GlobalReadoutDIB: for global readout request (DIF 0x7F)

        Raises:
            ValueError: If byte reading fails, direction is BIDIRECTIONAL,
                       DIF/DIFE chain is invalid, or validation fails

        Example:
            async def get_bytes(n: int) -> bytes:
                return await stream.read(n)

            dib = await DIB.from_bytes_async(
                CommunicationDirection.SLAVE_TO_MASTER,
                get_bytes
            )

            if isinstance(dib, DataDIB):
                print(f"Storage: {dib.storage_number}, Value: {dib.value_function}")
        """
        field_chain = await DIF.from_bytes_async(direction, get_next_bytes)

        return DIB(direction, *field_chain)


class DataDIB(DIB):
    """Data Information Block for data records.

    DataDIB represents data records that encode measurement values, status information,
    or other meter data. It accumulates information from the complete DIF/DIFE chain:

    Storage number accumulation:
        - DIF contributes bit 6 (value 0 or 1)
        - Each DataDIFE contributes bits 0-3 (shifted based on chain position)
        - Total: up to 41 bits (1 from DIF + 40 from 10 DIFEs)
        - If FinalDIFE present: storage number becomes register number (0-125)

    Tariff accumulation:
        - Each DataDIFE contributes bits 4-5 (2 bits, shifted based on position)
        - Total: up to 20 bits from 10 DIFEs

    Subunit accumulation:
        - Each DataDIFE contributes bit 6 (1 bit, shifted based on position)
        - Total: up to 10 bits from 10 DIFEs

    Attributes:
        data_support: Supported data types from DIF encoding (e.g., DataRules.Supports.BCDFK_4)
        value_function: Function type (INSTANTANEOUS, MAXIMUM, MINIMUM, ERROR)
        register_number: True if FinalDIFE present (storage number is register number)
        storage_number: Accumulated storage number or register number (0-125 if register_number=True)
        subunit: Accumulated subunit number
        tariff: Accumulated tariff number

    Validation:
        - DIF must be DataDIF
        - All DIFEs in chain must be DataDIFE or FinalDIFE
        - Chain length must not exceed DIB_MAXIMUM_CHAIN_LENGTH
        - If register_number=True, storage_number must be ≤ DIB_MAXIMUM_REGISTER_NUMBER

    Reference: EN 13757-3:2018
        - Section 6.3.3 (page 12): Data information block
        - Section 6.3.5 (page 14): Storage number and register number
        - Table 4 (page 13): Data field encoding
        - Table 8 (page 14): DIFE encoding
    """

    data_support: DataRules.Supports

    value_function: ValueFunction

    register_number: bool = False

    storage_number: int = 0

    subunit: int = 0

    tariff: int = 0

    def __init__(self, direction: CommunicationDirection, dif: DataDIF, *dife: DataDIFE) -> None:
        super().__init__(direction, dif, *dife)

        # DIB.__new__ guarantees dif is DataDIF for DataDIB subclasses
        assert isinstance(dif, DataDIF), "DataDIB must have DataDIF"

        self.data_support = dif.data_support

        self.value_function = dif.value_function

        self.storage_number += dif.storage_number

        test_field: DIF | DIFE | None = dif
        test_position = 0

        while True:
            if self._field_chain[test_position] is not test_field:
                raise ValueError("DIF/DIFE chain is broken")

            if test_field.next_field is None:
                if self._field_chain[test_position] is not self._field_chain[-1] or not test_field.last_field:
                    raise ValueError("DIF/DIFE chain is incomplete")

                break

            # DIFE.__init__ guarantees that last field cannot have next_field
            assert not test_field.last_field, "DIF/DIFE chain has extra fields after last_field"

            test_field = test_field.next_field
            test_position += 1

            if isinstance(test_field, DataDIFE):
                # Chain with DataDIFE <= 11 (guaranteed by DataDIFE.__init__ checking position)
                assert test_position + 1 <= DIB_MAXIMUM_CHAIN_LENGTH, (
                    "DIF/DIFE chain exceeds maximum length with DataDIFE"
                )

                self.storage_number += test_field.storage_number

                self.subunit += test_field.subunit

                self.tariff += test_field.tariff

                continue
            elif isinstance(test_field, FinalDIFE):
                # Chain with FinalDIFE <= 12 (guaranteed by FinalDIFE.__init__ checking position)
                assert test_position + 1 <= DIB_MAXIMUM_CHAIN_LENGTH + 1, (
                    "DIF/DIFE chain exceeds maximum length with final DIFE"
                )

                # FinalDIFE.__init__ guarantees last_field is True for FinalDIFE
                assert test_field.last_field, "FinalDIFE must be the last field in the DIF/DIFE chain"

                if self.storage_number > DIB_MAXIMUM_REGISTER_NUMBER:
                    raise ValueError("Register number (storage number) exceeds maximum allowed value")

                self.register_number = True

                continue

            raise AssertionError("Non-data DIF/DIFE found in DIF/DIFE chain")


class ReadoutSelectionDIB(DataDIB):
    """Data Information Block for readout selection.

    ReadoutSelectionDIB is a special type of DataDIB used in master-to-slave communication
    to select specific data records for readout. The DIF must have the readout_selection
    flag set (DIF code 0x08).

    This DIB type is only valid in MASTER_TO_SLAVE direction.

    Attributes:
        (Inherits all attributes from DataDIB)

    Validation:
        - DIF.readout_selection must be True
        - Direction must be MASTER_TO_SLAVE

    Reference: EN 13757-3:2018
        - Table 4 (page 13): Data field 0x08 - Selection for readout
    """

    def __init__(self, direction: CommunicationDirection, dif: DataDIF, *dife: DataDIFE) -> None:
        super().__init__(direction, dif, *dife)

        # DIB.__new__ guarantees readout_selection is True for ReadoutSelectionDIB
        assert dif.readout_selection, "ReadoutSelectionDIB must have readout_selection=True"


class SpecialDIB(DIB):
    """Base class for Data Information Blocks with special functions.

    SpecialDIB represents special control functions in M-Bus communication that
    don't carry measurement data. These include manufacturer-specific data blocks,
    idle fillers, and global readout requests.

    Special DIBs:
    - Must have a SpecialDIF as the primary DIF
    - Cannot have any DIFE bytes (chain length = 1)
    - Used for protocol control and special data structures

    Subclasses:
        - ManufacturerDIB: Manufacturer-specific data header (0x0F/0x1F)
        - IdleFillerDIB: Idle filler/padding byte (0x2F)
        - GlobalReadoutDIB: Global readout request (0x7F)

    Attributes:
        (Inherits direction from DIB)

    Validation:
        - DIF must be SpecialDIF
        - No DIFEs allowed (raises ValueError if any provided)

    Reference: EN 13757-3:2018
        - Table 6 (page 14): Special function codes
    """

    def __init__(self, direction: CommunicationDirection, dif: SpecialDIF, *dife: DIFE) -> None:
        super().__init__(direction, dif, *dife)

        # DIB.__new__ guarantees dif is SpecialDIF for SpecialDIB subclasses
        assert isinstance(dif, SpecialDIF), "SpecialDIB must have SpecialDIF"

        # SpecialDIF.last_field is always True, so DIFE.__init__ prevents extension
        assert not dife, "SpecialDIB cannot have DIFE fields"


class ManufacturerDIB(SpecialDIB):
    """Data Information Block for manufacturer-specific data.

    ManufacturerDIB marks the start of a manufacturer-specific data block. The data
    following this DIB is interpreted according to manufacturer-specific protocols
    and is not standardized by EN 13757-3.

    Two variants exist:
    - 0x0F: Manufacturer data (no more records follow)
    - 0x1F: Manufacturer data + more records follow in next datagram (slave to master only)

    The more_records_follow flag indicates whether additional data records will be
    sent in subsequent datagrams. This is used for multi-datagram responses.

    Attributes:
        more_records_follow: True if more records will follow in next datagram (0x1F)

    Validation:
        - Special function must be MANUFACTURER_DATA_HEADER
        - Can optionally include MORE_RECORDS_FOLLOW flag
        - 0x1F is only valid in SLAVE_TO_MASTER direction

    Reference: EN 13757-3:2018
        - Table 6 (page 14): Data field 0x0F and 0x1F
        - Section 6.3.4 (page 14): Manufacturer specific data
    """

    more_records_follow: bool

    def __init__(self, direction: CommunicationDirection, dif: SpecialDIF, *dife: DIFE) -> None:
        super().__init__(direction, dif, *dife)

        # DIB.__new__ uses 'in' check, but special_function values come from field tables
        # Field tables only contain valid combinations: 0x0F or 0x1F (with MORE_RECORDS_FOLLOW)
        assert (
            dif.special_function & ~_SpecialFieldFunction.MORE_RECORDS_FOLLOW
            is _SpecialFieldFunction.MANUFACTURER_DATA_HEADER
        ), "ManufacturerDIB must have MANUFACTURER_DATA_HEADER (optionally with MORE_RECORDS_FOLLOW)"

        self.more_records_follow = _SpecialFieldFunction.MORE_RECORDS_FOLLOW in dif.special_function


class IdleFillerDIB(SpecialDIB):
    """Data Information Block for idle filler.

    IdleFillerDIB represents an idle filler byte (0x2F) used as padding in M-Bus
    datagrams. This byte should be skipped/ignored during record parsing.

    Idle fillers are used to:
    - Align data to specific byte boundaries
    - Fill unused space in fixed-length telegram structures
    - Maintain backward compatibility when removing data records

    The presence of an IdleFillerDIB does not indicate a data record - it should
    be treated as a no-op during parsing.

    Attributes:
        (Inherits direction from DIB)

    Validation:
        - Special function must be exactly IDLE_FILLER (no other flags)

    Reference: EN 13757-3:2018
        - Table 6 (page 14): Data field 0x2F - Idle filler
    """

    def __init__(self, direction: CommunicationDirection, dif: SpecialDIF, *dife: DIFE) -> None:
        super().__init__(direction, dif, *dife)

        # DIB.__new__ uses 'in' check, but field tables only contain 0x2F for IDLE_FILLER
        assert dif.special_function is _SpecialFieldFunction.IDLE_FILLER, "IdleFillerDIB must have IDLE_FILLER"


class GlobalReadoutDIB(SpecialDIB):
    """Data Information Block for global readout request.

    GlobalReadoutDIB represents a global readout request (0x7F) sent from master
    to slave, requesting the meter to return all available data records.

    This is used in master-to-slave communication as a wildcard request to read
    all data from the meter without specifying individual records. The slave
    responds with all data records it has available.

    This DIB type is only valid in MASTER_TO_SLAVE direction.

    Attributes:
        (Inherits direction from DIB)

    Validation:
        - Special function must be exactly GLOBAL_READOUT (no other flags)
        - Direction must be MASTER_TO_SLAVE

    Reference: EN 13757-3:2018
        - Table 6 (page 14): Data field 0x7F - Global readout request
    """

    def __init__(self, direction: CommunicationDirection, dif: SpecialDIF, *dife: DIFE) -> None:
        super().__init__(direction, dif, *dife)

        # DIB.__new__ uses 'in' check, but field tables only contain 0x7F for GLOBAL_READOUT
        assert dif.special_function is _SpecialFieldFunction.GLOBAL_READOUT, "GlobalReadoutDIB must have GLOBAL_READOUT"
