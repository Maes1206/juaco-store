from datetime import datetime, timezone
from decimal import Decimal
import logging

from django.conf import settings
from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.urls import reverse
from django.utils import timezone as django_timezone

from . import bold
from .models import Cart, CartItem, Coupon, CouponRedemption, Order, OrderItem, OrderStatusHistory, Product, ProductVariant


FREE_SHIPPING_THRESHOLD = Decimal("400000")
FLAT_SHIPPING_RATE = Decimal("15000")
logger = logging.getLogger(__name__)


def shipping_cost_for(subtotal, quoted_cost=None):
    """Aplica envío gratis o la cotización guardada; conserva una tarifa de respaldo."""
    subtotal = Decimal(subtotal)
    if subtotal >= FREE_SHIPPING_THRESHOLD or subtotal <= 0:
        return Decimal("0")
    if quoted_cost is not None:
        return max(Decimal("0"), Decimal(str(quoted_cost)))
    return FLAT_SHIPPING_RATE


def _generate_order_number():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"JS-{stamp}-"
    last = Order.objects.filter(number__startswith=prefix).order_by("-number").first()
    sequence = int(last.number.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{sequence:04d}"


class CouponError(Exception):
    """Se lanza cuando un cupon no se puede aplicar o canjear."""


def validate_coupon(code, subtotal, user=None, for_update=False):
    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        raise CouponError("Ingresa un codigo de cupon.")
    queryset = Coupon.objects.select_for_update() if for_update else Coupon.objects.all()
    coupon = queryset.filter(code__iexact=normalized_code, is_active=True).first()
    if coupon is None:
        raise CouponError("El cupon no existe o esta inactivo.")
    now = django_timezone.now()
    if now < coupon.starts_at:
        raise CouponError("El cupon aun no esta vigente.")
    if now >= coupon.expires_at:
        raise CouponError("El cupon ya expiro.")
    if Decimal(subtotal) < coupon.minimum_purchase:
        raise CouponError(f"Este cupon requiere una compra minima de ${coupon.minimum_purchase:,.0f} COP.")
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        raise CouponError("El cupon alcanzo su limite de usos.")
    if user and user.is_authenticated and coupon.once_per_user and coupon.redemptions.filter(user=user).exists():
        raise CouponError("Ya utilizaste este cupon anteriormente.")
    return coupon


def coupon_totals(code, subtotal, user=None):
    if not code:
        return None, Decimal("0")
    coupon = validate_coupon(code, subtotal, user=user)
    return coupon, coupon.discount_for(subtotal)


def _validate_coupon_reservation(coupon, user):
    """Evita prometer mas canjes de los disponibles mientras un pago esta pendiente."""
    pending_orders = Order.objects.filter(
        coupon=coupon,
        status=Order.Status.PENDING,
        payment_method=Order.PaymentMethod.BOLD,
        stock_reserved=False,
    )
    if coupon.usage_limit is not None:
        reserved_uses = pending_orders.count()
        if coupon.times_used + reserved_uses >= coupon.usage_limit:
            raise CouponError("El cupon alcanzo su limite de usos.")
    if user and user.is_authenticated and coupon.once_per_user and pending_orders.filter(user=user).exists():
        raise CouponError("Ya tienes un pago pendiente con este cupon.")

class CheckoutError(Exception):
    """Se lanza cuando el carrito no puede convertirse en pedido."""


class OrderTransitionError(Exception):
    """Se lanza cuando un cambio de estado rompe el flujo operativo."""


def _variant_signature(entries):
    return sorted((entry.product_id, entry.variant_id, entry.quantity, entry.size, entry.color) for entry in entries)


def _equivalent_pending_order(user, items, address, delivery_method, total, coupon=None):
    """Pedido pendiente idéntico ya creado, para no duplicarlo si el cliente reintenta.

    Al conservar el carrito hasta el pago, volver atrás y confirmar otra vez llegaría
    aquí de nuevo; se reutiliza el mismo pedido en lugar de acumular pendientes.
    """
    if user is None or not user.is_authenticated:
        return None
    signature = _variant_signature(items)
    candidates = Order.objects.filter(
        user=user,
        status=Order.Status.PENDING,
        payment_method=Order.PaymentMethod.BOLD,
        stock_reserved=False,
        total=total,
        coupon=coupon,
        delivery_method=delivery_method,
        recipient_name=address.recipient_name,
        address_line_1=address.address_line_1,
    ).prefetch_related("items").order_by("-created_at")
    for candidate in candidates:
        if _variant_signature(candidate.items.all()) == signature:
            return candidate
    return None


@transaction.atomic
def create_order_from_cart(user, cart, address, payment_method, notes="", coupon_code="", shipping_cost=None, delivery_method=Order.DeliveryMethod.COURIER):
    items = list(cart.items.select_related("product", "variant"))
    if not items:
        raise CheckoutError("Tu carrito está vacío.")

    for item in items:
        if not item.product.is_active:
            raise CheckoutError(f"El producto «{item.product.name}» ya no está disponible.")
        available_stock = item.available_stock
        if item.quantity > available_stock:
            raise CheckoutError(f"No hay stock suficiente de «{item.product.name}» (disponibles: {available_stock}).")

    subtotal = sum((item.subtotal for item in items), Decimal("0"))
    shipping = shipping_cost_for(subtotal, quoted_cost=shipping_cost)
    coupon = None
    discount = Decimal("0")
    if coupon_code:
        try:
            coupon = validate_coupon(coupon_code, subtotal, user=user, for_update=True)
        except CouponError as exc:
            raise CheckoutError(str(exc)) from exc
        discount = coupon.discount_for(subtotal)

    total = max(Decimal("0"), subtotal - discount) + shipping
    if payment_method == Order.PaymentMethod.BOLD:
        pending = _equivalent_pending_order(user, items, address, delivery_method, total, coupon=coupon)
        if pending is not None:
            return pending
        if coupon is not None:
            try:
                _validate_coupon_reservation(coupon, user)
            except CouponError as exc:
                raise CheckoutError(str(exc)) from exc

    order = Order.objects.create(
        user=user,
        number=_generate_order_number(),
        payment_method=payment_method,
        delivery_method=delivery_method,
        recipient_name=address.recipient_name,
        phone=address.phone,
        address_line_1=address.address_line_1,
        address_line_2=address.address_line_2,
        department=address.department,
        city=address.city,
        postal_code=address.postal_code,
        subtotal=subtotal,
        shipping_cost=shipping,
        coupon=coupon,
        coupon_code=coupon.code if coupon else "",
        discount_amount=discount,
        total=total,
        notes=notes,
    )
    OrderStatusHistory.objects.create(
        order=order,
        from_status="",
        to_status=Order.Status.PENDING,
        source=OrderStatusHistory.Source.SYSTEM,
        note="Pedido creado correctamente.",
    )

    for item in items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            variant=item.variant,
            variant_sku=item.variant.sku if item.variant_id and item.variant.sku else "",
            product_name=item.product.name,
            product_image=item.product.main_image_source,
            unit_price=item.product.price,
            quantity=item.quantity,
            size=item.size,
            color=item.color,
        )

    if order.awaiting_online_payment:
        # El carrito, el inventario y el cupón se conservan intactos hasta que la
        # pasarela apruebe: si el cliente se devuelve, su compra sigue ahí.
        return order

    commit_order(order, cart=cart)
    return order


