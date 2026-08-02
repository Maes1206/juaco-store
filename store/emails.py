from email.mime.image import MIMEImage
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone


WELCOME_LOGO_CID = "nexus-welcome-logo"
ORDER_LOGO_CID = "nexus-order-logo"
STATUS_LOGO_CID = "nexus-status-logo"


def _attach_inline_image(message, path, cid):
    if not path.exists():
        return False
    subtype = path.suffix.lower().lstrip(".") or "png"
    if subtype == "jpg":
        subtype = "jpeg"
    image = MIMEImage(path.read_bytes(), _subtype=subtype)
    image.add_header("Content-ID", f"<{cid}>")
    image.add_header("Content-Disposition", "inline", filename=path.name)
    message.attach(image)
    return True


def _brand_logo_path():
    return settings.BASE_DIR / "shome-html" / "assets" / "img" / "shop" / "nexus-logo-horizontal-dark.png"


def _local_product_image_path(source):
    source = (source or "").split("?", 1)[0]
    if source.startswith(("/assets/", "assets/")):
        relative = source.lstrip("/")[len("assets/"):]
        return settings.BASE_DIR / "shome-html" / "assets" / relative
    if source.startswith(("/media/", "media/")):
        relative = source.lstrip("/")[len("media/"):]
        return settings.MEDIA_ROOT / relative
    return None


def _display_value(instance, method_name, fallback=""):
    method = getattr(instance, method_name, None)
    return method() if callable(method) else fallback


