"""PDF generation with ReportLab: GST tax invoice and payment receipt."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Invoice, Payment
from app.services.gst import amount_in_words

NAVY = colors.HexColor("#1e293b")
TEAL = colors.HexColor("#0f766e")


def _money(v) -> str:
    return f"{v:,.2f}"


def invoice_pdf(inv: Invoice) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Invoice {inv.invoice_no}")
    ss = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8.5, leading=11)
    bold = ParagraphStyle("bold", parent=small, fontName="Helvetica-Bold")
    title = ParagraphStyle("t", parent=ss["Title"], fontSize=18, textColor=NAVY, alignment=0, spaceAfter=2)
    el = [Paragraph(inv.seller_name, title),
          Paragraph(f"{inv.seller_address}<br/>GSTIN: {inv.seller_gstin}", small), Spacer(1, 6)]
    kind = "TAX INVOICE" + (" (CANCELLED)" if inv.status == "CANCELLED" else "")
    head = Table([[Paragraph(f"<b>{kind}</b>", ParagraphStyle("k", parent=small, fontSize=12, textColor=colors.white)),
                   Paragraph(f"<b>Invoice No:</b> {inv.invoice_no}<br/><b>Date:</b> {inv.invoice_date:%d-%m-%Y}<br/>"
                             f"<b>Due:</b> {inv.due_date:%d-%m-%Y} &nbsp; <b>FY:</b> {inv.financial_year}", small)]],
                 colWidths=[70 * mm, 112 * mm])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("PADDING", (0, 0), (-1, -1), 6)]))
    el += [head, Spacer(1, 6)]
    buyer = Table([[Paragraph(f"<b>Bill To</b><br/>{inv.buyer_name}<br/>{inv.buyer_address}<br/>GSTIN: {inv.buyer_gstin or 'Unregistered'}", small),
                    Paragraph(f"<b>Place of Supply</b><br/>{inv.place_of_supply} ({inv.place_of_supply_code})<br/>"
                              f"Supply type: {'Inter-state (IGST)' if inv.is_interstate else 'Intra-state (CGST + SGST)'}", small)]],
                  colWidths=[91 * mm, 91 * mm])
    buyer.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey), ("PADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    el += [buyer, Spacer(1, 8)]
    rows = [["#", "Description", "HSN", "Qty", "Rate", "Taxable", "CGST", "SGST", "IGST", "Total"]]
    for n, it in enumerate(inv.items, 1):
        rows.append([n, Paragraph(it.description, small), it.hsn_code, f"{it.quantity.normalize():f} {it.unit}", _money(it.unit_price), _money(it.taxable_amount),
                     _money(it.cgst), _money(it.sgst), _money(it.igst), _money(it.total)])
    rows.append(["", "Total", "", "", "", _money(inv.taxable_amount), _money(inv.cgst), _money(inv.sgst), _money(inv.igst), _money(inv.total)])
    t = Table(rows, repeatRows=1, colWidths=[8 * mm, 40 * mm, 14 * mm, 20 * mm, 16 * mm, 20 * mm, 16 * mm, 16 * mm, 14 * mm, 18 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("ALIGN", (3, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    el += [t, Spacer(1, 8),
           Paragraph(f"<b>Total payable: Rs. {_money(inv.total)}</b>", ParagraphStyle("tp", parent=small, fontSize=11, textColor=TEAL)),
           Paragraph(f"Amount in words: {amount_in_words(inv.total)}", small), Spacer(1, 18)]
    sig = Table([[Paragraph("Terms & Conditions<br/>1. Goods once sold will not be taken back except for quality defects.<br/>"
                            "2. Payment due by the due date shown above.<br/>3. Subject to Tamil Nadu jurisdiction.<br/>"
                            "4. Prototype document - GST treatment is a simplified exercise assumption.", small),
                  Paragraph(f"For {inv.seller_name}<br/><br/><br/><br/>Authorised Signatory", ParagraphStyle("s", parent=small, alignment=2))]],
                colWidths=[110 * mm, 72 * mm])
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.lightgrey)]))
    el.append(sig)
    doc.build(el)
    return buf.getvalue()


def receipt_pdf(p: Payment, invoice_nos: list[str]) -> bytes:
    from app.core.config import get_settings
    s = get_settings()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"Receipt {p.receipt_no}")
    ss = getSampleStyleSheet()
    el = [Paragraph(s.factory_name, ss["Title"]), Paragraph("PAYMENT RECEIPT", ss["Heading2"]), Spacer(1, 8)]
    data = [["Receipt No", p.receipt_no], ["Date", f"{p.payment_date:%d-%m-%Y}"], ["Received from", p.customer.name],
            ["Against invoice(s)", ", ".join(invoice_nos)], ["Mode", p.mode], ["Reference", p.reference or "-"],
            ["Amount", f"Rs. {_money(p.amount)}"], ["In words", amount_in_words(p.amount)]]
    t = Table(data, colWidths=[45 * mm, 120 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey), ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9"))]))
    el += [t, Spacer(1, 40), Paragraph("Authorised Signatory", ss["Normal"])]
    doc.build(el)
    return buf.getvalue()
