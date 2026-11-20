"""GST calculation engine (simplified exercise assumption - see README)."""
from dataclasses import dataclass
from decimal import Decimal

from app.services.common import q2


@dataclass
class GstLine:
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal

    @property
    def tax(self) -> Decimal:
        return self.cgst + self.sgst + self.igst

    @property
    def total(self) -> Decimal:
        return self.taxable + self.tax


def is_interstate(factory_state_code: str, place_of_supply_code: str) -> bool:
    return factory_state_code != place_of_supply_code


def compute_line(quantity: Decimal, unit_price: Decimal, rate: Decimal, interstate: bool) -> GstLine:
    """Intra-state: CGST = SGST = rate/2.  Inter-state: IGST = rate. Exact Decimal maths."""
    taxable = q2(Decimal(quantity) * Decimal(unit_price))
    if interstate:
        return GstLine(taxable, Decimal("0.00"), Decimal("0.00"), q2(taxable * rate / 100))
    half = q2(taxable * rate / 200)
    return GstLine(taxable, half, half, Decimal("0.00"))


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
         "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_1000(n: int) -> str:
    parts = []
    if n >= 100:
        parts.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        parts.append(_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))
    elif n > 0:
        parts.append(_ONES[n])
    return " ".join(parts)


def amount_in_words(amount: Decimal) -> str:
    """Indian numbering (lakh / crore). e.g. 7875 -> 'Rupees Seven Thousand Eight Hundred Seventy Five Only'."""
    amount = q2(amount)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    parts = []
    crore, rupees_rem = divmod(rupees, 10_000_000)
    lakh, rupees_rem = divmod(rupees_rem, 100_000)
    thousand, rest = divmod(rupees_rem, 1000)
    if crore:
        parts.append(_below_1000(crore) + " Crore")
    if lakh:
        parts.append(_below_1000(lakh) + " Lakh")
    if thousand:
        parts.append(_below_1000(thousand) + " Thousand")
    if rest:
        parts.append(_below_1000(rest))
    words = " ".join(parts) or "Zero"
    out = f"Rupees {words}"
    if paise:
        out += f" and {_below_1000(paise)} Paise"
    return out + " Only"
