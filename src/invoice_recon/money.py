"""Parse printed amounts to integer USD cents with Decimal; never float, never round."""

import re
from decimal import Decimal

_MONEY_RE = re.compile(r"^(\d{1,3}(,\d{3})+|\d+)(\.\d+)?$")
_INT_RE = re.compile(r"^\d+$")


class MoneyError(ValueError):
    """A printed amount or quantity cannot be parsed under the exercise rules."""


def parse_money(text: str | None) -> int:
    """Convert a printed amount such as "$1,234.50" to 123450 cents.

    More than two decimals, negatives and unparsable text raise MoneyError.
    """
    if text is None:
        raise MoneyError("missing")
    cleaned = re.sub(r"\s+", "", text).replace("$", "", 1)
    if not _MONEY_RE.match(cleaned):
        raise MoneyError(f"not a valid amount: {text!r}")
    number = Decimal(cleaned.replace(",", ""))
    if -number.as_tuple().exponent > 2:
        raise MoneyError(f"more than two decimals: {text!r}")
    return int(number * 100)


def parse_quantity(text: str | None) -> int:
    """Positive integer only."""
    if text is None:
        raise MoneyError("missing")
    cleaned = text.strip()
    if not _INT_RE.match(cleaned) or int(cleaned) <= 0:
        raise MoneyError(f"not a positive integer: {text!r}")
    return int(cleaned)


def format_cents(cents: int) -> str:
    """12000 -> "$120.00"."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}${whole:,}.{frac:02d}"
