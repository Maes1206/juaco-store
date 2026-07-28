from html import escape
from io import BytesIO
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


# Nombre conservado para compatibilidad interna; ahora representa el dorado de marca.
RED = colors.HexColor("#C7A26A")
INK = colors.HexColor("#171717")
MUTED = colors.HexColor("#6b7280")
LINE = colors.HexColor("#e5e7eb")
PANEL = colors.HexColor("#f7f7f8")


def _money(value):
    return f"${value:,.0f} COP".replace(",", ".")


def _local_asset(value):
    if not value:
        return None
    clean = str(value).split("?", 1)[0].replace("\\", "/").lstrip("/")
    static_prefix = settings.STATIC_URL.strip("/")
    media_prefix = settings.MEDIA_URL.strip("/")
    if static_prefix and clean.startswith(f"{static_prefix}/"):
        clean = clean[len(static_prefix) + 1 :]
    candidates = [
        Path(settings.BASE_DIR) / "shome-html" / clean,
        Path(settings.BASE_DIR) / "shome-html" / "assets" / clean,
        Path(settings.BASE_DIR) / clean,
    ]
    if media_prefix and clean.startswith(f"{media_prefix}/"):
        candidates.insert(0, Path(settings.MEDIA_ROOT) / clean[len(media_prefix) + 1 :])
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _scaled_image(path, max_width, max_height):
    try:
        image = Image(str(path))
        ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
        image.drawWidth = image.imageWidth * ratio
        image.drawHeight = image.imageHeight * ratio
        return image
    except Exception:
        return Spacer(max_width, max_height)


def _footer(canvas, doc):
    canvas.saveState()
    width, _ = A4
    canvas.setStrokeColor(LINE)
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 9 * mm, "NEXUS LUXURY FOOTWEAR  |  Comprobante de compra")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Pagina {doc.page}")
    canvas.restoreState()