@transaction.atomic
def commit_order(order, cart=None):
    """Aplica los efectos definitivos del pedido: inventario, cupón y carrito.

    Se ejecuta al crear el pedido cuando el pago es offline, y al aprobarse el
    cobro cuando pasa por la pasarela. Es idempotente.
    """
    if order.stock_reserved:
        return order

    for item in order.items.all():
        if item.variant_id:
            variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
            if item.quantity > variant.stock:
                raise CheckoutError(
                    f"No hay stock suficiente de «{item.product_name}» en {variant.label} "
                    f"(disponibles: {variant.stock})."
                )
            variant.stock -= item.quantity
            variant.save(update_fields=("stock", "updated_at"))
        elif item.product_id:
            Product.objects.filter(pk=item.product_id).update(
                stock=Greatest(F("stock") - item.quantity, Value(0))
            )

    if order.coupon_id and not CouponRedemption.objects.filter(order=order).exists():
        coupon = Coupon.objects.select_for_update().get(pk=order.coupon_id)
        if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
            raise CheckoutError("El cupon alcanzo su limite de usos antes de confirmar el pago.")
        if coupon.once_per_user and coupon.redemptions.filter(user=order.user).exists():
            raise CheckoutError("Este usuario ya utilizo el cupon anteriormente.")
        CouponRedemption.objects.create(
            coupon=coupon,
            user=order.user,
            order=order,
            discount_amount=order.discount_amount,
        )
        coupon.times_used += 1
        coupon.save(update_fields=("times_used", "updated_at"))

    if cart is not None:
        carts = Cart.objects.filter(pk=cart.pk, status=Cart.Status.ACTIVE)
    elif order.user_id:
        carts = Cart.objects.filter(user_id=order.user_id, status=Cart.Status.ACTIVE)
    else:
        # Sin dueño identificable no se toca ningún carrito: filtrar por user=None
        # arrasaría con los carritos de todos los invitados.
        carts = Cart.objects.none()
    for active_cart in carts:
        active_cart.items.all().delete()
        active_cart.status = Cart.Status.CONVERTED
        active_cart.save(update_fields=["status", "updated_at"])

    order.stock_reserved = True
    order.save(update_fields=["stock_reserved", "updated_at"])
    return order


