import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .forms import ProductAdminForm
from .models import Address, BlogCategory, BlogComment, BlogPost, Cart, CartItem, ContactRequest, Coupon, CouponRedemption, CustomerProfile, Favorite, HomeBanner, MarketingPopup, NewsletterSubscription, Order, OrderItem, Product, ProductReview
from .shipping import DEPARTMENTS, calculate_shipping


User = get_user_model()


class StoreFlowTests(TestCase):
    def setUp(self):
        self.product = Product.objects.first()

    def test_catalog_seeded(self):
        self.assertEqual(Product.objects.count(), 16)

    def test_public_routes_render(self):
        routes = [
            "/", "/index.html", "/about-us.html", "/contact.html", "/blog.html", "/blog-details.html",
            "/shop.html", f"/single-product.html?producto={self.product.slug}",
            "/account-login.html", "/account-register.html", "/shop-cart.html",
        ]
        for url in routes:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get("/account.html").status_code, 302)
        self.assertRedirects(self.client.get("/shop-wishlist.html"), "/account-login.html?next=/shop-wishlist.html")
        self.assertRedirects(self.client.get("/shop-checkout.html"), "/account-login.html?next=/shop-checkout.html")
        self.assertEqual(self.client.get("/page-not-found.html").status_code, 404)

    def test_newsletter_subscription_is_persisted_without_duplicates(self):
        response = self.client.post(
            "/newsletter/subscribe/",
            data=json.dumps({"email": "sneakerhead@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["created"])
        self.assertTrue(NewsletterSubscription.objects.filter(email="sneakerhead@example.com", is_active=True).exists())

        duplicate = self.client.post(
            "/newsletter/subscribe/",
            data=json.dumps({"email": "SNEAKERHEAD@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertFalse(duplicate.json()["created"])
        self.assertEqual(NewsletterSubscription.objects.count(), 1)

        invalid = self.client.post(
            "/newsletter/subscribe/",
            data=json.dumps({"email": "correo-invalido"}),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)
    def test_individual_catalog_sections_are_blank_and_use_their_banners(self):
        sections = (
            ("hombre", "Hombre", "SUUGUg7RXYY"),
            ("mujer", "Mujer", "7WRaJmvTJLQ"),
            ("clasicas", "Clasicas", "RVlCGo-KHeA"),
            ("nike", "Nike", "GXNOb23Jon8"),
        )
        for slug, title, image in sections:
            with self.subTest(section=slug):
                response = self.client.get(f"/secciones/{slug}/")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, title)
                self.assertContains(response, image)
                self.assertContains(response, "Aun no hemos agregado productos")
                self.assertContains(response, "unsplash.com/photos/")
                self.assertNotContains(response, self.product.name)

    def test_blog_uses_published_articles_and_slug_detail_url(self):
        post = BlogPost.objects.get(slug="siluetas-basket-urbanas")
        listing = self.client.get("/blog.html")
        self.assertContains(listing, post.title)
        self.assertContains(listing, f"/blog/{post.slug}/")
        detail = self.client.get(f"/blog/{post.slug}/")
        self.assertContains(detail, post.summary)
        self.assertContains(detail, "Categorías")

    def test_unified_search_matches_product_and_blog_tags_without_accents(self):
        self.product.tags = ["Edición limitada", "Colección urbana"]
        self.product.save(update_fields=["tags"])
        product_response = self.client.get("/buscar/?q=edicion+limitada")
        self.assertEqual(product_response.status_code, 200)
        self.assertContains(product_response, self.product.name)
        self.assertContains(product_response, "Edición limitada")

        category = BlogCategory.objects.create(name="Guías expertas", slug="guias-expertas")
        post = BlogPost.objects.create(
            category=category,
            title="Cómo limpiar tus sneakers blancos",
            slug="limpiar-sneakers-blancos-test",
            summary="Una guía clara para conservar tus tenis.",
            content="Pasos de limpieza para materiales delicados.",
            image="assets/img/blog/juaco-blog-cover-02.png",
            image_alt="Sneakers blancos limpios",
            tags=["Cuidado premium", "Limpieza profunda"],
            published_at="2026-07-12T12:00:00Z",
        )
        blog_response = self.client.get("/buscar/?q=cuidado+premium")
        self.assertEqual(blog_response.status_code, 200)
        self.assertContains(blog_response, post.title)
        self.assertContains(blog_response, "Cuidado premium")

    def test_registration_redirects_to_account(self):
        response = self.client.post(
            "/account-register.html",
            {
                "first_name": "Maria Jose",
                "last_name": "Perez Gomez",
                "username": "cliente",
                "email": "cliente@example.com",
                "password1": "ClaveSegura123!",
                "password2": "ClaveSegura123!",
            },
        )
        self.assertRedirects(response, "/account.html")
        user = User.objects.get(username="cliente")
        self.assertEqual(user.first_name, "Maria Jose")
        self.assertEqual(user.last_name, "Perez Gomez")
        account = self.client.get("/account.html?tab=account-info")
        self.assertContains(account, "Maria Jose")
        self.assertContains(account, "Perez Gomez")

    def test_registration_requires_first_and_last_name(self):
        response = self.client.post(
            "/account-register.html",
            {"username": "sin_nombre", "email": "sin_nombre@example.com", "password1": "ClaveSegura123!", "password2": "ClaveSegura123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="sin_nombre").exists())
        self.assertContains(response, "Este campo es obligatorio.")

    def test_login_accepts_email(self):
        User.objects.create_user(username="cliente", email="cliente@example.com", password="ClaveSegura123!")
        response = self.client.post("/account-login.html", {"username": "cliente@example.com", "password": "ClaveSegura123!"})
        self.assertRedirects(response, "/account.html")
        account = self.client.get("/account.html")
        self.assertContains(account, "Bienvenido, cliente")
        self.assertContains(account, "assets/img/shop/bannerlogin.png")

    def test_login_returns_to_favorites_and_rejects_external_redirects(self):
        User.objects.create_user(username="retorno", password="ClaveSegura123!")
        response = self.client.post(
            "/account-login.html",
            {"username": "retorno", "password": "ClaveSegura123!", "next": "/shop-wishlist.html"},
        )
        self.assertRedirects(response, "/shop-wishlist.html")
        self.client.logout()
        unsafe = self.client.post(
            "/account-login.html",
            {"username": "retorno", "password": "ClaveSegura123!", "next": "https://evil.example/"},
        )
        self.assertRedirects(unsafe, "/account.html")
    def test_anonymous_cart_persists_in_database(self):
        response = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 2, "size": "40"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual(CartItem.objects.get().quantity, 2)
        self.assertIsNone(CartItem.objects.get().cart.user)

    def test_cart_badge_uses_real_item_quantity(self):
        self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 2, "size": "40"}),
            content_type="application/json",
        )
        response = self.client.get("/")
        self.assertContains(response, '<sup class="shop-count" aria-label="2 artículos en el carrito">2</sup>', html=True)
        self.assertEqual(self.client.get("/api/cart/").json()["count"], 2)

    def test_guest_cart_merges_after_login(self):
        self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 1}),
            content_type="application/json",
        )
        user = User.objects.create_user(username="cliente", email="cliente@example.com", password="ClaveSegura123!")
        self.client.post("/account-login.html", {"username": "cliente", "password": "ClaveSegura123!"})
        cart = Cart.objects.get(user=user, status=Cart.Status.ACTIVE)
        self.assertEqual(cart.item_count, 1)
        self.assertFalse(Cart.objects.filter(user__isnull=True, status=Cart.Status.ACTIVE).exists())

    def test_favorites_require_authentication(self):
        response = self.client.post(
            "/api/favorites/",
            data=json.dumps({"product_id": self.product.slug}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_user_can_add_remove_and_view_favorites(self):
        user = User.objects.create_user(username="favorito", password="ClaveSegura123!")
        self.client.force_login(user)
        add = self.client.post(
            "/api/favorites/",
            data=json.dumps({"product_id": self.product.slug}),
            content_type="application/json",
        )
        self.assertEqual(add.status_code, 201)
        self.assertEqual(add.json()["count"], 1)
        favorite = Favorite.objects.get(user=user, product=self.product)
        page = self.client.get("/shop-wishlist.html")
        self.assertContains(page, "Favoritos")
        self.assertContains(page, self.product.name)
        delete = self.client.delete(f"/api/favorites/{favorite.id}/")
        self.assertEqual(delete.status_code, 200)
        self.assertEqual(delete.json()["count"], 0)

    def test_move_favorite_to_cart(self):
        user = User.objects.create_user(username="carrito-favorito", password="ClaveSegura123!")
        favorite = Favorite.objects.create(user=user, product=self.product)
        self.client.force_login(user)
        response = self.client.post(f"/api/favorites/{favorite.id}/move-to-cart/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["cart"]["count"], 1)
        self.assertFalse(Favorite.objects.filter(pk=favorite.pk).exists())
        self.assertTrue(CartItem.objects.filter(cart__user=user, product=self.product).exists())
    def test_checkout_creates_order_and_clears_cart(self):
        user = User.objects.create_user(username="comprador", email="comprador@example.com", password="ClaveSegura123!")
        address = Address.objects.create(
            user=user, first_name="Ana", last_name="Ruiz", address_line_1="Cra 1 # 2-3",
            department="Antioquia", city="Medellín", phone="3001112233", is_default=True,
        )
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=2, size="40")
        stock_before = self.product.stock

        response = self.client.post("/shop-checkout.html", {
            "address": address.id,
            "payment_method": Order.PaymentMethod.BANK_TRANSFER,
            "notes": "Sin timbre",
            "accept_terms": "on",
        })

        order = Order.objects.get(user=user)
        self.assertRedirects(response, f"/order-confirmation/{order.number}/")
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.item_count, 2)
        self.assertEqual(order.total, self.product.price * 2)
        self.assertEqual(order.recipient_name, "Ana Ruiz")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, stock_before - 2)
        cart.refresh_from_db()
        self.assertEqual(cart.status, Cart.Status.CONVERTED)
        self.assertEqual(cart.items.count(), 0)

    def test_coupon_applies_expires_and_redeems_during_checkout(self):
        user = User.objects.create_user(username="cupon-cliente", email="cupon@example.com", password="ClaveSegura123!")
        address = Address.objects.create(
            user=user, first_name="Lina", last_name="Rojas", address_line_1="Calle 10 # 4-20",
            department="Huila", city="Neiva", phone="3009998877", is_default=True,
        )
        coupon = Coupon.objects.create(
            code="juaco10", discount_type=Coupon.DiscountType.PERCENTAGE, value=10,
            minimum_purchase=1000, starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=1), usage_limit=2, once_per_user=True,
        )
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")

        coupon_form = self.client.get("/shop-cart.html")
        self.assertContains(coupon_form, 'action="/cart-coupon/apply/"', count=1)
        self.assertContains(coupon_form, 'id="couponCode"', count=1)

        apply_response = self.client.post("/cart-coupon/apply/", {"code": "juaco10"})
        self.assertRedirects(apply_response, "/shop-cart.html")
        expected_discount = coupon.discount_for(self.product.price)
        cart_payload = self.client.get("/api/cart/").json()
        self.assertEqual(cart_payload["coupon_code"], "JUACO10")
        self.assertEqual(cart_payload["discount"], int(expected_discount))
        self.assertEqual(cart_payload["total_after_discount"], int(self.product.price - expected_discount))
        self.assertContains(self.client.get("/shop-cart.html"), "JUACO10")
        checkout_page = self.client.get("/shop-checkout.html")
        self.assertContains(checkout_page, "Cupon JUACO10")
        self.assertContains(checkout_page, f"-${expected_discount:,.0f} COP".replace(",", "."))

        response = self.client.post("/shop-checkout.html", {
            "address": address.id, "payment_method": Order.PaymentMethod.BANK_TRANSFER,
            "notes": "Pedido con cupon", "accept_terms": "on",
        })
        order = Order.objects.get(user=user)
        self.assertRedirects(response, f"/order-confirmation/{order.number}/")
        self.assertEqual(order.coupon, coupon)
        self.assertEqual(order.coupon_code, "JUACO10")
        self.assertEqual(order.discount_amount, expected_discount)
        self.assertEqual(order.total, order.subtotal - expected_discount + order.shipping_cost)
        self.assertTrue(CouponRedemption.objects.filter(coupon=coupon, user=user, order=order).exists())
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 1)

        new_cart = Cart.objects.get(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=new_cart, product=self.product, quantity=1)
        reused = self.client.post("/cart-coupon/apply/", {"code": coupon.code}, follow=True)
        self.assertContains(reused, "Ya utilizaste este cupon anteriormente.")
        self.assertEqual(self.client.get("/api/cart/").json()["coupon_code"], "")

        expired = Coupon.objects.create(
            code="VENCIDO", discount_type=Coupon.DiscountType.FIXED, value=5000,
            starts_at=timezone.now() - timedelta(days=2), expires_at=timezone.now() - timedelta(days=1),
        )
        expired_response = self.client.post("/cart-coupon/apply/", {"code": expired.code}, follow=True)
        self.assertContains(expired_response, "El cupon ya expiro.")
    def test_checkout_pickup_in_neiva_does_not_require_address(self):
        user = User.objects.create_user(
            username="sin-direccion-pickup",
            first_name="Mario",
            last_name="López",
            password="ClaveSegura123!",
        )
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        page = self.client.get("/shop-checkout.html")
        self.assertContains(page, "Recoger en Neiva, Huila")
        self.assertContains(page, 'value="pickup"', html=False)

        response = self.client.post("/shop-checkout.html", {
            "delivery_method": "pickup",
            "payment_method": Order.PaymentMethod.BANK_TRANSFER,
            "accept_terms": "on",
        })
        order = Order.objects.get(user=user)
        self.assertRedirects(response, f"/order-confirmation/{order.number}/")
        self.assertEqual(order.shipping_cost, 0)
        self.assertEqual(order.city, "Neiva")
        self.assertEqual(order.department, "Huila")
        self.assertEqual(order.address_line_1, "Recogida en tienda")
        self.assertIn("Recoger en Neiva, Huila", order.notes)

    def test_checkout_hides_cash_on_delivery_and_shows_neiva_pickup(self):
        user = User.objects.create_user(username="recogida", password="ClaveSegura123!")
        Address.objects.create(
            user=user, first_name="Sara", last_name="Díaz", address_line_1="Punto de recogida",
            department="Huila", city="Neiva", phone="3001234567", is_default=True,
        )
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        self.client.post("/shipping-quote/", {"delivery_method": "pickup"})

        response = self.client.get("/shop-checkout.html")
        self.assertNotContains(response, "Pago contra entrega")
        self.assertContains(response, "Transferencia bancaria")
        self.assertContains(response, "Pago con Bold")
        self.assertContains(response, "Recogida en Neiva, Huila")

        invalid = self.client.post("/shop-checkout.html", {
            "address": user.addresses.first().id,
            "payment_method": Order.PaymentMethod.CASH_ON_DELIVERY,
            "accept_terms": "on",
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(Order.objects.filter(user=user).exists())

    def test_checkout_requires_accepting_terms(self):
        user = User.objects.create_user(username="sinterminos", password="ClaveSegura123!")
        address = Address.objects.create(
            user=user, first_name="Leo", last_name="Paz", address_line_1="Calle 5",
            department="Valle", city="Cali", phone="3002223344", is_default=True,
        )
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        response = self.client.post("/shop-checkout.html", {
            "address": address.id,
            "payment_method": Order.PaymentMethod.BANK_TRANSFER,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertContains(response, "términos y condiciones")

    def test_account_orders_show_product_preview_and_link(self):
        user = User.objects.create_user(username="historial", password="ClaveSegura123!")
        order = Order.objects.create(
            user=user, number="JS-PREVIEW-0001", recipient_name="Cliente Prueba", phone="300",
            address_line_1="Calle 1", department="Antioquia", city="Medellín",
            subtotal=self.product.price, total=self.product.price,
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            product_image=self.product.image, unit_price=self.product.price, quantity=1,
        )
        self.client.force_login(user)
        response = self.client.get("/account.html?tab=orders")
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.product.image)
        self.assertContains(response, f"single-product.html?producto={self.product.slug}")
    def test_new_account_dashboard_has_clickable_stats_checklist_and_recommendations(self):
        user = User.objects.create_user(username="nuevo", password="ClaveSegura123!")
        self.client.force_login(user)
        response = self.client.get("/account.html")
        self.assertContains(response, 'href="?tab=orders"', html=False)
        self.assertContains(response, 'href="?tab=cart"', html=False)
        self.assertContains(response, 'href="?tab=addresses"', html=False)
        self.assertContains(response, "Completa tu cuenta")
        self.assertContains(response, "Completa tu perfil")
        self.assertContains(response, "Agrega una direccion")
        self.assertContains(response, "Explora la tienda")
        self.assertContains(response, "Productos recomendados")
        self.assertContains(response, self.product.name)
    def test_order_detail_scoped_to_owner(self):
        owner = User.objects.create_user(username="dueno", password="ClaveSegura123!")
        other = User.objects.create_user(username="ajeno", password="ClaveSegura123!")
        order = Order.objects.create(
            user=owner, number="JS-TEST-0001", recipient_name="Dueño Uno", phone="300",
            address_line_1="x", department="d", city="c", subtotal=1000, total=1000,
        )
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/orders/{order.number}/").status_code, 404)
        self.client.force_login(owner)
        self.assertEqual(self.client.get(f"/orders/{order.number}/").status_code, 200)

    def test_admin_dashboard_requires_staff_and_exposes_management_sections(self):
        regular_user = User.objects.create_user(username="cliente-panel", first_name="Emanuel", last_name="Cantillo", password="ClaveSegura123!")
        CustomerProfile.objects.create(user=regular_user, document_number="1075000000", phone="3001234567")
        Address.objects.create(
            user=regular_user, label="Casa", first_name="Cliente", last_name="Panel",
            address_line_1="Calle 8 # 10-20", department="Huila", city="Neiva",
            phone="3001234567", is_default=True,
        )
        self.client.force_login(regular_user)
        response = self.client.get("/panel-admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

        sale = Order.objects.create(
            user=regular_user, number="JS-ADMIN-0001", status=Order.Status.PAID,
            recipient_name="Cliente Panel", phone="3001234567", address_line_1="Calle 1",
            department="Huila", city="Neiva", subtotal=self.product.price * 2, total=self.product.price * 2,
            purchase_value=self.product.price, sale_value=self.product.price * 2,
        )
        OrderItem.objects.create(
            order=sale, product=self.product, product_name=self.product.name,
            product_image=self.product.image, unit_price=self.product.price, quantity=2,
        )
        staff_user = User.objects.create_superuser(username="admin-panel", email="admin@example.com", password="ClaveSegura123!")
        self.client.force_login(staff_user)
        response = self.client.get("/panel-admin/")
        self.assertEqual(response.status_code, 200)
        for label in ("Ventas exitosas", "Clientes", "Reportes financieros", "Marketing", "Edicion de productos", "Blog"):
            self.assertContains(response, label)
        self.assertContains(response, '/admin/store/product/add/')
        self.assertContains(response, '/admin/store/blogpost/add/')
        self.assertContains(response, 'href="panel-admin/?section=sales#admin-panel-content"')
        self.assertContains(response, 'id="admin-panel-content"')
        self.assertContains(response, 'data-admin-panel-navigation')

        sales_response = self.client.get("/panel-admin/?section=sales")
        self.assertEqual(sales_response.status_code, 200)
        self.assertContains(sales_response, "JS-ADMIN-0001")
        self.assertContains(sales_response, self.product.name)
        self.assertContains(sales_response, self.product.image)

        reports_response = self.client.get("/panel-admin/?section=reports")
        self.assertEqual(reports_response.status_code, 200)
        self.assertContains(reports_response, "Utilidad bruta")
        self.assertContains(reports_response, "Valor de compra")
        self.assertContains(reports_response, "Valor de venta")
        self.assertEqual(reports_response.context["gross_profit_total"], self.product.price)
        monthly_row = list(reports_response.context["monthly_report"])[0]
        self.assertEqual(monthly_row["purchase_total"], self.product.price)
        self.assertEqual(monthly_row["sale_total"], self.product.price * 2)
        self.assertEqual(monthly_row["gross_profit"], self.product.price)

        clients_response = self.client.get("/panel-admin/?section=clients")
        self.assertEqual(clients_response.status_code, 200)
        self.assertContains(clients_response, "cliente-panel")
        self.assertContains(clients_response, "1075000000")
        self.assertContains(clients_response, "Calle 8 # 10-20")
        self.assertContains(clients_response, "data-client-toggle=")
        self.assertContains(clients_response, "Nombre, apellido o cedula")
        for query in ("Emanuel", "Cantillo", "1075000000"):
            search_response = self.client.get("/panel-admin/", {"section": "clients", "q": query})
            self.assertEqual(search_response.status_code, 200)
            self.assertContains(search_response, "cliente-panel")
            self.assertEqual(search_response.context["client_count"], 1)
        empty_search = self.client.get("/panel-admin/", {"section": "clients", "q": "SinCoincidencias"})
        self.assertNotContains(empty_search, "cliente-panel")
        self.assertContains(empty_search, 'No se encontraron clientes para "SinCoincidencias".')
        client_record = clients_response.context["clients"].get(pk=regular_user.pk)
        self.assertEqual(client_record.successful_order_count, 1)
        self.assertEqual(client_record.total_spent, self.product.price * 2)
        self.assertRedirects(self.client.get("/account.html"), "/panel-admin/")
        self.assertRedirects(self.client.get("/account-login.html"), "/panel-admin/")

    def test_account_details_save_assistance_profile(self):
        user = User.objects.create_user(
            username="cliente-asistencia", email="anterior@example.com", password="ClaveSegura123!",
        )
        self.client.force_login(user)
        response = self.client.post("/account-details/", {
            "first_name": "Laura",
            "last_name": "Perez",
            "username": "cliente-asistencia",
            "email": "laura@example.com",
            "document_number": "1234567890",
            "phone": "3101234567",
        })
        self.assertRedirects(response, "/account.html?tab=account-info")
        profile = CustomerProfile.objects.get(user=user)
        self.assertEqual(profile.document_number, "1234567890")
        self.assertEqual(profile.phone, "3101234567")

    def test_marketing_crud_inbox_comments_reviews_and_dynamic_banner(self):
        banner = HomeBanner.objects.create(
            name="Campana video", title="Nueva coleccion", subtitle="Descubre lo nuevo",
            media_type=HomeBanner.MediaType.VIDEO, layout=HomeBanner.Layout.FLAT,
            media_url="assets/video/banner.mp4", button_label="Ver tienda", button_url="shop.html",
        )
        popup = MarketingPopup.objects.create(
            name="Popup lanzamiento", title="Oferta especial", message="Conoce nuestra nueva coleccion.",
            image_url="assets/img/shop/popup.webp", image_position=MarketingPopup.ImagePosition.RIGHT,
            button_label="Comprar ahora", button_url="shop.html?tipo=footwear", delay_seconds=1,
        )
        home_response = self.client.get("/")
        self.assertContains(home_response, banner.title)
        self.assertContains(home_response, banner.media_url)
        self.assertContains(home_response, "autoplay muted loop playsinline")
        self.assertContains(home_response, popup.title)
        self.assertContains(home_response, popup.message)
        self.assertContains(home_response, popup.image_url)
        self.assertContains(home_response, "marketing-popup--image-right")
        self.assertContains(home_response, popup.button_url)
        self.assertContains(home_response, "data-marketing-popup")

        contact_response = self.client.post("/contact.html", {
            "name": "Cliente Contacto", "email": "contacto@example.com", "phone": "3001234567",
            "subject": "Necesito asistencia", "message": "Quiero conocer el estado de mi solicitud.",
        })
        self.assertRedirects(contact_response, "/contact.html")
        self.assertTrue(ContactRequest.objects.filter(email="contacto@example.com", status=ContactRequest.Status.NEW).exists())

        post = BlogPost.objects.filter(is_published=True).first()
        comment_response = self.client.post(f"/blog/{post.slug}/", {
            "name": "Lector Blog", "email": "lector@example.com", "body": "Comentario pendiente de moderacion.",
        })
        self.assertEqual(comment_response.status_code, 302)
        comment = BlogComment.objects.get(email="lector@example.com")
        self.assertFalse(comment.is_approved)
        comment.is_approved = True
        comment.admin_response = "Gracias por participar en nuestro blog."
        comment.save(update_fields=("is_approved", "admin_response"))
        public_comment = self.client.get(f"/blog/{post.slug}/")
        self.assertContains(public_comment, "Comentario pendiente de moderacion.")
        self.assertContains(public_comment, "Gracias por participar en nuestro blog.")
        self.assertContains(public_comment, "Respuesta de Juaco Store")
        reply_response = self.client.post(f"/blog/{post.slug}/", {
            "name": "Otro Lector", "email": "respuesta@example.com", "body": "Esta es una respuesta al comentario.",
            "parent_id": comment.id,
        })
        self.assertEqual(reply_response.status_code, 302)
        reply = BlogComment.objects.get(email="respuesta@example.com")
        self.assertEqual(reply.parent, comment)
        reply.is_approved = True
        reply.save(update_fields=("is_approved",))
        self.assertContains(self.client.get(f"/blog/{post.slug}/"), "Esta es una respuesta al comentario.")

        empty_product_reviews = self.client.get(f"/single-product.html?producto={self.product.slug}")
        self.assertEqual(empty_product_reviews.context["review_count"], 0)
        self.assertContains(empty_product_reviews, "Aun no hay resenas aprobadas")
        self.assertContains(empty_product_reviews, "Inicia sesion para puntuar y recomendar")
        reviewer = User.objects.create_user(username="comprador-resena", first_name="Comprador", email="comprador@example.com", password="ClaveSegura123!")
        self.client.force_login(reviewer)

        review_response = self.client.post(f"/single-product.html?producto={self.product.slug}", {
            "name": "Comprador", "email": "comprador@example.com", "rating": 5, "recommends": "on",
            "title": "Excelente producto", "body": "La calidad y el servicio fueron excelentes.",
        })
        self.assertEqual(review_response.status_code, 302)
        review = ProductReview.objects.get(email="comprador@example.com")
        self.assertEqual(review.user, reviewer)
        self.assertTrue(review.recommends)
        self.assertFalse(review.is_approved)
        review.is_approved = True
        review.admin_response = "Nos alegra que disfrutaras tu compra."
        review.save(update_fields=("is_approved", "admin_response"))
        public_review = self.client.get(f"/single-product.html?producto={self.product.slug}")
        self.assertEqual(public_review.context["review_count"], 1)
        self.assertEqual(public_review.context["recommendation_percent"], 100)
        self.assertContains(public_review, "Excelente producto")
        self.assertContains(public_review, "Recomienda este producto")
        self.assertContains(public_review, "Nos alegra que disfrutaras tu compra.")

        pending_comment = BlogComment.objects.create(
            post=post, name="Comentario Nuevo", email="nuevo-blog@example.com", body="Necesito una respuesta.",
        )
        pending_review = ProductReview.objects.create(
            product=self.product, name="Resena Nueva", email="nueva-resena@example.com", rating=4,
            title="Pregunta sobre talla", body="Quiero confirmar la talla.",
        )

        self.product.audience = Product.Audience.MEN
        self.product.product_type = Product.ProductType.ACCESSORY
        self.product.save(update_fields=("audience", "product_type"))
        filtered_shop = self.client.get("/shop.html", {"genero": "men", "tipo": "accessory"})
        self.assertIn(self.product, filtered_shop.context["products"])

        staff = User.objects.create_superuser(username="marketing-admin", email="marketing@example.com", password="ClaveSegura123!")
        self.client.force_login(staff)
        marketing_response = self.client.get("/panel-admin/?section=marketing")
        self.assertEqual(marketing_response.status_code, 200)
        self.assertEqual(marketing_response.context["marketing_notification_count"], 2)
        self.assertContains(marketing_response, "admin-menu-badge")
        self.assertContains(marketing_response, "2 notificaciones pendientes")
        self.assertContains(marketing_response, pending_comment.name)
        self.assertContains(marketing_response, pending_review.name)
        self.assertContains(marketing_response, "Responder")
        for label in ("Banner del home", "Popups promocionales", "Contacto y atencion", "Blog y comunidad", "Cupones de descuento", "Resenas de productos"):
            self.assertContains(marketing_response, label)
        self.assertEqual(marketing_response.context["active_popup_count"], 1)
        self.assertContains(marketing_response, "/admin/store/homebanner/")
        self.assertContains(marketing_response, "/admin/store/marketingpopup/")
        self.assertContains(marketing_response, "/admin/store/coupon/")
        self.assertContains(marketing_response, "/admin/store/couponredemption/")
        products_response = self.client.get("/panel-admin/?section=products")
        self.assertContains(products_response, "Tienda y productos")
        self.assertContains(products_response, "audience__exact=men")
        self.assertContains(marketing_response, "/admin/store/contactrequest/")
        self.assertContains(marketing_response, "/admin/store/blogcomment/")
        self.assertContains(marketing_response, "/admin/store/productreview/")
        self.assertContains(self.client.get(f"/admin/store/blogcomment/{pending_comment.id}/change/"), "admin_response")
        self.assertContains(self.client.get(f"/admin/store/productreview/{pending_review.id}/change/"), "admin_response")

    def test_cart_quantity_update_and_delete(self):
        add = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 1}),
            content_type="application/json",
        )
        item_id = add.json()["items"][0]["id"]
        update = self.client.patch(
            f"/api/cart/items/{item_id}/",
            data=json.dumps({"quantity": 3}),
            content_type="application/json",
        )
        self.assertEqual(update.json()["count"], 3)
        delete = self.client.delete(f"/api/cart/items/{item_id}/")
        self.assertEqual(delete.json()["count"], 0)

    def test_product_crud_parses_and_renders_variants(self):
        form = ProductAdminForm(data={
            "slug": "producto-variantes",
            "sku": "TEST-CRUD-001",
            "brand": "Jordan",
            "name": "Producto con variantes",
            "audience": Product.Audience.UNISEX,
            "product_type": Product.ProductType.FOOTWEAR,
            "collection": Product.Collection.CLASSICS,
            "description": "Producto creado desde el CRUD.",
            "additional_information": "Capellada premium y suela de caucho.",
            "detailed_description": "Descripcion completa controlada por el administrador.",
            "price": "250000",
            "compare_at_price": "280000",
            "image": "assets/img/shop/jordan423.png",
            "image_alt": "Vista principal del producto de prueba",
            "gallery": "assets/img/shop/jordan623.png | Vista lateral\nassets/img/shop/jordan723.png | Vista posterior",
            "tags": "Retro, cuero, Retro",
            "sizes": "38, 39, 40, 40",
            "colors": "Gris oscuro | #505050\nAzul | #586882",
            "weight_kg": "1.25",
            "stock": "10",
            "is_active": "on",
        })
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save()
        self.assertEqual(product.sizes, ["38", "39", "40"])
        self.assertEqual(product.colors, [
            {"name": "Gris oscuro", "hex": "#505050"},
            {"name": "Azul", "hex": "#586882"},
        ])
        self.assertEqual(product.gallery, [
            {"url": "assets/img/shop/jordan623.png", "alt": "Vista lateral"},
            {"url": "assets/img/shop/jordan723.png", "alt": "Vista posterior"},
        ])
        self.assertEqual(product.reference, "TEST-CRUD-001")
        self.assertTrue(product.has_discount)
        self.assertEqual(product.discount_percent, 11)

        response = self.client.get(f"/single-product.html?producto={product.slug}")
        self.assertContains(response, 'data-color="Gris oscuro"')
        self.assertEqual(product.collection, Product.Collection.CLASSICS)
        self.assertEqual(product.tags, ["Retro", "cuero"])
        self.assertContains(response, 'data-bg-color="#586882"')
        self.assertContains(response, 'data-size="38"')
        self.assertContains(response, 'data-size="40"')
        self.assertContains(response, product.description)
        self.assertContains(response, product.additional_information)
        self.assertContains(response, product.detailed_description)
        self.assertContains(response, product.sku)
        self.assertContains(response, "Vista lateral")
        self.assertContains(response, "Vista posterior")
        self.assertContains(response, "$280.000 COP")
        self.assertContains(response, "10 unidades")
        self.assertContains(response, "1,25 kg")

        collection_response = self.client.get("/shop.html", {"coleccion": Product.Collection.CLASSICS})
        self.assertEqual(collection_response.status_code, 200)
        self.assertIn(product, collection_response.context["products"])

    def test_product_admin_exposes_complete_detail_fields(self):
        staff = User.objects.create_superuser(
            username="catalog-admin",
            email="catalog@example.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(staff)
        response = self.client.get("/admin/store/product/add/")
        for field_name in (
            "sku", "description", "additional_information", "detailed_description",
            "price", "compare_at_price", "stock", "weight_kg", "image",
            "image_alt", "gallery", "sizes", "colors", "tags", "collection", "is_active",
        ):
            self.assertContains(response, f'id="id_{field_name}"', html=False)

    def test_cart_validates_and_keeps_color_and_size(self):
        self.product.sizes = ["38", "40"]
        self.product.colors = [{"name": "Negro", "hex": "#111111"}]
        self.product.save(update_fields=["sizes", "colors"])

        invalid = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "size": "99", "color": "Negro"}),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

        response = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "size": "40", "color": "Negro"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        item = CartItem.objects.get()
        self.assertEqual(item.size, "40")
        self.assertEqual(item.color, "Negro")
        self.assertEqual(response.json()["items"][0]["color"], "Negro")

    def test_shipping_rates_and_all_departments(self):
        self.assertEqual(len(DEPARTMENTS), 32)

        urban = calculate_shipping("Huila", "Neiva", "2")
        self.assertEqual(urban.zone, "urban")
        self.assertEqual(urban.cost, 6950)

        national = calculate_shipping("Antioquia", "Medellín", "2")
        self.assertEqual(national.zone, "national")
        self.assertEqual(national.cost, 24950)

        special = calculate_shipping("Amazonas", "Leticia", "2")
        self.assertEqual(special.zone, "special")
        self.assertEqual(special.cost, 24950)
        self.assertIn("10 días", special.delivery_days)

        pickup = calculate_shipping("", "", "", method="pickup")
        self.assertEqual(pickup.cost, 0)
        self.assertEqual(pickup.city, "Neiva")

    def test_shipping_quote_updates_cart_totals(self):
        add = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 1}),
            content_type="application/json",
        )
        self.assertEqual(add.status_code, 201)

        response = self.client.post(
            "/shipping-quote/",
            {
                "delivery_method": "courier",
                "department": "Antioquia",
                "city": "Medellín",
                "postal_code": "050001",
                "weight_kg": "1.4",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[0][0], "/shop-cart.html#shipping-calculator")
        self.assertEqual(response.context["shipping_quote"]["department"], "Antioquia")
        self.assertEqual(response.context["shipping_cost"], 24950)
        self.assertContains(response, "Trayecto nacional")
        self.assertContains(response, "Tarifas oficiales expedidas el 1 de junio de 2026")

        payload = self.client.get("/api/cart/").json()
        self.assertEqual(payload["shipping"], 24950)
        self.assertEqual(payload["total"], payload["total_after_discount"] + 24950)

    def test_shipping_quote_validates_weight_limit(self):
        response = self.client.post(
            "/shipping-quote/",
            {
                "delivery_method": "courier",
                "department": "Valle del Cauca",
                "city": "Cali",
                "weight_kg": "31",
            },
            follow=True,
        )
        self.assertContains(response, "El peso debe estar entre 0,1 y 30 kg.")
        self.assertNotIn("cart_shipping_quote", self.client.session)
