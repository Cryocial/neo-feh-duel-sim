from enum import Enum, auto


class MovementType(Enum):
    INFANTRY = auto()
    ARMOR = auto()
    CAVALRY = auto()
    FLIER = auto()


class WeaponType(Enum):
    SWORD = auto()
    LANCE = auto()
    AXE = auto()
    BOW = auto()
    DAGGER = auto()
    TOME = auto()
    STAFF = auto()
    DRAGON = auto()
    BEAST = auto()


class Color(Enum):
    RED = auto()
    BLUE = auto()
    GREEN = auto()
    COLORLESS = auto()


class StatType(Enum):
    HP = "hp"
    ATK = "atk"
    SPD = "spd"
    DEF = "defense"
    RES = "res"


class StrikeType(Enum):
    FIRST = auto()
    FOLLOW_UP = auto()
    POTENT = auto()
