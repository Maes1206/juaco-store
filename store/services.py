from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone as django_timezone

from . import bold
from .models import Cart, CartItem, Coupon, CouponRedemption, Order, OrderItem, Product


FREE_SHIPPING_THRESHOLD = Decimal("400000")
FLAT_SHIPPING_RATE = Decimal("15000")


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

class CheckoutError(Exception):
    """Se lanza cuando el carrito no puede convertirse en pedido."""


def _variant_signature(entries):
    return sorted((entry.product_id, entry.quantity, entry.size, entry.color) for entry in entries)


def _equivalent_pending_order(user, items, address, delivery_method, total):
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
    items = list(cart.items.select_related("product"))
    if not items:
        raise CheckoutError("Tu carrito está vacío.")

    for item in items:
        if not item.product.is_active:
            raise CheckoutError(f"El producto «{item.product.name}» ya no está disponible.")
        if item.quantity > item.product.stock:
            raise CheckoutError(f"No hay stock suficiente de «{item.product.name}» (disponibles: {item.product.stock}).")

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
        pending = _equivalent_pending_order(user, items, address, delivery_method, total)
        if pending is not None:
            return pending

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

    for item in items:
        OrderItem.objects.create(
            order=order,
            product=item.product,
            product_name=item.product.name,
            product_image=item.product.image,
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
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(
                stock=Greatest(F("stock") - item.quantity, Value(0))
            )

    if order.coupon_id and not CouponRedemption.objects.filter(order=order).exists():
        CouponRedemption.objects.create(
            coupon_id=order.coupon_id,
            user=order.user,
            order=order,
            discount_amount=order.discount_amount,
        )
        Coupon.objects.filter(pk=order.coupon_id).update(times_used=F("times_used") + 1)

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
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)


@transaction.atomic
def apply_payment_status(order, status, transaction_id=""):
    """Registra el estado informado por Bold. Es idempotente: los webhooks se reintentan."""
    locked = Order.objects.select_for_update().get(pk=order.pk)
    fields = set()

    if transaction_id and locked.payment_transaction_id != transaction_id:
        locked.payment_transaction_id = transaction_id
        fields.add("payment_transaction_id")

    if status and locked.payment_status != status:
        locked.payment_status = status
        fields.add("payment_status")

    if status == bold.STATUS_APPROVED and locked.status == Order.Status.PENDING:
        locked.status = Order.Status.PAID
        locked.paid_at = django_timezone.now()
        fields.update({"status", "paid_at"})
        # Recién aquí se descuenta el inventario, se canjea el cupón y se vacía
        # el carrito: hasta ahora la compra seguía disponible para el cliente.
        commit_order(locked)
    elif status == bold.STATUS_VOIDED and locked.status != Order.Status.CANCELLED:
        if locked.stock_reserved:
            # Una anulación libera el inventario que se descontó al aprobarse.
            _restore_stock(locked)
            locked.stock_reserved = False
            fields.add("stock_reserved")
        locked.status = Order.Status.CANCELLED
        fields.add("status")

    if fields:
        fields.add("updated_at")
        locked.save(update_fields=sorted(fields))

    for field in ("status", "payment_status", "payment_transaction_id", "paid_at"):
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
            for item in session_cart.items.select_related("product"):
                target, created = CartItem.objects.get_or_create(
                    cart=cart,
                    product=item.product,
                    size=item.size,
                    color=item.color,
                    defaults={"quantity": item.quantity},
                )
                if not created:
                    target.quantity = min(target.quantity + item.quantity, item.product.stock)
                    target.save(update_fields=["quantity", "updated_at"])
            session_cart.delete()
        if cart.session_key != session_key:
            cart.session_key = session_key
            cart.save(update_fields=["session_key", "updated_at"])
        return cart
    cart, _ = Cart.objects.get_or_create(user__isnull=True, session_key=session_key, status=Cart.Status.ACTIVE)
    return cart
