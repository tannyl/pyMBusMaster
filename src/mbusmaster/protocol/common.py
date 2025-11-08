"""Common types and utilities shared across protocol components.

This module contains fundamental types used throughout the protocol layer.

Reference: EN 13757-3:2018
"""

from enum import Flag, auto


class CommunicationDirection(Flag):
    """Represents the actual direction of communication.

    Only two directions exist:
    - MASTER_TO_SLAVE: Data flows from master (e.g., commands, requests)
    - SLAVE_TO_MASTER: Data flows from slave (e.g., responses, data)
    """

    MASTER_TO_SLAVE = auto()
    SLAVE_TO_MASTER = auto()
    BIDIRECTIONAL = MASTER_TO_SLAVE | SLAVE_TO_MASTER
