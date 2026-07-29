from enum import Enum


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class MarketState(StringEnum):
    T_PLUS = "T+"
    T_MINUS = "T-"
    RANGE = "R"
    U = "U"


class MilestoneStatus(StringEnum):
    CONFIRMED = "CONFIRMED"
    CANDIDATE = "CANDIDATE"
    BLOCKED = "BLOCKED"
    INVALIDATED = "INVALIDATED"


class ActionType(StringEnum):
    WAIT_FOR_DATA = "WAIT_FOR_DATA"
    WAIT_FOR_SETUP = "WAIT_FOR_SETUP"
    WATCH_ENTRY = "WATCH_ENTRY"
    ENTER_CONDITIONAL = "ENTER_CONDITIONAL"
    HOLD = "HOLD"
    ADD_CONDITIONAL = "ADD_CONDITIONAL"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class PositionDirection(StringEnum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"
    UNKNOWN = "UNKNOWN"


class EvidenceUsage(StringEnum):
    EXACT = "EXACT"
    QUALITATIVE_ONLY = "QUALITATIVE_ONLY"
    BLOCKED = "BLOCKED"


class ImageRole(StringEnum):
    STATE_DAILY = "STATE_DAILY"
    EXECUTION_60M = "EXECUTION_60M"
    MEMBER_POSITION = "MEMBER_POSITION"
    CONTRACT_ROLLOVER = "CONTRACT_ROLLOVER"
    ACCOUNT_POSITION = "ACCOUNT_POSITION"
    AUXILIARY = "AUXILIARY"
