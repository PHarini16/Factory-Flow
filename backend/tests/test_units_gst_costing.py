from decimal import Decimal

import pytest

from app.core import units
from app.services import stock
from app.services.gst import amount_in_words, compute_line
from app.services.production import pct_variance

D = Decimal


def test_unit_conversions():
    assert units.convert(D("2"), "kg", "g") == D("2000")
    assert units.convert(D("500"), "ml", "litre") == D("0.5")
    assert units.convert(D("3"), "packet", "piece") == D("3")
    assert units.convert(D("1.5"), "L", "ml") == D("1500")


def test_incompatible_units_rejected():
    with pytest.raises(units.UnitError):
        units.convert(D("1"), "kg", "litre")
    with pytest.raises(units.UnitError):
        units.convert(D("1"), "carton", "piece")
    with pytest.raises(units.UnitError):
        units.normalize_unit("bushel")


def test_gst_intra_state():
    g = compute_line(D("150"), D("50"), D("5"), interstate=False)
    assert (g.taxable, g.cgst, g.sgst, g.igst, g.total) == (D("7500.00"), D("187.50"), D("187.50"), D("0.00"), D("7875.00"))


def test_gst_inter_state():
    g = compute_line(D("120"), D("50"), D("5"), interstate=True)
    assert (g.taxable, g.cgst, g.sgst, g.igst, g.total) == (D("6000.00"), D("0.00"), D("0.00"), D("300.00"), D("6300.00"))


def test_gst_rounding_is_decimal_exact():
    g = compute_line(D("3"), D("33.33"), D("5"), False)  # 99.99 taxable
    assert g.taxable == D("99.99") and g.cgst == D("2.50") and g.sgst == D("2.50")


def test_amount_in_words():
    assert amount_in_words(D("7875")) == "Rupees Seven Thousand Eight Hundred Seventy Five Only"
    assert amount_in_words(D("125000.50")) == "Rupees One Lakh Twenty Five Thousand and Fifty Paise Only"


def test_variance_formula():
    assert pct_variance(D("188"), D("200")) == D("-6")
    assert pct_variance(D("10.5"), D("10")) == D("5")
    assert pct_variance(D("1"), D("0")) == D("0")


def test_weighted_average_flour(db, items, users):
    flour = items["RM-FLOUR"]
    from datetime import date
    stock.post_movement(db, item=flour, quantity=D("60"), unit="kg", direction="IN", movement_type="PURCHASE_RECEIPT", txn_date=date.today(),
                        source_type="T", source_id=1, user=users["admin"], rate=D("45"))
    assert flour.avg_cost == D("43.125")
    assert stock.balance(db, flour.id) == D("160")


def test_weighted_average_with_unit_conversion(db, items, users):
    from datetime import date
    flour = items["RM-FLOUR"]
    # 10,000 g at Rs 0.045/g == 10 kg at Rs 45/kg
    stock.post_movement(db, item=flour, quantity=D("10000"), unit="g", direction="IN", movement_type="PURCHASE_RECEIPT", txn_date=date.today(),
                        source_type="T", source_id=1, user=users["admin"], rate=D("0.045"))
    assert stock.balance(db, flour.id) == D("110")
    assert flour.avg_cost == (D("4200") + D("450")) / D("110")
