"""Row-level validation/cleaning. Pure Python (no DB, no network) so it is easy to test."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

ALLOWED_COMMODITIES = {"wheat": "Wheat", "mustard": "Mustard"}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
MISSING_TOKENS = {"", "na", "n/a", "nan", "null", "none", "-", "--"}
MAX_PRICE = Decimal("1000000")  # Rs/quintal sanity cap; also keeps DECIMAL(10,2) safe
CENT = Decimal("0.01")

MAX_LEN = {"state": 100, "district": 150, "market": 200,
           "commodity": 100, "variety": 150, "grade": 100}


def clean_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def parse_date(value) -> date:
    text = clean_text(value)
    if text.lower() in MISSING_TOKENS:
        raise ValueError("missing date")
    head = text[:10]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unparseable date '{text}'")


def parse_price(value, field: str) -> Decimal | None:
    """None for genuinely missing values; ValueError for present-but-bad values."""
    if value is None:
        return None
    text = clean_text(value).replace(",", "")
    if text.lower() in MISSING_TOKENS:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"{field} is not numeric ('{text}')")
    if not number.is_finite():
        raise ValueError(f"{field} is not a finite number")
    if number < 0:
        raise ValueError(f"{field} is negative ({number})")
    if number > MAX_PRICE:
        raise ValueError(f"{field} is implausibly large ({number})")
    return number.quantize(CENT)


def make_record_hash(price_date: date, state: str, district: str, market: str,
                     commodity: str, variety: str, grade: str) -> str:
    parts = [price_date.isoformat()] + [
        s.casefold() for s in (state, district, market, commodity, variety, grade)
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def validate_record(raw, expected_state: str = "Rajasthan", today: date | None = None):
    """Return (clean_row_dict, None) or (None, rejection_reason)."""
    if not isinstance(raw, dict):
        return None, "record is not an object"
    today = today or date.today()

    try:
        price_date = parse_date(raw.get("date") or raw.get("arrival_date"))
    except ValueError as exc:
        return None, str(exc)
    if price_date < date(2000, 1, 1) or price_date > today + timedelta(days=1):
        return None, f"date out of range ({price_date})"

    state = clean_text(raw.get("state")) or expected_state
    if state.casefold() != expected_state.casefold():
        return None, f"unexpected state '{state}'"
    state = expected_state

    district = clean_text(raw.get("district"))
    market = clean_text(raw.get("market"))
    if not district:
        return None, "missing district"
    if not market:
        return None, "missing market"

    commodity_raw = clean_text(raw.get("commodity"))
    commodity = ALLOWED_COMMODITIES.get(commodity_raw.casefold())
    if not commodity:
        return None, f"unsupported commodity '{commodity_raw}'"

    variety = clean_text(raw.get("variety"))
    grade = clean_text(raw.get("grade"))

    try:
        min_p = parse_price(raw.get("min_price"), "min_price")
        max_p = parse_price(raw.get("max_price"), "max_price")
        modal_p = parse_price(raw.get("modal_price"), "modal_price")
    except ValueError as exc:
        return None, str(exc)
    if min_p is None and max_p is None and modal_p is None:
        return None, "no prices present"
    if min_p is not None and max_p is not None and min_p > max_p:
        return None, f"min_price {min_p} greater than max_price {max_p}"

    row = {
        "price_date": price_date, "state": state,
        "district": district[: MAX_LEN["district"]],
        "market": market[: MAX_LEN["market"]],
        "commodity": commodity,
        "variety": variety[: MAX_LEN["variety"]],
        "grade": grade[: MAX_LEN["grade"]],
        "min_price": min_p, "max_price": max_p, "modal_price": modal_p,
    }
    row["record_hash"] = make_record_hash(
        price_date, state, row["district"], row["market"], commodity,
        row["variety"], row["grade"],
    )
    return row, None
