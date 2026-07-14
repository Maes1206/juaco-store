import json
from types import SimpleNamespace
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.forms import PasswordChangeForm
from django.http import Http404, JsonResponse
from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models.functions import TruncMonth
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import AccountDetailsForm, AddressForm, BlogCommentForm, CheckoutForm, ContactRequestForm, EmailOrUsernameAuthenticationForm, NewsletterSubscriptionForm, ProductReviewForm, RegisterForm
from .models import Address, BlogCategory, BlogComment, BlogPost, Cart, CartItem, ContactRequest, Coupon, CustomerProfile, Favorite, HomeBanner, MarketingPopup, NewsletterSubscription, Order, OrderItem, Product, ProductReview
from .search import UnifiedSearchService
from .services import CouponError, CheckoutError, coupon_totals, create_order_from_cart, ensure_session_key, get_cart, shipping_cost_for
from .shipping import DEPARTMENTS, DESTINATIONS, calculate_shipping


PUBLIC_TEMPLATES = {
    "home": "index.html",
    "about": "about-us.html",
    "contact": "contact.html",
    "wishlist": "shop-wishlist.html",
    "checkout": "shop-checkout.html",
}


CATALOG_SECTIONS = {
    "hombre": {"title": "Hombre", "subtitle": "Sneakers seleccionados para hombre.", "image": "https://unsplash.com/photos/SUUGUg7RXYY/download?force=true&w=1800", "alt": "Hombre con sneakers negros y blancos en estilo urbano", "banner_credit_name": "Creaslim", "banner_credit_url": "https://unsplash.com/photos/um-homem-encostado-a-uma-parede-usando-tenis-preto-e-branco-SUUGUg7RXYY", "editorial_image": "https://unsplash.com/photos/k4ucH7p-aNE/download?force=true&w=1200", "editorial_alt": "Hombre mostrando sus sneakers", "credit_name": "Kaithleen Gonzalez", "credit_url": "https://unsplash.com/photos/man-showing-his-sneaker-k4ucH7p-aNE"},
    "mujer": {"title": "Mujer", "subtitle": "Sneakers para combinar a tu manera.", "image": "https://unsplash.com/photos/7WRaJmvTJLQ/download?force=true&w=1800", "alt": "Mujer saltando con sneakers blancos", "banner_credit_name": "Frankie", "banner_credit_url": "https://unsplash.com/photos/woman-jumps-using-white-sneakers-7WRaJmvTJLQ", "editorial_image": "https://unsplash.com/photos/DM5iENjcd30/download?force=true&w=1200", "editorial_alt": "Mujer con sneakers de estilo creativo", "credit_name": "ZUZANA", "credit_url": "https://unsplash.com/photos/woman-wearing-sneaker-and-sandal-DM5iENjcd30"},
    "clasicas": {"title": "Clasicas", "subtitle": "Los modelos esenciales de todos los tiempos.", "image": "https://unsplash.com/photos/RVlCGo-KHeA/download?force=true&w=1800", "alt": "Par de sneakers blancos clasicos", "banner_credit_name": "SJ", "banner_credit_url": "https://unsplash.com/photos/a-pair-of-white-sneakers-RVlCGo-KHeA", "editorial_image": "https://unsplash.com/photos/XwWGyrVidZE/download?force=true&w=1200", "editorial_alt": "Sneakers Adidas blanco y negro", "credit_name": "Eddie Palmore", "credit_url": "https://unsplash.com/photos/black-and-white-adidas-sneakers-XwWGyrVidZE"},
    "nike": {"title": "Nike", "subtitle": "Siluetas iconicas que marcaron la cultura sneaker.", "image": "https://unsplash.com/photos/GXNOb23Jon8/download?force=true&w=1800", "alt": "Sneakers Nike en entorno urbano", "editorial_image": "https://unsplash.com/photos/GXNOb23Jon8/download?force=true&w=1200", "editorial_alt": "Sneakers Nike negros, blancos y naranjas", "credit_name": "Erik Mclean", "credit_url": "https://unsplash.com/photos/a-close-up-of-a-persons-feet-wearing-nike-sneakers-GXNOb23Jon8"},
}

