from datetime import datetime, timezone
from decimal import Decimal

from django.db import transaction

from .models import Cart, CartItem, Order, OrderItem


FREE_SHIPPING_THRESHOLD = Decimal("400000")
FLAT_SHIPPING_RATE = Decimal("15000")


def shipping_cost_for(subtotal):
    """Envío gratis desde $400.000 COP; de lo contrario tarifa fija."""
    if subtotal >= FREE_SHIPPING_THRESHOLD:
        return Decimal("0")
    if subtotal <= 0:
        return Decimal("0")
    return FLAT_SHIPPING_RATE


def _generate_order_number():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"JS-{stamp}-"
    last = Order.objects.filter(number__startswith=prefix).order_by("-number").first()
    sequence = int(last.number.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{sequence:04d}"


class CheckoutError(Exception):
    """Se lanza cuando el carrito no puede convertirse en pedido."""


@transaction.atomic
def create_order_from_cart(user, cart, address, payment_method, notes=""):
    items = list(cart.items.select_related("product"))
    if not items:
        raise CheckoutError("Tu carrito está vacío.")

    for item in items:
        if not item.product.is_active:
            raise CheckoutError(f"El producto «{item.product.name}» ya no está disponible.")
        if item.quantity > item.product.stock:
            raise CheckoutError(f"No hay stock suficiente de «{item.product.name}» (disponibles: {item.product.stock}).")

    subtotal = sum((item.subtotal for item in items), Decimal("0"))
    shipping = shipping_cost_for(subtotal)

    order = Order.objects.create(
        user=user,
        number=_generate_order_number(),
        payment_method=payment_method,
        recipient_name=address.recipient_name,
        phone=address.phone,
        address_line_1=address.address_line_1,
        address_line_2=address.address_line_2,
        department=address.department,
        city=address.city,
        postal_code=address.postal_code,
        subtotal=subtotal,
        shipping_cost=shipping,
        total=subtotal + shipping,
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
        )
        item.product.stock = max(0, item.product.stock - item.quantity)
        item.product.save(update_fields=["stock"])

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
