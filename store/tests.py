import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Address, BlogCategory, BlogPost, Cart, CartItem, Favorite, Order, OrderItem, Product


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
            {"username": "cliente", "email": "cliente@example.com", "password1": "ClaveSegura123!", "password2": "ClaveSegura123!"},
        )
        self.assertRedirects(response, "/account.html")
        self.assertTrue(User.objects.filter(username="cliente").exists())

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