@ensure_csrf_cookie
def page(request, name):
    template = PUBLIC_TEMPLATES.get(name)
    if not template:
        raise Http404
    context = {}
    if name == "home":
        context["home_banners"] = HomeBanner.objects.filter(is_active=True)
        context["marketing_popup"] = MarketingPopup.objects.filter(is_active=True).first()
    elif name == "contact":
        initial = {}
        if request.user.is_authenticated:
            initial = {"name": request.user.get_full_name() or request.user.username, "email": request.user.email}
        form = ContactRequestForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, "Recibimos tu solicitud. Nuestro equipo te contactara pronto.")
            return redirect("contact")
        context["contact_form"] = form
    return render(request, f"store/{template}", context)


@require_POST
def newsletter_subscribe(request):
    try:
        payload = json.loads(request.body or "{}") if request.content_type == "application/json" else request.POST
    except json.JSONDecodeError:
        return JsonResponse({"message": "La solicitud no es válida."}, status=400)

    form = NewsletterSubscriptionForm(payload)
    if not form.is_valid():
        return JsonResponse({"message": "Ingresa un correo electrónico válido."}, status=400)

    email = form.cleaned_data["email"]
    subscription, created = NewsletterSubscription.objects.get_or_create(email=email)
    if not created and not subscription.is_active:
        subscription.is_active = True
        subscription.updated_at = timezone.now()
        subscription.save(update_fields=("is_active", "updated_at"))

    message = "¡Listo! Te avisaremos de los próximos drops." if created else "Este correo ya está suscrito a los próximos drops."
    return JsonResponse({"message": message, "created": created})

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
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.get_full_name() or request.user.username, "email": request.user.email}
    comment_form = BlogCommentForm(request.POST or None, initial=initial)
    if request.method == "POST" and comment_form.is_valid():
        comment = comment_form.save(commit=False)
        comment.post = post
        comment.user = request.user if request.user.is_authenticated else None
        parent_id = request.POST.get("parent_id")
        if parent_id:
            parent = post.comments.filter(pk=parent_id, is_approved=True).first()
            comment.parent = parent.parent if parent and parent.parent_id else parent
        comment.save()
        messages.success(request, "Tu comentario o respuesta fue recibido y quedo pendiente de aprobacion.")
        return redirect(f"/blog/{post.slug}/#comentarios")
    approved_replies = BlogComment.objects.filter(is_approved=True).select_related("user").order_by("created_at")
    comments = post.comments.filter(is_approved=True, parent__isnull=True).prefetch_related(
        Prefetch("replies", queryset=approved_replies, to_attr="approved_replies")
    )
    comment_count = post.comments.filter(is_approved=True).count()
    return render(request, "store/blog-details.html", {"post": post, "categories": categories, "recent_posts": recent_posts, "tags": tags, "comments": comments, "comment_count": comment_count, "comment_form": comment_form})

@login_required
@ensure_csrf_cookie
def wishlist(request):
    favorites = request.user.favorites.select_related("product")
    return render(request, "store/shop-wishlist.html", {"favorites": favorites})

@ensure_csrf_cookie
def shop(request):
    products = Product.objects.filter(is_active=True)
    audience = request.GET.get("genero")
    collection = request.GET.get("coleccion")
    product_type = request.GET.get("tipo")
    brand = request.GET.get("marca")
    if audience:
        products = products.filter(audience=audience)
    if collection:
        products = products.filter(collection=collection)
    if product_type:
        products = products.filter(product_type=product_type)
    if brand:
        products = products.filter(brand__iexact=brand)
    return render(request, "store/shop.html", {"products": products})


@ensure_csrf_cookie
def catalog_section(request, section):
    section_data = CATALOG_SECTIONS.get(section)
    if section_data is None:
        raise Http404
    return render(request, "store/catalog-section.html", {"catalog_section": section_data})


