"""Integración con la pasarela de pagos Bold.

Documentación: https://developers.bold.co/pagos-en-linea/boton-de-pagos
El botón se abre en el navegador con la llave de identidad; la llave secreta solo
se usa en el servidor para firmar el cobro y validar los webhooks.
"""

import base64
import hashlib
import hmac
import json
import logging
from decimal import ROUND_HALF_UP, Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.urls import reverse


logger = logging.getLogger(__name__)

# Bold rechaza cobros por debajo de $1.000 COP y descripciones de más de 100 caracteres.
MINIMUM_AMOUNT = Decimal("1000")
DESCRIPTION_MAX_LENGTH = 100

STATUS_PROCESSING = "PROCESSING"
STATUS_PENDING = "PENDING"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_FAILED = "FAILED"
STATUS_VOIDED = "VOIDED"
STATUS_NO_TRANSACTION = "NO_TRANSACTION_FOUND"

# Estados finales que permiten reintentar con una referencia nueva.
RETRYABLE_STATUSES = frozenset({STATUS_REJECTED, STATUS_FAILED})
# Un intento en curso: no se debe generar otra referencia todavía.
IN_PROGRESS_STATUSES = frozenset({STATUS_PROCESSING, STATUS_PENDING})

WEBHOOK_EVENT_STATUSES = {
    "SALE_APPROVED": STATUS_APPROVED,
    "SALE_REJECTED": STATUS_REJECTED,
    "VOID_APPROVED": STATUS_VOIDED,
}


class BoldNotConfigured(Exception):
    """Faltan la llave de identidad o la llave secreta."""


class BoldRequestError(Exception):
    """La consulta a la API de Bold no se pudo completar."""


def is_configured():
    return bool(settings.BOLD_IDENTITY_KEY and settings.BOLD_SECRET_KEY)


def ensure_configured():
    if not is_configured():
        raise BoldNotConfigured("Configura BOLD_IDENTITY_KEY y BOLD_SECRET_KEY para cobrar con Bold.")


def amount_for(total):
    """Bold cobra en unidades enteras de la moneda, sin decimales."""
    return int(Decimal(total).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def integrity_signature(reference, amount, currency=None):
    """SHA256 de {referencia}{monto}{moneda}{llave secreta}."""
    ensure_configured()
    currency = currency or settings.BOLD_CURRENCY
    chain = f"{reference}{amount}{currency}{settings.BOLD_SECRET_KEY}"
    return hashlib.sha256(chain.encode("utf-8")).hexdigest()


def public_url(request, path):
    """URL absoluta preferiendo el dominio público configurado para Bold."""
    if settings.BOLD_PUBLIC_BASE_URL:
        return f"{settings.BOLD_PUBLIC_BASE_URL}{path}"
    return request.build_absolute_uri(path)


def _https_only(url):
    """Bold exige HTTPS en las URLs de retorno; en local no hay una válida."""
    return url if url.lower().startswith("https://") else ""


def description_for(order):
    names = [item.product_name for item in order.items.all()]
    detail = ", ".join(names) if names else "Compra en Nexus Luxury Footwear"
    description = f"Pedido {order.number}: {detail}"
    if len(description) > DESCRIPTION_MAX_LENGTH:
        description = description[: DESCRIPTION_MAX_LENGTH - 3].rstrip(" ,") + "..."
    return description


def customer_data(order):
    user = order.user
    profile = getattr(user, "customer_profile", None) if user else None
    document_number = getattr(profile, "document_number", "") or ""
    phone = "".join(char for char in (order.phone or "") if char.isdigit())
    data = {
        "email": getattr(user, "email", "") or "",
        "fullName": order.recipient_name,
        "phone": phone,
        "dialCode": "+57",
    }
    if document_number:
        data["documentNumber"] = document_number
        data["documentType"] = "CC"
    return {key: value for key, value in data.items() if value}


def billing_address(order):
    address = order.address_line_1
    if order.address_line_2:
        address = f"{address}, {order.address_line_2}"
    data = {
        "address": address,
        "zipCode": order.postal_code,
        "city": order.city,
        "state": order.department,
        "country": "CO",
    }
    return {key: value for key, value in data.items() if value}


def checkout_config(order, request):
    """Configuración que consume `new BoldCheckout(...)` en el navegador."""
    ensure_configured()
    amount = amount_for(order.total)
    if amount < MINIMUM_AMOUNT:
        raise BoldNotConfigured(f"Bold solo procesa cobros desde ${MINIMUM_AMOUNT:,.0f} COP.")
    reference = order.payment_reference
    config = {
        "orderId": reference,
        "currency": settings.BOLD_CURRENCY,
        "amount": str(amount),
        "apiKey": settings.BOLD_IDENTITY_KEY,
        "integritySignature": integrity_signature(reference, amount, settings.BOLD_CURRENCY),
        "description": description_for(order),
        "customerData": json.dumps(customer_data(order)),
        "billingAddress": json.dumps(billing_address(order)),
        "extraData1": order.number,
    }
    redirection_url = _https_only(public_url(request, reverse("bold_return")))
    if redirection_url:
        config["redirectionUrl"] = redirection_url
    origin_url = _https_only(public_url(request, reverse("order_payment", args=[order.number])))
    if origin_url:
        config["originUrl"] = origin_url
    return config


def webhook_url(request):
    return public_url(request, reverse("bold_webhook"))


def fetch_payment_status(reference):
    """Consulta el estado real de la venta en Bold. Lanza BoldRequestError si falla."""
    ensure_configured()
    url = f"{settings.BOLD_API_BASE_URL}/v2/payment-voucher/{reference}"
    request = Request(
        url,
        headers={
            "Authorization": f"x-api-key {settings.BOLD_IDENTITY_KEY}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=settings.BOLD_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        # Mientras no exista un intento de pago, Bold responde 404 o un 400 de
        # validación del comprobante; en ambos casos no hay nada que registrar.
        if exc.code in {400, 404}:
            logger.info("Bold aún no reporta pagos para %s (HTTP %s): %s", reference, exc.code, detail)
            return {"payment_status": STATUS_NO_TRANSACTION, "reference_id": reference}
        logger.warning("Bold respondió %s al consultar %s: %s", exc.code, reference, detail)
        raise BoldRequestError("Bold no pudo confirmar el estado del pago.") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        logger.warning("Fallo al consultar el pago %s en Bold: %s", reference, exc)
        raise BoldRequestError("No pudimos comunicarnos con Bold. Intenta de nuevo.") from exc

    # La API envuelve el comprobante dentro de "payload".
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else body
    if not payload.get("payment_status"):
        payload = {**payload, "payment_status": STATUS_NO_TRANSACTION}
    return payload


def _webhook_keys():
    """En modo de pruebas Bold firma los eventos con una llave vacía."""
    keys = [settings.BOLD_SECRET_KEY]
    if settings.BOLD_TEST_MODE:
        keys.append("")
    return keys


def verify_webhook_signature(raw_body, signature):
    """HMAC-SHA256 de la petición en base64, comparado con la cabecera x-bold-signature."""
    if not signature:
        return False
    encoded_body = base64.b64encode(raw_body)
    for key in _webhook_keys():
        expected = hmac.new(key.encode("utf-8"), encoded_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature.strip().lower()):
            return True
    return False


def webhook_reference(event):
    """Referencia del comercio dentro del evento (data.metadata.reference)."""
    data = event.get("data") or {}
    metadata = data.get("metadata") or {}
    return metadata.get("reference") or data.get("reference") or ""


def webhook_transaction_id(event):
    data = event.get("data") or {}
    return event.get("subject") or data.get("payment_id") or ""
