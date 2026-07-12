import json
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import Http404, JsonResponse
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import AccountDetailsForm, AddressForm, CheckoutForm, EmailOrUsernameAuthenticationForm, RegisterForm
from .models import Address, BlogCategory, BlogPost, CartItem, Favorite, Order, OrderItem, Product
from .search import UnifiedSearchService
from .services import CheckoutError, create_order_from_cart, ensure_session_key, get_cart, shipping_cost_for


PUBLIC_TEMPLATES = {
    "home": "index.html",
    "about": "about-us.html",
    "contact": "contact.html",
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
def search(request):
    results = UnifiedSearchService().search(request.GET.get("q"))
    return render(request, "store/search.html", {"search_results": results})


@ensure_csrf_cookie
def blog(request):
    posts = BlogPost.objects.filter(is_published=True).select_related("category")
    category_slug = request.GET.get("categoria")
    query = request.GET.get("q", "").strip()
    if category_slug:
        posts = posts.filter(category__slug=category_slug)
    if query:
        posts = posts.filter(Q(title__icontains=query) | Q(summary__icontains=query) | Q(content__icontains=query) | Q(tags__icontains=query))
    categories = BlogCategory.objects.annotate(published_count=Count("posts", filter=Q(posts__is_published=True)))
    return render(request, "store/blog.html", {"posts": posts, "categories": categories, "selected_category": category_slug, "query": query})


@ensure_csrf_cookie
def blog_detail(request, slug=None):
    slug = slug or request.GET.get("articulo")
    posts = BlogPost.objects.filter(is_published=True).select_related("category")
    post = get_object_or_404(posts, slug=slug) if slug else posts.first()
    if post is None:
        raise Http404
    recent_posts = posts.exclude(pk=post.pk)[:4]
    tags = sorted({tag for article_tags in posts.values_list("tags", flat=True) for tag in article_tags})
    categories = BlogCategory.objects.annotate(published_count=Count("posts", filter=Q(posts__is_published=True)))
    return render(request, "store/blog-details.html", {"post": post, "categories": categories, "recent_posts": recent_posts, "tags": tags})

@login_required
@ensure_csrf_cookie
def wishlist(request):
    favorites = request.user.favorites.select_related("product")
    return render(request, "store/shop-wishlist.html", {"favorites": favorites})

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
        guest_cart.session_key = ensure_session_key(request)
        guest_cart.save(update_fields=["session_key", "updated_at"])
        get_cart(request)
        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = "account"
        return redirect(next_url)
    return render(request, "store/account-login.html", {"form": form, "next": request.GET.get("next", "")})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("account")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        guest_cart = get_cart(request)
        user = form.save()
        login(request, user)
        guest_cart.session_key = ensure_session_key(request)
        guest_cart.save(update_fields=["session_key", "updated_at"])
        get_cart(request)
        messages.success(request, "Tu cuenta fue creada correctamente.")
        return redirect("account")
    return render(request, "store/account-register.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("home")


def _account_context(request, active_tab, **overrides):
    context = {
        "cart": get_cart(request),
        "addresses": request.user.addresses.all(),
        "orders": request.user.orders.prefetch_related(Prefetch("items", queryset=OrderItem.objects.select_related("product"), to_attr="prefetched_items")),
        "address_form": AddressForm(),
        "editing_address": None,
        "active_tab": active_tab,
        "remaining_address_slots": max(0, 5 - request.user.addresses.count()),
        "account_form": AccountDetailsForm(instance=request.user),
        "password_form": PasswordChangeForm(user=request.user),
    }
    context.update(overrides)
    return context


@login_required
def account(request):
    editing_address = None
    if request.GET.get("editar"):
        editing_address = get_object_or_404(Address, pk=request.GET["editar"], user=request.user)
    context = _account_context(
        request,
        request.GET.get("tab", "dashboard"),
        address_form=AddressForm(instance=editing_address),
        editing_address=editing_address,
    )
    return render(request, "store/account.html", context)


@login_required
@require_POST
def account_details_update(request):
    form = AccountDetailsForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, "Tus datos se actualizaron correctamente.")
        return redirect("/account.html?tab=account-info")
    messages.error(request, "Revisa los datos ingresados e inténtalo nuevamente.")
    context = _account_context(request, "account-info", account_form=form)
    return render(request, "store/account.html", context)


@login_required
@require_POST
def account_password_change(request):
    form = PasswordChangeForm(user=request.user, data=request.POST)
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Tu contraseña se actualizó correctamente.")
        return redirect("/account.html?tab=account-info")
    messages.error(request, "Revisa los datos de la contraseña e inténtalo nuevamente.")
    context = _account_context(request, "account-info", password_form=form)
    return render(request, "store/account.html", context)


@login_required
def order_detail(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number, user=request.user)
    return render(request, "store/order-detail.html", {"order": order})


@login_required
@require_POST
def address_create(request):
    if request.user.addresses.count() >= 5:
        messages.error(request, "Has alcanzado el máximo de 5 direcciones guardadas.")
        return redirect("/account.html?tab=addresses")
    form = AddressForm(request.POST)
    if form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        if address.is_default:
            request.user.addresses.update(is_default=False)
        elif not request.user.addresses.exists():
            address.is_default = True
        address.save()
        messages.success(request, "Dirección guardada correctamente.")
    else:
        messages.error(request, "Revisa los datos de la dirección e inténtalo nuevamente.")
    return redirect("/account.html?tab=addresses")


@login_required
@require_POST
def address_delete(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        replacement = request.user.addresses.first()
        if replacement:
            replacement.is_default = True
            replacement.save(update_fields=["is_default", "updated_at"])
    messages.success(request, "Dirección eliminada.")
    return redirect("/account.html?tab=addresses")


@login_required
@require_POST
def address_update(request, address_id):
    address = get_object_or_404(Address, pk=address_id, user=request.user)
    form = AddressForm(request.POST, instance=address)
    if form.is_valid():
        address = form.save(commit=False)
        if address.is_default:
            request.user.addresses.exclude(pk=address.pk).update(is_default=False)
        address.save()
        messages.success(request, "Dirección actualizada correctamente.")
    else:
        messages.error(request, "Revisa los datos de la dirección e inténtalo nuevamente.")
    return redirect("/account.html?tab=addresses")


@ensure_csrf_cookie
def cart_view(request):
    return render(request, "store/shop-cart.html", {"cart": get_cart(request)})


@login_required
@ensure_csrf_cookie
def checkout(request):
    cart = get_cart(request)
    items = cart.items.select_related("product")
    addresses = request.user.addresses.all()

    if request.method == "POST":
        if not items:
            messages.error(request, "Tu carrito está vacío.")
            return redirect("cart")
        form = CheckoutForm(request.POST, user=request.user)
        if form.is_valid():
            try:
                order = create_order_from_cart(
                    user=request.user,
                    cart=cart,
                    address=form.cleaned_data["address"],
                    payment_method=form.cleaned_data["payment_method"],
                    notes=form.cleaned_data["notes"],
                )
            except CheckoutError as exc:
                messages.error(request, str(exc))
                return redirect("checkout")
            return redirect("order_confirmation", number=order.number)
    else:
        form = CheckoutForm(user=request.user, initial={"payment_method": Order.PaymentMethod.BANK_TRANSFER})

    subtotal = cart.subtotal
    shipping = shipping_cost_for(subtotal)
    return render(request, "store/shop-checkout.html", {
        "cart": cart,
        "items": items,
        "addresses": addresses,
        "default_address": addresses.filter(is_default=True).first() or addresses.first(),
        "form": form,
        "payment_methods": Order.PaymentMethod.choices,
        "subtotal": subtotal,
        "shipping_cost": shipping,
        "total": subtotal + shipping,
        "free_shipping_threshold": 400000,
    })


@login_required
def order_confirmation(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number, user=request.user)
    return render(request, "store/order-confirmation.html", {"order": order})


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


def _favorite_payload(user):
    favorites = user.favorites.select_related("product")
    return {
        "count": favorites.count(),
        "items": [
            {
                "id": favorite.id,
                "product_id": favorite.product.slug,
                "name": favorite.product.name,
                "image": favorite.product.image,
                "price": int(favorite.product.price),
                "stock": favorite.product.stock,
            }
            for favorite in favorites
        ],
    }


@require_http_methods(["GET", "POST"])
def favorites_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión para guardar favoritos."}, status=401)
    if request.method == "POST":
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Datos inválidos."}, status=400)
        product = get_object_or_404(Product, slug=data.get("product_id"), is_active=True)
        Favorite.objects.get_or_create(user=request.user, product=product)
    return JsonResponse(_favorite_payload(request.user), status=201 if request.method == "POST" else 200)


@require_http_methods(["DELETE"])
def favorite_item_api(request, favorite_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión para gestionar favoritos."}, status=401)
    favorite = get_object_or_404(Favorite, pk=favorite_id, user=request.user)
    favorite.delete()
    return JsonResponse(_favorite_payload(request.user))


@require_POST
def favorite_move_to_cart_api(request, favorite_id):
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Inicia sesión para gestionar favoritos."}, status=401)
    favorite = get_object_or_404(Favorite.objects.select_related("product"), pk=favorite_id, user=request.user)
    product = favorite.product
    if not product.is_active or product.stock < 1:
        return JsonResponse({"error": "Este producto no está disponible."}, status=409)
    cart = get_cart(request)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, size="", defaults={"quantity": 1})
    if not created:
        item.quantity = min(item.quantity + 1, product.stock)
        item.save(update_fields=["quantity", "updated_at"])
    favorite.delete()
    return JsonResponse({"favorites": _favorite_payload(request.user), "cart": _cart_payload(cart)})

@require_http_methods(["GET"])
def session_info(request):
    if request.user.is_authenticated:
        return JsonResponse({
            "authenticated": True,
            "username": request.user.first_name or request.user.username,
            "label": "Mi cuenta",
            "href": "account.html",
        })
    return JsonResponse({
        "authenticated": False,
        "username": "",
        "label": "Cuenta",
        "href": "account-login.html",
    })


def health(request):
    return JsonResponse({"status": "ok"})


def not_found(request, exception=None):
    return render(request, "store/page-not-found.html", status=404)