@ensure_csrf_cookie
def product_detail(request):
    slug = request.GET.get("producto")
    if slug:
        product = get_object_or_404(Product, slug=slug, is_active=True)
    else:
        product = Product.objects.filter(is_active=True).order_by("brand", "name").first()
        if product is None:
            raise Http404
    initial = {}
    if request.user.is_authenticated:
        initial = {"name": request.user.get_full_name() or request.user.username, "email": request.user.email}
    if request.method == "POST" and not request.user.is_authenticated:
        messages.info(request, "Inicia sesion para puntuar y recomendar productos.")
        return redirect(f"/account-login.html?next=/single-product.html%3Fproducto%3D{product.slug}%23reviews")
    review_form = ProductReviewForm(request.POST or None, initial=initial)
    if request.method == "POST" and product and review_form.is_valid():
        review = review_form.save(commit=False)
        review.product = product
        review.user = request.user
        review.name = request.user.get_full_name() or request.user.username
        review.email = request.user.email
        review.save()
        messages.success(request, "Tu puntuacion y recomendacion fueron recibidas y quedaron pendientes de aprobacion.")
        return redirect(f"/single-product.html?producto={product.slug}#reviews")
    reviews = product.reviews.filter(is_approved=True).select_related("user") if product else ProductReview.objects.none()
    review_stats = reviews.aggregate(average=Avg("rating"), total=Count("id"), recommendations=Count("id", filter=Q(recommends=True)))
    recommendation_percent = round((review_stats["recommendations"] / review_stats["total"]) * 100) if review_stats["total"] else 0
    related_products = Product.objects.filter(is_active=True, stock__gt=0).exclude(pk=product.pk).filter(
        Q(audience=product.audience) | Q(brand__iexact=product.brand)
    ).order_by("brand", "name")[:4]
    return render(request, "store/single-product.html", {
        "product": product,
        "related_products": related_products,
        "reviews": reviews,
        "review_form": review_form,
        "review_average": review_stats["average"] or 0,
        "review_count": review_stats["total"],
        "recommendation_percent": recommendation_percent,
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("admin_dashboard" if request.user.is_staff else "account")
    form = EmailOrUsernameAuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        guest_cart = get_cart(request)
        login(request, form.get_user())
        guest_cart.session_key = ensure_session_key(request)
        guest_cart.save(update_fields=["session_key", "updated_at"])
        get_cart(request)
        next_url = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            next_url = "admin_dashboard" if request.user.is_staff else "account"
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
    cart = get_cart(request)
    addresses = request.user.addresses.all()
    orders = request.user.orders.prefetch_related(
        Prefetch("items", queryset=OrderItem.objects.select_related("product"), to_attr="prefetched_items")
    )
    profile_complete = all((request.user.first_name.strip(), request.user.last_name.strip(), request.user.email.strip()))
    context = {
        "cart": cart,
        "addresses": addresses,
        "orders": orders,
        "address_form": AddressForm(),
        "editing_address": None,
        "active_tab": active_tab,
        "remaining_address_slots": max(0, 5 - addresses.count()),
        "account_form": AccountDetailsForm(instance=request.user),
        "password_form": PasswordChangeForm(user=request.user),
        "show_account_checklist": not orders.exists(),
        "account_checklist": (
            {"label": "Completa tu perfil", "description": "Agrega tus nombres, apellidos y correo.", "href": "?tab=account-info", "completed": profile_complete},
            {"label": "Agrega una direccion", "description": "Guarda tu direccion para agilizar tu compra.", "href": "?tab=addresses", "completed": addresses.exists()},
            {"label": "Explora la tienda", "description": "Encuentra tus proximos sneakers favoritos.", "href": "shop.html", "completed": False},
        ),
        "recommended_products": Product.objects.filter(is_active=True, stock__gt=0).exclude(cart_items__cart=cart).exclude(slug="adidas-campus").order_by("brand", "name")[:3],
    }
    context.update(overrides)
    return context
ADMIN_PANEL_SECTIONS = {"overview", "sales", "clients", "reports", "marketing", "products", "blog"}
SUCCESSFUL_ORDER_STATUSES = (Order.Status.PAID, Order.Status.SHIPPED, Order.Status.DELIVERED)


@staff_member_required
@ensure_csrf_cookie
def admin_dashboard(request):
    section = request.GET.get("section", "overview")
    if section not in ADMIN_PANEL_SECTIONS:
        section = "overview"

    successful_orders_qs = Order.objects.filter(status__in=SUCCESSFUL_ORDER_STATUSES).select_related("user").prefetch_related("items")
    successful_order_count = successful_orders_qs.count()
    total_revenue = successful_orders_qs.aggregate(total=Sum("total"))["total"] or Decimal("0")
    average_ticket = total_revenue / successful_order_count if successful_order_count else Decimal("0")
    successful_orders = list(successful_orders_qs[:100])
    pending_orders = Order.objects.filter(status=Order.Status.PENDING)
    pending_revenue = pending_orders.aggregate(total=Sum("total"))["total"] or Decimal("0")
    configured_financials = Q(purchase_value__isnull=False, sale_value__isnull=False)
    financial_totals = successful_orders_qs.aggregate(
        purchase=Sum("purchase_value", filter=configured_financials),
        sale=Sum("sale_value", filter=configured_financials),
    )
    gross_profit_total = (financial_totals["sale"] or Decimal("0")) - (financial_totals["purchase"] or Decimal("0"))

    item_revenue = ExpressionWrapper(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=14, decimal_places=2))
    sold_products = (
        OrderItem.objects.filter(order__status__in=SUCCESSFUL_ORDER_STATUSES)
        .values("product_name", "product_image")
        .annotate(units_sold=Sum("quantity"), revenue=Sum(item_revenue))
        .order_by("-units_sold", "product_name")
    )
    monthly_report = (
        Order.objects.filter(status__in=SUCCESSFUL_ORDER_STATUSES)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            order_count=Count("id"),
            revenue=Sum("total"),
            purchase_total=Sum("purchase_value", filter=configured_financials),
            sale_total=Sum("sale_value", filter=configured_financials),
            gross_profit=ExpressionWrapper(
                Sum("sale_value", filter=configured_financials) - Sum("purchase_value", filter=configured_financials),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
        )
        .order_by("-month")[:12]
    )

    User = get_user_model()
    client_search = request.GET.get("q", "").strip()
    clients = (
        User.objects.filter(is_staff=False)
        .select_related("customer_profile")
        .prefetch_related("addresses")
        .annotate(
            successful_order_count=Count("orders", filter=Q(orders__status__in=SUCCESSFUL_ORDER_STATUSES), distinct=True),
            total_spent=Sum("orders__total", filter=Q(orders__status__in=SUCCESSFUL_ORDER_STATUSES)),
        )
        .order_by("-date_joined")
    )
    if client_search:
        clients = clients.filter(
            Q(first_name__icontains=client_search)
            | Q(last_name__icontains=client_search)
            | Q(username__icontains=client_search)
            | Q(customer_profile__document_number__icontains=client_search)
        )
    top_favorites = Product.objects.filter(is_active=True).annotate(favorite_count=Count("favorited_by")).order_by("-favorite_count", "name")[:6]
    products = Product.objects.all().order_by("brand", "name")
    blog_posts = BlogPost.objects.select_related("category").all()
    active_banner_count = HomeBanner.objects.filter(is_active=True).count()
    active_popup_count = MarketingPopup.objects.filter(is_active=True).count()
    active_coupon_count = Coupon.objects.filter(is_active=True).count()
    pending_contact_count = ContactRequest.objects.filter(status=ContactRequest.Status.NEW).count()
    pending_blog_comments = BlogComment.objects.filter(is_approved=False).select_related("post")[:5]
    pending_reviews = ProductReview.objects.filter(is_approved=False).select_related("product")[:5]
    pending_blog_comment_count = BlogComment.objects.filter(is_approved=False).count()
    pending_review_count = ProductReview.objects.filter(is_approved=False).count()
    marketing_notification_count = pending_blog_comment_count + pending_review_count
    recent_contact_requests = ContactRequest.objects.all()[:5]

    return render(request, "store/admin-dashboard.html", {
        "section": section,
        "successful_orders": successful_orders,
        "successful_order_count": successful_order_count,
        "sold_products": sold_products,
        "clients": clients,
        "client_search": client_search,
        "monthly_report": monthly_report,
        "total_revenue": total_revenue,
        "average_ticket": average_ticket,
        "gross_profit_total": gross_profit_total,
        "pending_order_count": pending_orders.count(),
        "pending_revenue": pending_revenue,
        "client_count": clients.count(),
        "product_count": products.count(),
        "low_stock_count": products.filter(stock__lte=5).count(),
        "active_cart_count": Cart.objects.filter(status=Cart.Status.ACTIVE).count(),
        "favorite_count": Favorite.objects.count(),
        "published_post_count": blog_posts.filter(is_published=True).count(),
        "top_favorites": top_favorites,
        "products": products,
        "blog_posts": blog_posts,
        "blog_categories": BlogCategory.objects.all(),
        "active_banner_count": active_banner_count,
        "active_popup_count": active_popup_count,
        "active_coupon_count": active_coupon_count,
        "pending_contact_count": pending_contact_count,
        "pending_blog_comment_count": pending_blog_comment_count,
        "pending_review_count": pending_review_count,
        "marketing_notification_count": marketing_notification_count,
        "pending_blog_comments": pending_blog_comments,
        "pending_reviews": pending_reviews,
        "recent_contact_requests": recent_contact_requests,
    })

@login_required
def account(request):
    if request.user.is_staff:
        return redirect("admin_dashboard")
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


COUPON_SESSION_KEY = "cart_coupon_code"
SHIPPING_QUOTE_SESSION_KEY = "cart_shipping_quote"


def _coupon_state(request, subtotal):
    code = request.session.get(COUPON_SESSION_KEY, "")
    if not code:
        return None, Decimal("0")
    try:
        return coupon_totals(code, subtotal, user=request.user)
    except CouponError:
        request.session.pop(COUPON_SESSION_KEY, None)
        return None, Decimal("0")


def _shipping_state(request, subtotal):
    quote = request.session.get(SHIPPING_QUOTE_SESSION_KEY)
    quoted_cost = quote.get("cost") if quote else None
    return quote, shipping_cost_for(subtotal, quoted_cost=quoted_cost)


@ensure_csrf_cookie
def cart_view(request):
    cart = get_cart(request)
    coupon, discount = _coupon_state(request, cart.subtotal)
    shipping_quote, shipping = _shipping_state(request, cart.subtotal)
    total = max(Decimal("0"), cart.subtotal - discount) + shipping
    return render(request, "store/shop-cart.html", {
        "cart": cart,
        "coupon": coupon,
        "discount": discount,
        "discounted_subtotal": cart.subtotal - discount,
        "shipping_quote": shipping_quote,
        "shipping_cost": shipping,
        "total": total,
        "departments": DEPARTMENTS,
        "destinations": DESTINATIONS,
        "estimated_weight": min(30, max(1, cart.item_count)),
    })


@require_POST
def shipping_quote(request):
    try:
        quote = calculate_shipping(
            department=request.POST.get("department"),
            city=request.POST.get("city"),
            weight_kg=request.POST.get("weight_kg"),
            postal_code=request.POST.get("postal_code"),
            method=request.POST.get("delivery_method", "courier"),
        )
    except ValueError as exc:
        request.session.pop(SHIPPING_QUOTE_SESSION_KEY, None)
        messages.error(request, str(exc))
    else:
        request.session[SHIPPING_QUOTE_SESSION_KEY] = quote.session_payload()
        messages.success(request, f"Envío calculado desde Neiva: {quote.cost:,.0f} COP.")
    return redirect("/shop-cart.html#shipping-calculator")


@require_POST
def coupon_apply(request):
    cart = get_cart(request)
    try:
        coupon, discount = coupon_totals(request.POST.get("code"), cart.subtotal, user=request.user)
    except CouponError as exc:
        request.session.pop(COUPON_SESSION_KEY, None)
        messages.error(request, str(exc))
    else:
        request.session[COUPON_SESSION_KEY] = coupon.code
        messages.success(request, f"Cupon {coupon.code} aplicado. Ahorras ${discount:,.0f} COP.")
    return redirect("cart")


@require_POST
def coupon_remove(request):
    request.session.pop(COUPON_SESSION_KEY, None)
    messages.info(request, "El cupon fue retirado del carrito.")
    return redirect("cart")


@login_required
@ensure_csrf_cookie
def checkout(request):
    cart = get_cart(request)
    items = cart.items.select_related("product")
    addresses = request.user.addresses.all()
    subtotal = cart.subtotal
    coupon, discount = _coupon_state(request, subtotal)
    shipping_quote, shipping = _shipping_state(request, subtotal)

    if request.method == "POST":
        if not items:
            messages.error(request, "Tu carrito está vacío.")
            return redirect("cart")
        form = CheckoutForm(request.POST, user=request.user)
        if form.is_valid():
            delivery_method = form.cleaned_data["delivery_method"]
            if delivery_method == "pickup":
                profile = getattr(request.user, "customer_profile", None)
                address = SimpleNamespace(
                    recipient_name=request.user.get_full_name() or request.user.username,
                    phone=getattr(profile, "phone", "") or "Por confirmar",
                    address_line_1="Recogida en tienda",
                    address_line_2="",
                    department="Huila",
                    city="Neiva",
                    postal_code="",
                )
                order_shipping = Decimal("0")
                notes = "Recoger en Neiva, Huila."
                if form.cleaned_data["notes"]:
                    notes += f" {form.cleaned_data['notes']}"
            else:
                address = form.cleaned_data["address"]
                order_shipping = shipping
                notes = form.cleaned_data["notes"]
            try:
                order = create_order_from_cart(
                    user=request.user,
                    cart=cart,
                    address=address,
                    payment_method=form.cleaned_data["payment_method"],
                    notes=notes,
                    coupon_code=coupon.code if coupon else "",
                    shipping_cost=order_shipping,
                )
            except CheckoutError as exc:
                messages.error(request, str(exc))
                return redirect("checkout")
            request.session.pop(COUPON_SESSION_KEY, None)
            request.session.pop(SHIPPING_QUOTE_SESSION_KEY, None)
            return redirect("order_confirmation", number=order.number)
    else:
        initial_delivery = "pickup" if shipping_quote and shipping_quote.get("method") == "pickup" else "courier"
        form = CheckoutForm(user=request.user, initial={
            "payment_method": Order.PaymentMethod.BANK_TRANSFER,
            "delivery_method": initial_delivery,
        })

    return render(request, "store/shop-checkout.html", {
        "cart": cart,
        "items": items,
        "addresses": addresses,
        "default_address": addresses.filter(is_default=True).first() or addresses.first(),
        "form": form,
        "payment_methods": [
            choice
            for choice in Order.PaymentMethod.choices
            if choice[0] != Order.PaymentMethod.CASH_ON_DELIVERY
        ],
        "subtotal": subtotal,
        "shipping_cost": shipping,
        "shipping_quote": shipping_quote,
        "coupon": coupon,
        "discount": discount,
        "total": max(Decimal("0"), subtotal - discount) + shipping,
        "free_shipping_threshold": 400000,
    })


@login_required
def order_confirmation(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number, user=request.user)
    return render(request, "store/order-confirmation.html", {"order": order})


def _cart_payload(cart, request=None):
    items = [
        {
            "id": item.id,
            "product_id": item.product.slug,
            "name": item.product.name,
            "image": item.product.image,
            "price": int(item.product.price),
            "quantity": item.quantity,
            "size": item.size,
            "color": item.color,
            "subtotal": int(item.subtotal),
        }
        for item in cart.items.select_related("product")
    ]
    coupon = None
    discount = Decimal("0")
    shipping = shipping_cost_for(cart.subtotal)
    if request is not None:
        coupon, discount = _coupon_state(request, cart.subtotal)
        _, shipping = _shipping_state(request, cart.subtotal)
    discounted_subtotal = max(Decimal("0"), cart.subtotal - discount)
    return {
        "id": cart.id,
        "count": cart.item_count,
        "subtotal": int(cart.subtotal),
        "discount": int(discount),
        "shipping": int(shipping),
        "total_after_discount": int(discounted_subtotal),
        "total": int(discounted_subtotal + shipping),
        "coupon_code": coupon.code if coupon else "",
        "items": items,
    }


@require_http_methods(["GET"])
def cart_api(request):
    return JsonResponse(_cart_payload(get_cart(request), request))


@require_POST
def cart_add_api(request):
    try:
        data = json.loads(request.body or "{}")
        quantity = max(1, int(data.get("quantity", 1)))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"error": "Datos invalidos."}, status=400)
    product = get_object_or_404(Product, slug=data.get("product_id"), is_active=True)
    if product.stock < 1:
        return JsonResponse({"error": "Producto agotado."}, status=409)

    size = str(data.get("size", "")).strip()[:12]
    available_sizes = [str(value) for value in (product.sizes or [])]
    if available_sizes and not size:
        size = available_sizes[0]
    elif available_sizes and size not in available_sizes:
        return JsonResponse({"error": "Selecciona una talla disponible."}, status=400)

    color = str(data.get("color", "")).strip()[:60]
    available_colors = [
        str(value.get("name", "")).strip()
        for value in (product.colors or [])
        if isinstance(value, dict) and value.get("name")
    ]
    if available_colors and not color:
        color = available_colors[0]
    elif available_colors and color not in available_colors:
        return JsonResponse({"error": "Selecciona un color disponible."}, status=400)

    cart = get_cart(request)
    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        size=size,
        color=color,
        defaults={"quantity": min(quantity, product.stock)},
    )
    if not created:
        item.quantity = min(item.quantity + quantity, product.stock)
        item.save(update_fields=["quantity", "updated_at"])
    return JsonResponse(_cart_payload(cart, request), status=201)

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
    return JsonResponse(_cart_payload(cart, request))


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
    default_size = str(product.sizes[0]) if product.sizes else ""
    default_color = str(product.colors[0].get("name", "")) if product.colors and isinstance(product.colors[0], dict) else ""
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, size=default_size, color=default_color, defaults={"quantity": 1})
    if not created:
        item.quantity = min(item.quantity + 1, product.stock)
        item.save(update_fields=["quantity", "updated_at"])
    favorite.delete()
    return JsonResponse({"favorites": _favorite_payload(request.user), "cart": _cart_payload(cart, request)})

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
