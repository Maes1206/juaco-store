import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from .forms import EmailOrUsernameAuthenticationForm, RegisterForm
from .models import CartItem, Product
from .services import get_cart


PUBLIC_TEMPLATES = {
    "home": "index.html",
    "about": "about-us.html",
    "contact": "contact.html",
    "blog": "blog.html",
    "blog_detail": "blog-details.html",
    "wishlist": "shop-wishlist.html",
    "checkout": "shop-checkout.html",
}


@ensure_csrf_cookie
def page(request, name):
    template = PUBLIC_TEMPLATES.get(name)
    if not template:
        raise Http404
    return render(request, f"store/{template}")


@ensure_csrf_cookie
def shop(request):
    products = Product.objects.filter(is_active=True)
    return render(request, "store/shop.html", {"products": products})


@ensure_csrf_cookie
def product_detail(request):
    slug = request.GET.get("producto")
    product = Product.objects.filter(slug=slug, is_active=True).first() if slug else Product.objects.filter(is_active=True).first()
    return render(request, "store/single-product.html", {"product": product})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("account")
    form = EmailOrUsernameAuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        guest_cart = get_cart(request)
        login(request, form.get_user())
        guest_cart.session_key = request.session.session_key
        guest_cart.save(update_fields=["session_key", "updated_at"])
        get_cart(request)
        return redirect(request.POST.get("next") or "account")
    return render(request, "store/account-login.html", {"form": form})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("account")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        guest_cart = get_cart(request)
        user = form.save()
        login(request, user)
        guest_cart.session_key = request.session.session_key
        guest_cart.save(update_fields=["session_key", "updated_at"])
        get_cart(request)
        messages.success(request, "Tu cuenta fue creada correctamente.")
        return redirect("account")
    return render(request, "store/account-register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


@login_required
def account(request):
    cart = get_cart(request)
    return render(request, "store/account.html", {"cart": cart})


@ensure_csrf_cookie
def cart_view(request):
    return render(request, "store/shop-cart.html", {"cart": get_cart(request)})


def _cart_payload(cart):
    items = [
        {
            "id": item.id,
            "product_id": item.product.slug,
            "name": item.product.name,
            "image": item.product.image,
            "price": int(item.product.price),
            "quantity": item.quantity,
            "size": item.size,
            "subtotal": int(item.subtotal),
        }
        for item in cart.items.select_related("product")
    ]
    return {"id": cart.id, "count": cart.item_count, "subtotal": int(cart.subtotal), "items": items}


@require_http_methods(["GET"])
def cart_api(request):
    return JsonResponse(_cart_payload(get_cart(request)))


@require_POST
def cart_add_api(request):
    try:
        data = json.loads(request.body or "{}")
        quantity = max(1, int(data.get("quantity", 1)))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"error": "Datos inválidos."}, status=400)
    product = get_object_or_404(Product, slug=data.get("product_id"), is_active=True)
    if product.stock < 1:
        return JsonResponse({"error": "Producto agotado."}, status=409)
    cart = get_cart(request)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        size=str(data.get("size", ""))[:12],
        defaults={"quantity": min(quantity, product.stock)},
    )
    if not created:
        item.quantity = min(item.quantity + quantity, product.stock)
        item.save(update_fields=["quantity", "updated_at"])
    return JsonResponse(_cart_payload(cart), status=201)


@require_http_methods(["PATCH", "DELETE"])
def cart_item_api(request, item_id):
    cart = get_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    if request.method == "DELETE":
        item.delete()
    else:
        try:
            data = json.loads(request.body or "{}")
            quantity = int(data.get("quantity", 1))
        except (ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({"error": "Cantidad inválida."}, status=400)
        if quantity <= 0:
            item.delete()
        else:
            item.quantity = min(quantity, item.product.stock)
            item.save(update_fields=["quantity", "updated_at"])
    return JsonResponse(_cart_payload(cart))


def not_found(request, exception=None):
    return render(request, "store/page-not-found.html", status=404)