def build_order_receipt(order):
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=15 * mm,
        bottomMargin=21 * mm,
        title=f"Comprobante {order.number}",
        author="Nexus Luxury Footwear",
        subject="Comprobante de compra",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("ReceiptTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=19, leading=22, textColor=INK, spaceAfter=3 * mm)
    eyebrow = ParagraphStyle("Eyebrow", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=RED, charSpace=1.1)
    heading = ParagraphStyle("Heading", parent=styles["Heading3"], fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=INK, spaceAfter=2 * mm)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=colors.HexColor("#404040"))
    small = ParagraphStyle("Small", parent=body, fontSize=7.5, leading=10, textColor=MUTED)
    right = ParagraphStyle("Right", parent=body, alignment=TA_RIGHT)
    total_style = ParagraphStyle("Total", parent=right, fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=INK)
    center_small = ParagraphStyle("CenterSmall", parent=small, alignment=TA_CENTER)

    logo_path = Path(settings.BASE_DIR) / "shome-html" / "assets" / "img" / "shop" / "nexus-logo-horizontal.png"
    logo = _scaled_image(logo_path, 49 * mm, 17 * mm)
    header_text = [
        Paragraph("COMPROBANTE DE COMPRA", eyebrow),
        Paragraph(escape(order.number), title),
        Paragraph(f"Emitido el {order.created_at:%d/%m/%Y a las %H:%M}", small),
    ]
    header = Table([[logo, header_text]], colWidths=[76 * mm, 98 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    status_label = escape(order.get_status_display())
    delivery_label = escape(order.get_delivery_method_display())
    payment_label = escape(order.get_payment_method_display())
    info = Table([
        [Paragraph("CLIENTE", eyebrow), Paragraph("TIPO DE ENVIO", eyebrow), Paragraph("PAGO", eyebrow), Paragraph("ESTADO", eyebrow)],
        [Paragraph(f"<b>{escape(order.recipient_name)}</b><br/>{escape(order.phone)}", body), Paragraph(f"<b>{delivery_label}</b><br/>{escape(order.city)}, {escape(order.department)}", body), Paragraph(payment_label, body), Paragraph(f"<font color='#0f766e'><b>{status_label}</b></font>", body)],
    ], colWidths=[50 * mm, 46 * mm, 43 * mm, 35 * mm])
    info.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, 0), 1.2 * mm),
        ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 4 * mm),
        ("LINEBEFORE", (1, 0), (-1, -1), 0.5, LINE),
    ]))

    story = [header, Spacer(1, 6 * mm), HRFlowable(width="100%", thickness=1.6, color=RED), Spacer(1, 6 * mm), info, Spacer(1, 8 * mm), Paragraph("Articulos del pedido", heading)]
    rows = [[Paragraph("PRODUCTO", eyebrow), Paragraph("DETALLES", eyebrow), Paragraph("CANT.", eyebrow), Paragraph("TOTAL", eyebrow)]]
    for item in order.items.all():
        path = _local_asset(item.product_image)
        preview = _scaled_image(path, 24 * mm, 20 * mm) if path else Paragraph("Sin imagen", center_small)
        product = Table([[preview, Paragraph(f"<b>{escape(item.product_name)}</b><br/><font color='#6b7280'>Precio unitario: {_money(item.unit_price)}</font>", body)]], colWidths=[28 * mm, 64 * mm])
        product.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm), ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        details = []
        if item.size:
            details.append(f"Talla: {escape(item.size)}")
        if item.color:
            details.append(f"Color: {escape(item.color)}")
        rows.append([product, Paragraph("<br/>".join(details) or "-", body), Paragraph(str(item.quantity), body), Paragraph(f"<b>{_money(item.subtotal)}</b>", right)])
    products = Table(rows, colWidths=[96 * mm, 34 * mm, 16 * mm, 28 * mm], repeatRows=1)
    products.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efefef")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, 0), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3 * mm), ("TOPPADDING", (0, 1), (-1, -1), 4 * mm),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4 * mm), ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
    ]))
    story.extend([products, Spacer(1, 7 * mm)])

    address = f"<b>{escape(order.recipient_name)}</b><br/>{escape(order.address_line_1)}"
    if order.address_line_2:
        address += f", {escape(order.address_line_2)}"
    address += f"<br/>{escape(order.city)}, {escape(order.department)}"
    if order.postal_code:
        address += f" - {escape(order.postal_code)}"
    address += f"<br/>Tel. {escape(order.phone)}"
    summary_rows = [[Paragraph("Subtotal", body), Paragraph(_money(order.subtotal), right)]]
    if order.discount_amount > 0:
        coupon = f"Descuento{f' ({escape(order.coupon_code)})' if order.coupon_code else ''}"
        summary_rows.append([Paragraph(coupon, body), Paragraph(f"-{_money(order.discount_amount)}", right)])
    summary_rows.extend([
        [Paragraph("Envio", body), Paragraph(_money(order.shipping_cost) if order.shipping_cost > 0 else "Gratis", right)],
        [Paragraph("TOTAL PAGADO" if order.status == order.Status.PAID else "TOTAL DEL PEDIDO", eyebrow), Paragraph(_money(order.total), total_style)],
    ])
    totals = Table(summary_rows, colWidths=[45 * mm, 40 * mm])
    totals.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm), ("TOPPADDING", (0, 0), (-1, -2), 2.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 2.5 * mm), ("LINEABOVE", (0, -1), (-1, -1), 1.3, INK),
        ("TOPPADDING", (0, -1), (-1, -1), 4 * mm),
    ]))
    delivery = [Paragraph("Entrega", heading), Paragraph(address, body), Spacer(1, 3 * mm), Paragraph("TIPO DE ENVIO", eyebrow), Paragraph(delivery_label, body)]
    if order.notes:
        delivery.extend([Spacer(1, 3 * mm), Paragraph("NOTAS", eyebrow), Paragraph(escape(order.notes), body)])
    closing = Table([[delivery, totals]], colWidths=[87 * mm, 87 * mm])
    closing.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8 * mm), ("LEFTPADDING", (1, 0), (1, 0), 5 * mm),
        ("RIGHTPADDING", (1, 0), (1, 0), 0), ("LINEBEFORE", (1, 0), (1, 0), 0.5, LINE),
    ]))
    thanks = ParagraphStyle("Thanks", parent=heading, alignment=TA_CENTER, fontSize=11, textColor=RED)
    story.extend([KeepTogether(closing), Spacer(1, 9 * mm), Paragraph("Gracias por elegir Nexus Luxury Footwear", thanks), Paragraph("Conserva este comprobante como soporte de tu compra.", center_small)])
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    output.seek(0)
    return output