class PaymentError(Exception):
    """Se lanza cuando el cobro en la pasarela no se puede preparar o confirmar."""


@transaction.atomic
def ensure_payment_reference(order):
    """Devuelve la referencia vigente para Bold y crea una nueva tras un intento fallido.

    Reutilizar la referencia mantiene consultable el intento en curso; después de un
    rechazo Bold exige un identificador distinto para poder volver a cobrar.
    """
    locked = Order.objects.select_for_update().get(pk=order.pk)
    if locked.payment_reference and locked.payment_status not in bold.RETRYABLE_STATUSES:
        order.payment_reference = locked.payment_reference
        order.payment_status = locked.payment_status
        return locked.payment_reference

    locked.payment_attempts += 1
    locked.payment_reference = f"{locked.number}-{locked.payment_attempts}"
    locked.payment_status = ""
    locked.payment_transaction_id = ""
    locked.save(update_fields=["payment_reference", "payment_status", "payment_transaction_id", "payment_attempts", "updated_at"])

    order.payment_reference = locked.payment_reference
    order.payment_status = locked.payment_status
    order.payment_transaction_id = locked.payment_transaction_id
    order.payment_attempts = locked.payment_attempts
    return locked.payment_reference


def _restore_stock(order):
    for item in order.items.all():
        if item.variant_id:
            variant = ProductVariant.objects.select_for_update().get(pk=item.variant_id)
            variant.stock += item.quantity
            variant.save(update_fields=("stock", "updated_at"))
        elif item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)


FULFILLMENT_STATUS_BY_ORDER_STATUS = {
    Order.Status.PENDING: Order.FulfillmentStatus.PENDING_SHIPMENT,
    Order.Status.PAID: Order.FulfillmentStatus.PENDING_SHIPMENT,
    Order.Status.PREPARING: Order.FulfillmentStatus.PACKING,
    Order.Status.SHIPPED: Order.FulfillmentStatus.IN_TRANSIT,
    Order.Status.DELIVERED: Order.FulfillmentStatus.DELIVERED,
}
NOTIFIABLE_ORDER_STATUSES = {
    Order.Status.PAID,
    Order.Status.PREPARING,
    Order.Status.SHIPPED,
    Order.Status.DELIVERED,
    Order.Status.CANCELLED,
    Order.Status.REFUNDED,
}