def send_welcome_email(user, *, account_url, shop_url):
    """Envía la bienvenida de marca sin exponer información sensible."""
    if not user.email:
        return False
    context = {
        "display_name": user.first_name.strip() or user.username,
        "account_url": account_url,
        "shop_url": shop_url,
        "logo_cid": WELCOME_LOGO_CID,
    }
    message = EmailMultiAlternatives(
        subject="Bienvenido a Nexus Luxury Footwear",
        body=render_to_string("store/emails/welcome-email.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    message.attach_alternative(render_to_string("store/emails/welcome-email.html", context), "text/html")
    _attach_inline_image(message, _brand_logo_path(), WELCOME_LOGO_CID)
    return bool(message.send(fail_silently=False))


def build_order_confirmation_message(order, *, order_url, payment_url="", recipient_email=None, items=None):
    """Construye una confirmación compatible con Django 5 y clientes en modo oscuro."""
    order_items = list(items if items is not None else order.items.all())
    email_items = []
    inline_images = []
    for index, item in enumerate(order_items, start=1):
        image_source = item.product_image or ""
        image_path = _local_product_image_path(image_source)
        if image_path and image_path.exists():
            image_cid = f"nexus-order-product-{index}"
            rendered_source = f"cid:{image_cid}"
            inline_images.append((image_path, image_cid))
        elif image_source.startswith(("https://", "http://")):
            rendered_source = image_source
        else:
            rendered_source = ""
        email_items.append({"item": item, "image_source": rendered_source})

    awaiting_payment = bool(getattr(order, "awaiting_online_payment", False) and payment_url)
    context = {
        "order": order,
        "email_items": email_items,
        "display_name": (getattr(order, "recipient_name", "") or "Cliente").split()[0],
        "payment_label": _display_value(order, "get_payment_method_display", getattr(order, "payment_method", "")),
        "delivery_label": _display_value(order, "get_delivery_method_display", getattr(order, "delivery_method", "")),
        "status_label": _display_value(order, "get_status_display", getattr(order, "status", "")),
        "action_url": payment_url if awaiting_payment else order_url,
        "action_label": "Completar pago" if awaiting_payment else "Ver mi pedido",
        "logo_cid": ORDER_LOGO_CID,
    }
    message = EmailMultiAlternatives(
        subject=f"Confirmación de pedido {order.number} | Nexus Luxury Footwear",
        body=render_to_string("store/emails/order-confirmation-email.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient_email or getattr(getattr(order, "user", None), "email", "")],
    )
    message.attach_alternative(render_to_string("store/emails/order-confirmation-email.html", context), "text/html")
    _attach_inline_image(message, _brand_logo_path(), ORDER_LOGO_CID)
    for image_path, image_cid in inline_images:
        _attach_inline_image(message, image_path, image_cid)
    return message


def send_order_confirmation_email(order, *, order_url, payment_url=""):
    """Envía una sola confirmación y libera el intento si SMTP falla."""
    from .models import Order

    recipient = getattr(getattr(order, "user", None), "email", "")
    if not recipient:
        return False
    claimed = Order.objects.filter(pk=order.pk, confirmation_email_sent_at__isnull=True).update(
        confirmation_email_sent_at=timezone.now()
    )
    if not claimed:
        return False
    try:
        sent = bool(build_order_confirmation_message(order, order_url=order_url, payment_url=payment_url).send(fail_silently=False))
    except Exception:
        Order.objects.filter(pk=order.pk).update(confirmation_email_sent_at=None)
        raise
    if not sent:
        Order.objects.filter(pk=order.pk).update(confirmation_email_sent_at=None)
        return False
    order.refresh_from_db(fields=["confirmation_email_sent_at"])
    return True


STATUS_COPY = {
    "paid": ("Pago confirmado", "Tu pago fue confirmado", "Tu compra ya está confirmada y pasará a preparación."),
    "preparing": ("Preparación", "Estamos preparando tu pedido", "Nuestro equipo está alistando cuidadosamente tus productos."),
    "shipped": ("Pedido despachado", "Tu pedido está en camino", "El pedido fue entregado a la transportadora y ya puedes consultar su guía."),
    "delivered": ("Entrega completada", "Tu pedido fue entregado", "Esperamos que disfrutes tu selección Nexus Luxury Footwear."),
    "cancelled": ("Pedido cancelado", "Tu pedido fue cancelado", "El pedido quedó cancelado y el inventario fue liberado."),
    "refunded": ("Reembolso", "Tu pedido fue reembolsado", "Registramos el reembolso y liberamos el inventario correspondiente."),
}


def build_order_status_message(history, *, order_url, recipient_email=None):
    order = history.order
    eyebrow, title, description = STATUS_COPY[history.to_status]
    context = {
        "order": order,
        "history": history,
        "display_name": (order.recipient_name or "Cliente").split()[0],
        "eyebrow": eyebrow,
        "title": title,
        "description": description,
        "order_url": order_url,
        "dispatch_receipt_url": (
            urljoin(order_url, reverse("order_dispatch_receipt", args=[order.number]))
            if order.dispatch_receipt
            else ""
        ),
        "logo_cid": STATUS_LOGO_CID,
    }
    recipient = recipient_email or getattr(getattr(order, "user", None), "email", "")
    message = EmailMultiAlternatives(
        subject=f"{title} · {order.number} | Nexus Luxury Footwear",
        body=render_to_string("store/emails/order-status-email.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    message.attach_alternative(render_to_string("store/emails/order-status-email.html", context), "text/html")
    _attach_inline_image(message, _brand_logo_path(), STATUS_LOGO_CID)
    return message


def send_order_status_email(history_id, *, order_url):
    """Notifica exactamente una vez cada cambio operativo relevante."""
    from .models import OrderStatusHistory

    history = OrderStatusHistory.objects.select_related("order__user").get(pk=history_id)
    recipient = getattr(getattr(history.order, "user", None), "email", "")
    if not recipient or history.to_status not in STATUS_COPY:
        return False
    claimed = OrderStatusHistory.objects.filter(pk=history.pk, notification_sent_at__isnull=True).update(
        notification_sent_at=timezone.now()
    )
    if not claimed:
        return False
    try:
        sent = bool(build_order_status_message(history, order_url=order_url).send(fail_silently=False))
    except Exception:
        OrderStatusHistory.objects.filter(pk=history.pk).update(notification_sent_at=None)
        raise
    if not sent:
        OrderStatusHistory.objects.filter(pk=history.pk).update(notification_sent_at=None)
        return False
    history.refresh_from_db(fields=["notification_sent_at"])
    return True
