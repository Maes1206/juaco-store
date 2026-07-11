import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Cart, CartItem, Product


User = get_user_model()


class StoreFlowTests(TestCase):
    def setUp(self):
        self.product = Product.objects.first()

    def test_catalog_seeded(self):
        self.assertEqual(Product.objects.count(), 16)

    def test_public_routes_render(self):
        routes = [
            "/", "/index.html", "/about-us.html", "/contact.html", "/blog.html", "/blog-details.html",
            "/shop.html", f"/single-product.html?producto={self.product.slug}", "/shop-wishlist.html",
            "/shop-checkout.html", "/account-login.html", "/account-register.html", "/shop-cart.html",
        ]
        for url in routes:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get("/account.html").status_code, 302)
        self.assertEqual(self.client.get("/page-not-found.html").status_code, 404)

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
