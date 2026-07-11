from .services import get_cart


def cart_summary(request):
    if request.path.startswith("/admin/"):
        return {}
    try:
        cart = get_cart(request)
        return {"global_cart_count": cart.item_count, "global_cart": cart}
    except Exception:
        return {"global_cart_count": 0}
