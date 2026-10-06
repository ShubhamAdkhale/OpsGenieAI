"""Indian-numbering rupee formatting.

Python's `{:,}` groups in thousands (410,000). Indian convention groups the
last three digits then in pairs (4,10,000). The frontend already formats its
own numbers with `en-IN`, so backend-generated sentences must match or the
same figure appears two different ways on one screen.
"""

from __future__ import annotations


def indian_group(amount: float) -> str:
    """4_10_000.0 -> '4,10,000'"""
    negative = amount < 0
    digits = f"{abs(int(round(amount)))}"
    if len(digits) <= 3:
        grouped = digits
    else:
        last_three = digits[-3:]
        rest = digits[:-3]
        pairs = []
        while len(rest) > 2:
            pairs.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            pairs.insert(0, rest)
        grouped = ",".join([*pairs, last_three])
    return f"-{grouped}" if negative else grouped


def inr(amount: float) -> str:
    """Rupee figure with the symbol, e.g. '₹4,10,000'.

    Uses the ₹ sign rather than "Rs" so backend-generated sentences match the
    figures the frontend renders beside them.
    """
    return f"₹{indian_group(amount)}"
