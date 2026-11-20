"""Unit conversion using canonical base units.

Dimensions:  mass -> g,  volume -> ml,  count -> piece (packet/piece interchangeable).
Carton is its own dimension: a carton's size is product-specific so it is never
implicitly convertible to pieces. Incompatible dimensions raise UnitError.
"""
from decimal import Decimal

D = Decimal

# unit -> (dimension, factor to the dimension's base unit)
UNITS: dict[str, tuple[str, Decimal]] = {
    "kg": ("mass", D("1000")),
    "g": ("mass", D("1")),
    "litre": ("volume", D("1000")),
    "ml": ("volume", D("1")),
    "piece": ("count", D("1")),
    "packet": ("count", D("1")),
    "carton": ("carton", D("1")),
}

ALIASES = {"l": "litre", "liter": "litre", "pcs": "piece", "pc": "piece", "kgs": "kg"}


class UnitError(ValueError):
    pass


def normalize_unit(unit: str) -> str:
    u = (unit or "").strip()
    if u in UNITS:
        return u
    u = ALIASES.get(u.lower(), u.lower())
    if u not in UNITS:
        raise UnitError(f"Unsupported unit '{unit}'. Supported: {', '.join(UNITS)}")
    return u


def dimension(unit: str) -> str:
    return UNITS[normalize_unit(unit)][0]


def to_base(qty: Decimal, unit: str) -> Decimal:
    return Decimal(qty) * UNITS[normalize_unit(unit)][1]


def convert(qty: Decimal, from_unit: str, to_unit: str) -> Decimal:
    f, t = normalize_unit(from_unit), normalize_unit(to_unit)
    if UNITS[f][0] != UNITS[t][0]:
        raise UnitError(f"Cannot convert between incompatible units '{f}' ({UNITS[f][0]}) and '{t}' ({UNITS[t][0]})")
    return Decimal(qty) * UNITS[f][1] / UNITS[t][1]
