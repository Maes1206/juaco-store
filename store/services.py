from django.db import transaction

from .models import Cart, CartItem


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


@transaction.atomic
def get_cart(request):
    session_key = _session_key(request)
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
