"""Single source of truth for the commodities this dashboard supports.

Everything that needs the commodity list (validation, ingestion, queries, the UI) reads it from
here, so adding a sixth commodity later is a one-place change.  The dashboard is Rajasthan-only;
that rule lives in settings.target_state and in validation, not here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Commodity:
    name: str                      # canonical name, exactly what is stored in the database
    label: str                     # what the UI shows
    season: str                    # "rabi" or "kharif" (decides which MSP season applies)
    api_names: tuple[str, ...]     # names to ask the upstream API for, tried in order
    aliases: tuple[str, ...]       # spellings accepted from the API / CSV / query strings
    price_floor: Decimal           # sanity range in Rs/quintal: catches unit mistakes (Rs/kg, Rs/ton)
    price_ceiling: Decimal


COMMODITIES: tuple[Commodity, ...] = (
    Commodity(
        "Wheat", "Wheat", "rabi", ("Wheat",), ("wheat",),
        Decimal("1000"), Decimal("7000"),
    ),
    Commodity(
        "Mustard", "Mustard", "rabi", ("Mustard",),
        ("mustard", "rapeseed & mustard", "rapeseed and mustard", "rapeseed/mustard"),
        Decimal("2500"), Decimal("12000"),
    ),
    Commodity(
        "Bajra", "Bajra", "kharif", ("Bajra", "Bajra(Pearl Millet/Cumbu)"),
        ("bajra", "bajra(pearl millet/cumbu)", "bajra(pearl millet)", "pearl millet"),
        Decimal("800"), Decimal("6000"),
    ),
    Commodity(
        "Soybean", "Soybean", "kharif", ("Soybean", "Soyabean"),
        ("soybean", "soyabean", "soya bean", "soyabeans", "soybeans"),
        Decimal("2000"), Decimal("10000"),
    ),
    # Whole Bengal gram only.  "Gram Dal", "Black Gram (Urd)" and "Green Gram (Moong)" are
    # different commodities and are deliberately NOT aliases (they are rejected as unsupported).
    Commodity(
        "Gram", "Gram (Chana)", "rabi", ("Gram", "Bengal Gram(Gram)(Whole)", "Chana"),
        ("gram", "chana", "gram (chana)", "bengal gram", "bengal gram(gram)(whole)", "chickpea"),
        Decimal("2500"), Decimal("12000"),
    ),
)

COMMODITY_NAMES: tuple[str, ...] = tuple(c.name for c in COMMODITIES)
BY_NAME: dict[str, Commodity] = {c.name: c for c in COMMODITIES}


def _key(text) -> str:
    """Case-, space- and punctuation-spacing-insensitive comparison key."""
    return re.sub(r"\s+", "", str(text or "")).casefold()


_ALIAS_INDEX: dict[str, str] = {}
for _c in COMMODITIES:
    for _alias in (_c.name, *_c.aliases, *_c.api_names):
        _ALIAS_INDEX[_key(_alias)] = _c.name


def normalize_commodity(raw) -> str | None:
    """'Soyabean' / 'chana' / 'BAJRA(Pearl Millet/Cumbu)' -> canonical name, or None if unsupported."""
    return _ALIAS_INDEX.get(_key(raw))


def label_for(name: str) -> str:
    c = BY_NAME.get(name)
    return c.label if c else name