def _public_order_url(order):
    base_url = (
        getattr(settings, "PUBLIC_SITE_URL", "")
        or getattr(settings, "BOLD_PUBLIC_BASE_URL", "")
        or "http://127.0.0.1:8000"
    ).rstrip("/")
    return f"{base_url}{reverse('order_detail', args=[order.number])}"


def _send_status_notification(history_id, order_url):
    from .emails import send_order_status_email

    try:
        send_order_status_email(history_id, order_url=order_url)
    except Exception:
        logger.exception("No se pudo enviar la notificación del cambio de estado %s.", history_id)


def _transition_locked_order(
    order,
    target_status,
    *,
    actor=None,
    note="",
    source=OrderStatusHistory.Source.SYSTEM,
    order_url="",
    notify=True,
):
    """Aplica una transición sobre un pedido bloqueado por la transacción actual."""
    target_status = str(target_status)
    if target_status == order.status:
        return None
    if target_status not in order.available_transition_values:
        labels = dict(Order.Status.choices)
        raise OrderTransitionError(
            f"No se puede pasar de «{order.get_status_display()}» a "
            f"«{labels.get(target_status, target_status)}»."
        )

    if target_status == Order.Status.SHIPPED and order.delivery_method == Order.DeliveryMethod.COURIER:
        if not order.carrier.strip() or not order.tracking_number.strip():
            raise OrderTransitionError("Indica la transportadora y el número de guía antes de marcar el pedido como enviado.")

    previous_status = order.status
    fields = {"status", "fulfillment_status", "updated_at"}
    now = django_timezone.now()

    if target_status == Order.Status.PAID:
        if not order.stock_reserved:
            commit_order(order)
        if order.paid_at is None:
            order.paid_at = now
            fields.add("paid_at")
    elif target_status in {Order.Status.CANCELLED, Order.Status.REFUNDED}:
        if order.stock_reserved:
            _restore_stock(order)
            order.stock_reserved = False
            fields.add("stock_reserved")

    order.status = target_status
    if target_status in FULFILLMENT_STATUS_BY_ORDER_STATUS:
        order.fulfillment_status = FULFILLMENT_STATUS_BY_ORDER_STATUS[target_status]
    if target_status == Order.Status.SHIPPED and order.shipped_at is None:
        order.shipped_at = now
        fields.add("shipped_at")
    if target_status == Order.Status.DELIVERED and order.delivered_at is None:
        order.delivered_at = now
        fields.add("delivered_at")
    order.save(update_fields=sorted(fields))

    history = OrderStatusHistory.objects.create(
        order=order,
        from_status=previous_status,
        to_status=target_status,
        source=source,
        note=(note or "").strip()[:300],
        changed_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    if notify and target_status in NOTIFIABLE_ORDER_STATUSES and order.user_id and order.user.email:
        destination = order_url or _public_order_url(order)
        transaction.on_commit(lambda: _send_status_notification(history.pk, destination))
    return history


@transaction.atomic
def transition_order(
    order,
    target_status,
    *,
    actor=None,
    note="",
    source=OrderStatusHistory.Source.SYSTEM,
    order_url="",
    notify=True,
):
    """Cambia el estado con bloqueo, auditoría, inventario y notificación idempotentes."""
    locked = Order.objects.select_for_update().select_related("user").get(pk=order.pk)
    history = _transition_locked_order(
        locked,
        target_status,
        actor=actor,
        note=note,
        source=source,
        order_url=order_url,
        notify=notify,
    )
    for field in (
        "status", "fulfillment_status", "stock_reserved", "paid_at", "shipped_at", "delivered_at",
    ):
        setattr(order, field, getattr(locked, field))
    return locked, history


@transaction.atomic
def apply_payment_status(
    order,
    status,
    transaction_id="",
    *,
    source=OrderStatusHistory.Source.PAYMENT,
    order_url="",
):
    """Registra el estado informado por Bold. Es idempotente: los webhooks se reintentan."""
    locked = Order.objects.select_for_update().select_related("user").get(pk=order.pk)
    fields = set()

    accepts_reported_status = not (
        (locked.is_closed and status != bold.STATUS_VOIDED)
        or (locked.is_paid and status not in {bold.STATUS_APPROVED, bold.STATUS_VOIDED})
        or (locked.payment_status == bold.STATUS_VOIDED and status != bold.STATUS_VOIDED)
    )

    if transaction_id and accepts_reported_status and locked.payment_transaction_id != transaction_id:
        locked.payment_transaction_id = transaction_id
        fields.add("payment_transaction_id")

    if status and accepts_reported_status and locked.payment_status != status:
        locked.payment_status = status
        fields.add("payment_status")

    if status == bold.STATUS_APPROVED and locked.status == Order.Status.PENDING:
        if fields:
            fields.add("updated_at")
            locked.save(update_fields=sorted(fields))
            fields.clear()
        # Recién aquí se descuenta el inventario, se canjea el cupón y se vacía
        # el carrito: hasta ahora la compra seguía disponible para el cliente.
        _transition_locked_order(
            locked,
            Order.Status.PAID,
            source=source,
            note="Pago confirmado por la pasarela.",
            order_url=order_url,
        )
    elif status == bold.STATUS_VOIDED and not locked.is_closed:
        if fields:
            fields.add("updated_at")
            locked.save(update_fields=sorted(fields))
            fields.clear()
        target_status = Order.Status.CANCELLED if locked.status == Order.Status.PENDING else Order.Status.REFUNDED
        _transition_locked_order(
            locked,
            target_status,
            source=source,
            note="Anulación confirmada por la pasarela.",
            order_url=order_url,
        )
            # Una anulación libera el inventario que se descontó al aprobarse.

    if fields:
        fields.add("updated_at")
        locked.save(update_fields=sorted(fields))

    for field in (
        "status", "fulfillment_status", "stock_reserved", "payment_status", "payment_transaction_id",
        "paid_at", "shipped_at", "delivered_at",
    ):
        setattr(order, field, getattr(locked, field))
    return locked


def sync_payment_status(order):
    """Consulta Bold y actualiza el pedido. Devuelve el estado informado."""
    if not order.payment_reference:
        return bold.STATUS_NO_TRANSACTION
    try:
        payload = bold.fetch_payment_status(order.payment_reference)
    except (bold.BoldNotConfigured, bold.BoldRequestError) as exc:
        raise PaymentError(str(exc)) from exc
    status = payload.get("payment_status") or bold.STATUS_NO_TRANSACTION
    apply_payment_status(order, status, transaction_id=payload.get("transaction_id") or "")
    return status


def ensure_session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


@transaction.atomic
def get_cart(request):
    session_key = ensure_session_key(request)
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user, status=Cart.Status.ACTIVE, defaults={"session_key": session_key})
        session_cart = Cart.objects.filter(user__isnull=True, session_key=session_key, status=Cart.Status.ACTIVE).exclude(pk=cart.pk).first()
        if session_cart:
            for item in session_cart.items.select_related("product", "variant"):
                target, created = CartItem.objects.get_or_create(
                    cart=cart,
                    product=item.product,
                    variant=item.variant,
                    size=item.size,
                    color=item.color,
                    defaults={"quantity": item.quantity},
                )
                if not created:
                    target.quantity = min(target.quantity + item.quantity, item.available_stock)
                    target.save(update_fields=["quantity", "updated_at"])
            session_cart.delete()
        if cart.session_key != session_key:
            cart.session_key = session_key
            cart.save(update_fields=["session_key", "updated_at"])
        return cart
    cart, _ = Cart.objects.get_or_create(user__isnull=True, session_key=session_key, status=Cart.Status.ACTIVE)
    return cart
