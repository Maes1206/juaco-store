from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone as django_timezone

from .models import Cart, CartItem, Coupon, CouponRedemption, Order, OrderItem


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
        total=max(Decimal("0"), subtotal - discount) + shipping,
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
        item.product.stock = max(0, item.product.stock - item.quantity)
        item.product.save(update_fields=["stock"])

    if coupon:
        CouponRedemption.objects.create(coupon=coupon, user=user, order=order, discount_amount=discount)
        Coupon.objects.filter(pk=coupon.pk).update(times_used=F("times_used") + 1)

    cart.items.all().delete()
    cart.status = Cart.Status.CONVERTED
    cart.save(update_fields=["status", "updated_at"])

    return order


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
