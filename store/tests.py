import base64
import hashlib
import hmac
import io
import json
import re
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from urllib.parse import urlsplit
from PIL import Image

from . import bold
from .emails import send_order_confirmation_email, send_order_status_email
from .forms import ProductAdminForm
from .image_optimization import TARGET_IMAGE_BYTES, optimize_uploaded_image
from .colors import color_hex_from_name, dominant_color_from_image, nearest_color_name, resolve_color_hex
from .models import MAX_VIDEO_UPLOAD_BYTES, Address, BlogCategory, BlogComment, BlogPost, Cart, CartItem, ContactRequest, Coupon, CouponRedemption, CustomerProfile, Favorite, HomeBanner, MarketingPopup, NewsletterSubscription, Order, OrderItem, OrderStatusHistory, Product, ProductImage, ProductReview, ProductVariant, StoreSection, validate_dispatch_receipt, validate_uploaded_media
from .receipts import receipt_verification_token
from .services import OrderTransitionError, apply_payment_status, transition_order
from .shipping import DEPARTMENTS, calculate_shipping
from .stockx import StockXReleaseDate, lookup_release_date


User = get_user_model()


class StoreFlowTests(TestCase):
    def setUp(self):
        self.product = Product.objects.first()

    def section_product_names(self, slug, **filters):
        """Nombres de una seccion recorriendo todas sus paginas."""
        names = []
        page_number = 1
        while True:
            response = self.client.get(f"/secciones/{slug}/", {**filters, "pagina": page_number})
            self.assertEqual(response.status_code, 200)
            page = response.context["page_obj"]
            names.extend(product.name for product in page.object_list)
            if not page.has_next():
                return names
            page_number += 1

    def test_catalog_seeded(self):
        self.assertEqual(Product.objects.count(), 16)

    def test_footer_uses_the_high_contrast_logo_for_dark_backgrounds(self):
        response = self.client.get("/")
        self.assertContains(response, "assets/img/shop/nexus-logo-horizontal-dark.png")
        self.assertContains(response, "assets/img/shop/nexus-logo-horizontal-dark@2x.png")

    def test_seeded_brand_sections_are_in_the_store_menu_and_receive_products(self):
        home = self.client.get("/")
        html = home.content.decode()
        desktop_menu_start = html.index('<ul class="submenu-nav">')
        desktop_menu_end = html.index("</ul>", desktop_menu_start)
        desktop_menu = html[desktop_menu_start:desktop_menu_end]

        expected_order = ("nike", "jordan", "adidas", "puma", "ofertas", "accesorios")
        positions = [desktop_menu.index(f"/secciones/{slug}/") for slug in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(desktop_menu.count("/secciones/nike/"), 1)

        for brand in ("Nike", "Jordan", "Adidas", "Puma"):
            with self.subTest(brand=brand):
                section = StoreSection.objects.get(
                    slug=brand.lower(),
                    section_type=StoreSection.SectionType.BRAND,
                    is_active=True,
                )
                brand_products = Product.objects.filter(brand=section)
                self.assertEqual(section.brand_products.count(), brand_products.count())
                response = self.client.get(f"/secciones/{section.slug}/")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, section.banner_image_url.split("?")[0])
                self.assertContains(response, brand_products.first().name)

    def test_travis_scott_featured_card_opens_its_own_detail_with_gallery(self):
        slug = "nike-sb-dunk-low-travis-scott"
        home = self.client.get("/")
        detail_url = f"single-product.html?producto={slug}"
        self.assertContains(home, detail_url, count=3)

        product = Product.objects.get(slug=slug)
        self.assertEqual(len(product.product_images), 4)

        detail = self.client.get(f"/{detail_url}")
        self.assertContains(detail, product.name)
        for image in product.product_images:
            self.assertContains(detail, image["url"])

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
    def test_standard_catalog_sections_list_products_from_admin_classification(self):
        self.product.audience = Product.Audience.MEN
        self.product.collection = Product.Collection.CLASSICS
        self.product.save(update_fields=("audience", "collection"))
        sections = (
            ("hombre", "Hombre", "SUUGUg7RXYY", True),
            ("mujer", "Mujer", "7WRaJmvTJLQ", False),
            ("clasicas", "Clasicas", "RVlCGo-KHeA", True),
        )
        for slug, title, image, should_show_product in sections:
            with self.subTest(section=slug):
                response = self.client.get(f"/secciones/{slug}/")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, title)
                self.assertContains(response, image)
                self.assertContains(response, "unsplash.com/photos/")
                self.assertNotContains(response, "Foto:")
                if should_show_product:
                    self.assertContains(response, self.product.name)
                else:
                    self.assertNotContains(response, self.product.name)

        self.product.audience = Product.Audience.UNISEX
        self.product.save(update_fields=("audience",))
        self.assertContains(self.client.get("/secciones/hombre/"), self.product.name)
        self.assertContains(self.client.get("/secciones/mujer/"), self.product.name)

    def test_offers_section_starts_empty_and_only_lists_tagged_products(self):
        empty_response = self.client.get("/secciones/ofertas/")
        self.assertEqual(empty_response.status_code, 200)
        self.assertContains(empty_response, "Ofertas")
        self.assertContains(empty_response, "DM-TpKGZV3U")
        self.assertContains(empty_response, "p5C9ZTeDzko")
        self.assertContains(empty_response, "Aún no hay productos en oferta")
        self.assertContains(empty_response, "Explorar toda la tienda")
        self.assertNotContains(empty_response, "Foto:")
        self.assertNotContains(empty_response, self.product.name)

        self.product.is_on_sale = True
        self.product.save(update_fields=("is_on_sale",))
        populated_response = self.client.get("/secciones/ofertas/")
        self.assertContains(populated_response, self.product.name)
        self.assertContains(populated_response, f"single-product.html?producto={self.product.slug}")

        self.product.is_active = False
        self.product.save(update_fields=("is_active",))
        inactive_response = self.client.get("/secciones/ofertas/")
        self.assertNotContains(inactive_response, self.product.name)

    def test_product_admin_exposes_offers_toggle(self):
        product_admin = admin.site._registry[Product]
        self.assertIn("is_on_sale", product_admin.list_display)
        self.assertIn("is_on_sale", product_admin.list_filter)

    def test_accessories_section_lists_products_classified_from_the_crud(self):
        empty_response = self.client.get("/secciones/accesorios/")
        self.assertEqual(empty_response.status_code, 200)
        self.assertContains(empty_response, "Accesorios")
        self.assertContains(empty_response, "cexQ3hh-XT0")
        self.assertContains(empty_response, "sxA_7Tcl1p0")
        self.assertContains(empty_response, "Aún no hemos agregado accesorios")
        self.assertContains(empty_response, "Explorar toda la tienda")
        self.assertNotContains(empty_response, "Foto:")
        self.assertNotContains(empty_response, self.product.name)

        self.product.product_type = Product.ProductType.ACCESSORY
        self.product.save(update_fields=("product_type",))
        populated_response = self.client.get("/secciones/accesorios/")
        self.assertContains(populated_response, self.product.name)
        self.assertContains(populated_response, "Accesorio")
        self.assertContains(populated_response, f"single-product.html?producto={self.product.slug}")

        self.product.stock = 0
        self.product.save(update_fields=("stock",))
        sold_out_response = self.client.get("/secciones/accesorios/")
        self.assertNotContains(sold_out_response, self.product.name)

    def test_dynamic_store_section_crud_navigation_and_product_assignment(self):
        section = StoreSection.objects.create(
            title="Marcas premium",
            slug="marcas-premium",
            description="Una selección especial de firmas y colaboraciones.",
            banner_image_url="https://images.example.com/marcas-banner.webp",
            banner_image_alt="Sneakers premium en exhibición",
            empty_image_url="https://images.example.com/marcas-empty.webp",
            empty_image_alt="Detalle editorial de una colección premium",
            empty_title="Próximamente en Marcas premium",
            empty_description="Estamos preparando esta selección.",
            position=3,
        )

        home = self.client.get("/")
        self.assertContains(home, section.title, count=2)
        self.assertContains(home, f"/secciones/{section.slug}/", count=2)

        empty_page = self.client.get(f"/secciones/{section.slug}/")
        self.assertEqual(empty_page.status_code, 200)
        self.assertContains(empty_page, section.description)
        self.assertContains(empty_page, section.banner_image_url)
        self.assertContains(empty_page, section.empty_image_url)
        self.assertContains(empty_page, section.empty_title)
        self.assertNotContains(empty_page, self.product.name)

        product_form = ProductAdminForm(instance=self.product)
        self.assertIn(section, product_form.fields["store_sections"].queryset)
        self.assertNotIn(section, product_form.fields["brand"].queryset)
        self.product.store_sections.add(section)
        populated_page = self.client.get(f"/secciones/{section.slug}/")
        self.assertContains(populated_page, self.product.name)
        self.assertContains(populated_page, f"single-product.html?producto={self.product.slug}")

        section.is_active = False
        section.save(update_fields=("is_active", "updated_at"))
        hidden_home = self.client.get("/")
        self.assertNotContains(hidden_home, f"/secciones/{section.slug}/")
        self.assertEqual(self.client.get(f"/secciones/{section.slug}/").status_code, 404)

    def test_dynamic_brand_is_available_to_products_and_uses_its_catalog_page(self):
        brand = StoreSection.objects.create(
            section_type=StoreSection.SectionType.BRAND,
            title="New Balance",
            slug="new-balance",
            description="Siluetas deportivas y urbanas de New Balance.",
            banner_image_url="https://images.example.com/new-balance-banner.webp",
            empty_image_url="https://images.example.com/new-balance-empty.webp",
            position=40,
        )

        product_form = ProductAdminForm(instance=self.product)
        self.assertIn(brand, product_form.fields["brand"].queryset)
        self.assertNotIn(brand, product_form.fields["store_sections"].queryset)

        self.product.brand = brand
        self.product.save()
        home = self.client.get("/")
        self.assertContains(home, "/secciones/new-balance/", count=2)
        page = self.client.get("/secciones/new-balance/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, self.product.name)
        self.assertContains(page, brand.banner_image_url)

        with self.assertRaises(ValidationError):
            brand.section_type = StoreSection.SectionType.CUSTOM
            brand.full_clean()

    def test_dynamic_store_section_validates_media_and_reserved_slugs(self):
        missing_media = StoreSection(
            title="Colecciones",
            slug="colecciones",
            description="Selecciones especiales.",
        )
        with self.assertRaises(ValidationError) as media_error:
            missing_media.full_clean()
        self.assertIn("banner_image_file", media_error.exception.message_dict)
        self.assertIn("empty_image_file", media_error.exception.message_dict)

        reserved = StoreSection(
            title="Otra sección hombre",
            slug="hombre",
            description="No debe reemplazar una sección principal.",
            banner_image_url="https://images.example.com/banner.webp",
            empty_image_url="https://images.example.com/empty.webp",
        )
        with self.assertRaises(ValidationError) as slug_error:
            reserved.full_clean()
        self.assertIn("slug", slug_error.exception.message_dict)

    def test_store_section_and_product_admin_forms_show_dynamic_options(self):
        section = StoreSection.objects.create(
            title="Ediciones especiales",
            slug="ediciones-especiales",
            description="Lanzamientos seleccionados.",
            banner_image_url="https://images.example.com/banner.webp",
            empty_image_url="https://images.example.com/empty.webp",
        )
        section_admin = admin.site._registry[StoreSection]
        product_admin = admin.site._registry[Product]
        self.assertIn("is_active", section_admin.list_editable)
        self.assertIn("store_sections", product_admin.filter_horizontal)
        self.assertIn("store_sections", product_admin.list_filter)

        staff = User.objects.create_superuser("secciones-admin", "secciones@example.com", "ClaveSegura123!")
        self.client.force_login(staff)
        section_form = self.client.get("/admin/store/storesection/add/")
        self.assertContains(section_form, "Banner de la sección")
        self.assertContains(section_form, "Estado vacío")
        product_form = self.client.get(f"/admin/store/product/{self.product.pk}/change/")
        self.assertContains(product_form, "Otras secciones donde se muestra")
        self.assertContains(product_form, section.title)
        dashboard = self.client.get("/panel-admin/?section=products")
        self.assertContains(dashboard, "Marcas y secciones dinámicas")
        self.assertContains(dashboard, section.title)

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
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        account = self.client.get("/account.html?tab=account-info")
        self.assertContains(account, "Maria Jose")
        self.assertContains(account, "Perez Gomez")

    def test_registration_sends_responsive_branded_welcome_email(self):
        response = self.client.post(
            "/account-register.html",
            {
                "first_name": "Valentina",
                "last_name": "Rojas",
                "username": "valentina",
                "email": "valentina@example.com",
                "password1": "ClaveSegura123!",
                "password2": "ClaveSegura123!",
            },
        )

        self.assertRedirects(response, "/account.html")
        self.assertEqual(len(mail.outbox), 1)
        welcome = mail.outbox[0]
        self.assertEqual(welcome.subject, "Bienvenido a Nexus Luxury Footwear")
        self.assertEqual(welcome.to, ["valentina@example.com"])
        self.assertIn("Hola Valentina", welcome.body)
        self.assertIn("http://testserver/shop.html", welcome.body)

        html_body = next(alternative.content for alternative in welcome.alternatives if alternative.mimetype == "text/html")
        self.assertIn("cid:nexus-welcome-logo", html_body)
        self.assertIn("font-family: Poppins, Arial, sans-serif", html_body)
        self.assertIn("background:#1f2226", html_body)
        self.assertIn("background:#c7a26a", html_body)
        self.assertIn('class="email-logo-cell"', html_body)
        self.assertIn("background:#17191c", html_body)
        inline_logos = [attachment for attachment in welcome.attachments if attachment.get_content_type() == "image/png"]
        self.assertEqual(len(inline_logos), 1)
        self.assertEqual(inline_logos[0]["Content-ID"], "<nexus-welcome-logo>")
        self.assertEqual(inline_logos[0].get_filename(), "nexus-logo-horizontal-dark.png")

    @override_settings(ADMIN_REGISTRATION_EMAILS={"emersonmanquillo@gmail.com"})
    def test_authorized_admin_email_requires_confirmation_before_promotion(self):
        response = self.client.post(
            "/account-register.html",
            {
                "first_name": "Emerson",
                "last_name": "Manquillo",
                "username": "emerson-admin",
                "email": "EmersonManquillo@gmail.com",
                "password1": "ClaveSegura123!",
                "password2": "ClaveSegura123!",
            },
        )

        self.assertRedirects(response, "/account-login.html")
        user = User.objects.get(username="emerson-admin")
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(len(mail.outbox), 1)
        confirmation = mail.outbox[0]
        self.assertEqual(confirmation.subject, "Bienvenidos admins | Nexus Luxury Footwear")
        self.assertEqual(confirmation.to, ["emersonmanquillo@gmail.com"])
        self.assertIn("Bienvenidos admins", confirmation.body)
        confirmation_url = re.search(r"http://testserver/confirmar-admin/[^\s]+", confirmation.body).group(0)

        confirmation_response = self.client.get(confirmation_url)

        self.assertRedirects(confirmation_response, "/panel-admin/")
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(self.client.get("/panel-admin/").status_code, 200)

    @override_settings(ADMIN_REGISTRATION_EMAILS={"emersonmanquillo@gmail.com"})
    @patch("store.views.send_admin_confirmation_email", side_effect=OSError("smtp no disponible"))
    def test_failed_admin_confirmation_email_does_not_leave_privileged_account(self, mocked_email):
        response = self.client.post(
            "/account-register.html",
            {
                "first_name": "Emerson",
                "last_name": "Manquillo",
                "username": "emerson-retry",
                "email": "emersonmanquillo@gmail.com",
                "password1": "ClaveSegura123!",
                "password2": "ClaveSegura123!",
            },
        )

        self.assertRedirects(response, "/account-register.html")
        self.assertFalse(User.objects.filter(username="emerson-retry").exists())
        mocked_email.assert_called_once()

    @patch("store.views.send_welcome_email", side_effect=OSError("smtp temporalmente no disponible"))
    def test_registration_succeeds_when_welcome_email_provider_is_unavailable(self, mocked_welcome):
        response = self.client.post(
            "/account-register.html",
            {
                "first_name": "Camila",
                "last_name": "Torres",
                "username": "camila",
                "email": "camila@example.com",
                "password1": "ClaveSegura123!",
                "password2": "ClaveSegura123!",
            },
        )

        self.assertRedirects(response, "/account.html")
        self.assertTrue(User.objects.filter(username="camila").exists())
        mocked_welcome.assert_called_once()

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

    def test_login_remember_me_controls_session_expiration(self):
        User.objects.create_user(username="recordado", email="recordado@example.com", password="ClaveSegura123!")

        browser_session = self.client.post(
            "/account-login.html",
            {"username": "recordado@example.com", "password": "ClaveSegura123!"},
        )
        self.assertRedirects(browser_session, "/account.html")
        self.assertTrue(self.client.session.get_expire_at_browser_close())

        self.client.logout()
        remembered_session = self.client.post(
            "/account-login.html",
            {"username": "recordado@example.com", "password": "ClaveSegura123!", "remember_me": "1"},
        )
        self.assertRedirects(remembered_session, "/account.html")
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertAlmostEqual(self.client.session.get_expiry_age(), settings.SESSION_COOKIE_AGE, delta=5)

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

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_changes_password_and_token_is_single_use(self):
        user = User.objects.create_user(
            username="recuperacion",
            email="recuperacion@example.com",
            password="ClaveAnterior123!",
        )

        requested = self.client.post("/recuperar-contrasena/", {"email": user.email})
        self.assertRedirects(requested, "/recuperar-contrasena/enviado/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(user.username, mail.outbox[0].subject)

        reset_url = re.search(r"https?://[^\s]+", mail.outbox[0].body).group(0)
        token_path = urlsplit(reset_url).path
        opened = self.client.get(token_path)
        self.assertEqual(opened.status_code, 302)
        set_password_path = opened.url

        form_page = self.client.get(set_password_path)
        self.assertContains(form_page, "Nueva contraseña")
        changed = self.client.post(
            set_password_path,
            {"new_password1": "ClaveNueva456!", "new_password2": "ClaveNueva456!"},
        )
        self.assertRedirects(changed, "/restablecer/completado/")

        user.refresh_from_db()
        self.assertFalse(user.check_password("ClaveAnterior123!"))
        self.assertTrue(user.check_password("ClaveNueva456!"))
        self.assertRedirects(
            self.client.post(
                "/account-login.html",
                {"username": user.email, "password": "ClaveNueva456!"},
            ),
            "/account.html",
        )

        self.client.logout()
        reused = self.client.get(token_path, follow=True)
        self.assertContains(reused, "ya no es válido")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_password_reset_does_not_reveal_unknown_emails(self):
        requested = self.client.post("/recuperar-contrasena/", {"email": "desconocido@example.com"})
        self.assertRedirects(requested, "/recuperar-contrasena/enviado/")
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_admin_password_reset_corrects_known_usco_domain_typo(self):
        admin_user = User.objects.create_superuser(
            username="admin-usco",
            email="u20242226877@usco.edu.co",
            password="ClaveAnterior123!",
        )

        requested = self.client.post(
            "/recuperar-contrasena/",
            {"email": "U20242226877@usco.edu.com"},
        )

        self.assertRedirects(requested, "/recuperar-contrasena/enviado/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [admin_user.email])
        reset_url = re.search(r"https?://[^\s]+", mail.outbox[0].body).group(0)
        opened = self.client.get(urlsplit(reset_url).path)
        self.assertEqual(opened.status_code, 302)
        form_page = self.client.get(opened.url)
        self.assertContains(form_page, 'name="new_password1"')
        self.assertContains(form_page, 'name="new_password2"')

    def test_login_corrects_known_usco_domain_typo(self):
        User.objects.create_superuser(
            username="admin-usco-login",
            email="u20242226877@usco.edu.co",
            password="ClaveSegura123!",
        )

        response = self.client.post(
            "/account-login.html",
            {"username": "U20242226877@usco.edu.com", "password": "ClaveSegura123!"},
        )

        self.assertRedirects(response, "/panel-admin/")
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

    def test_cart_page_renders_the_same_items_as_the_cart_api(self):
        add = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 2, "size": "40"}),
            content_type="application/json",
        )
        item = add.json()["items"][0]

        response = self.client.get("/shop-cart.html")
        self.assertContains(response, 'id="django-cart-items"')
        self.assertContains(response, f'data-cart-row="{item["id"]}"')
        self.assertContains(response, self.product.name)
        self.assertContains(response, "Talla: 40")
        self.assertContains(response, 'data-cart-comparison')
        self.assertContains(response, "Compara antes de elegir")
        self.assertContains(response, 'data-comparison-open')
        self.assertContains(response, 'data-comparison-modal hidden')
        self.assertNotContains(response, "Tu carrito está vacío")

    def test_cart_comparison_api_exposes_two_real_products_and_specs(self):
        second_product = Product.objects.exclude(pk=self.product.pk).first()
        ProductReview.objects.create(
            product=self.product,
            name="Cliente uno",
            email="cliente-uno@example.com",
            rating=5,
            recommends=True,
            title="Excelente",
            body="Muy cómodo.",
            is_approved=True,
        )
        ProductReview.objects.create(
            product=self.product,
            name="Cliente dos",
            email="cliente-dos@example.com",
            rating=4,
            recommends=False,
            title="Buen producto",
            body="Buen diseño.",
            is_approved=True,
        )
        ProductReview.objects.create(
            product=self.product,
            name="Pendiente",
            email="pendiente@example.com",
            rating=1,
            recommends=True,
            title="No publicada",
            body="Esta reseña no debe afectar las estadísticas.",
            is_approved=False,
        )
        for product in (self.product, second_product):
            add = self.client.post(
                "/api/cart/items/",
                data=json.dumps({"product_id": product.slug, "quantity": 1}),
                content_type="application/json",
            )
            self.assertEqual(add.status_code, 201)

        payload = self.client.get("/api/cart/").json()
        self.assertEqual(len({item["product_id"] for item in payload["items"]}), 2)
        for item in payload["items"]:
            for field in ("brand", "audience", "reference", "release_date", "release_year", "description", "stock", "weight_kg", "review_average", "review_count", "recommendation_percent", "sizes", "colors"):
                self.assertIn(field, item)

        reviewed = next(item for item in payload["items"] if item["product_id"] == self.product.slug)
        self.assertEqual(reviewed["review_average"], 4.5)
        self.assertEqual(reviewed["review_count"], 2)
        self.assertEqual(reviewed["recommendation_percent"], 50)

        without_reviews = next(item for item in payload["items"] if item["product_id"] == second_product.slug)
        self.assertIsNone(without_reviews["review_average"])
        self.assertEqual(without_reviews["review_count"], 0)
        self.assertEqual(without_reviews["recommendation_percent"], 0)

        page = self.client.get("/shop-cart.html")
        self.assertContains(page, 'assets/js/cart-comparison.js')

    def test_free_shipping_callout_tracks_the_purchase_goal(self):
        self.product.price = 250000
        self.product.save(update_fields=["price"])
        add = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 1}),
            content_type="application/json",
        )
        payload = add.json()
        self.assertFalse(payload["free_shipping_unlocked"])
        self.assertEqual(payload["free_shipping_remaining"], 150000)
        self.assertEqual(payload["free_shipping_progress"], 62)

        item_id = payload["items"][0]["id"]
        updated = self.client.patch(
            f"/api/cart/items/{item_id}/",
            data=json.dumps({"quantity": 2}),
            content_type="application/json",
        ).json()
        self.assertTrue(updated["free_shipping_unlocked"])
        self.assertEqual(updated["shipping"], 0)

        page = self.client.get("/shop-cart.html")
        self.assertContains(page, "¡Envío gratis desbloqueado!")
        self.assertContains(page, 'class="fa fa-check" data-free-shipping-icon')
        self.assertContains(page, ">GRATIS<")

    def test_shipping_weight_is_calculated_from_cart_products(self):
        self.product.weight_kg = "1.35"
        self.product.save(update_fields=["weight_kg"])
        response = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 2}),
            content_type="application/json",
        )
        self.assertEqual(response.json()["estimated_weight"], 2.7)

        page = self.client.get("/shop-cart.html")
        self.assertContains(page, "Peso calculado automáticamente")
        self.assertContains(page, 'value="2.70" data-auto-shipping-weight-input')
        self.assertContains(page, "calcularemos el envío automáticamente")

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
        cart_item = CartItem.objects.create(cart=cart, product=self.product, quantity=2, size="40")
        selected_variant = cart_item.variant
        selected_variant_stock_before = selected_variant.stock
        sibling_variant = self.product.variants.exclude(pk=selected_variant.pk).first()
        sibling_variant_stock_before = sibling_variant.stock
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
        order_item = order.items.get()
        self.assertEqual(order_item.variant, selected_variant)
        self.assertEqual(order_item.variant_sku, selected_variant.sku or "")
        self.assertEqual(order.item_count, 2)
        self.assertEqual(order.total, self.product.price * 2)
        self.assertEqual(order.recipient_name, "Ana Ruiz")
        self.assertIsNotNone(order.confirmation_email_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        confirmation = mail.outbox[0]
        self.assertTrue(confirmation.subject.startswith("Confirmaci"))
        self.assertIn(order.number, confirmation.subject)
        self.assertTrue(confirmation.subject.endswith("| Nexus Luxury Footwear"))
        self.assertEqual(confirmation.to, [user.email])
        html_body = next(alternative.content for alternative in confirmation.alternatives if alternative.mimetype == "text/html")
        self.assertIn(self.product.name, html_body)
        self.assertIn(order.number, html_body)
        self.assertIn("Talla 40", html_body)
        self.assertIn("Envío", html_body)
        self.assertIn("Gratis", html_body)
        self.assertIn("cid:nexus-order-product-1", html_body)
        self.assertIn('class="email-logo-cell"', html_body)
        self.assertIn("background:#17191c", html_body)
        inline_images = [attachment for attachment in confirmation.attachments if attachment.get_content_maintype() == "image"]
        self.assertGreaterEqual(len(inline_images), 2)
        order_logo = next(attachment for attachment in inline_images if attachment["Content-ID"] == "<nexus-order-logo>")
        self.assertEqual(order_logo.get_filename(), "nexus-logo-horizontal-dark.png")
        self.assertFalse(
            send_order_confirmation_email(
                order,
                order_url=f"http://testserver/order-confirmation/{order.number}/",
            )
        )
        self.assertEqual(len(mail.outbox), 1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, stock_before - 2)
        selected_variant.refresh_from_db()
        sibling_variant.refresh_from_db()
        self.assertEqual(selected_variant.stock, selected_variant_stock_before - 2)
        self.assertEqual(sibling_variant.stock, sibling_variant_stock_before)
        cart.refresh_from_db()
        self.assertEqual(cart.status, Cart.Status.CONVERTED)
        self.assertEqual(cart.items.count(), 0)

    @patch("store.views.send_order_confirmation_email", side_effect=OSError("smtp temporalmente no disponible"))
    def test_checkout_succeeds_when_confirmation_email_provider_is_unavailable(self, mocked_confirmation):
        user = User.objects.create_user(username="pedido-sin-correo", email="pedido@example.com", password="ClaveSegura123!")
        address = Address.objects.create(
            user=user,
            first_name="Laura",
            last_name="Gómez",
            address_line_1="Calle 8 # 3-20",
            department="Huila",
            city="Neiva",
            phone="3001114455",
            is_default=True,
        )
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="39")

        response = self.client.post(
            "/shop-checkout.html",
            {
                "address": address.id,
                "payment_method": Order.PaymentMethod.BANK_TRANSFER,
                "accept_terms": "on",
            },
        )

        order = Order.objects.get(user=user)
        self.assertRedirects(response, f"/order-confirmation/{order.number}/")
        mocked_confirmation.assert_called_once()

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

    def _coupon_client(self, username="cupon-checkout"):
        """Cliente con sesión, dirección y un producto en el carrito."""
        user = User.objects.create_user(username=username, email=f"{username}@example.com", password="ClaveSegura123!")
        Address.objects.create(
            user=user, first_name="Lina", last_name="Rojas", address_line_1="Calle 10 # 4-20",
            department="Huila", city="Neiva", phone="3009998877", is_default=True,
        )
        self.client.force_login(user)
        cart = Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")
        return user, cart

    def test_checkout_offers_its_own_coupon_field_and_returns_to_checkout(self):
        user, _ = self._coupon_client()
        Coupon.objects.create(
            code="CHECKOUT15", discount_type=Coupon.DiscountType.PERCENTAGE, value=15,
            starts_at=timezone.now() - timedelta(days=1), expires_at=timezone.now() + timedelta(days=1),
        )

        page = self.client.get("/shop-checkout.html")
        self.assertContains(page, 'id="checkoutCouponCode"', count=1)
        # El campo no puede anidarse dentro del formulario del pedido: se enlaza por id.
        self.assertContains(page, 'form="checkout-coupon-apply"')
        self.assertContains(page, 'id="checkout-coupon-apply"', count=1)

        applied = self.client.post("/cart-coupon/apply/", {"code": "checkout15", "origen": "checkout"})
        # Aplicarlo desde el checkout debe devolver al checkout, no al carrito.
        self.assertRedirects(applied, "/shop-checkout.html")

        expected = (self.product.price * Decimal("15") / Decimal("100")).quantize(Decimal("0.01"))
        summary = self.client.get("/shop-checkout.html")
        self.assertContains(summary, "CHECKOUT15")
        self.assertContains(summary, f"-${expected:,.0f} COP".replace(",", "."))
        self.assertContains(summary, 'form="checkout-coupon-remove"')

        removed = self.client.post("/cart-coupon/remove/", {"origen": "checkout"})
        self.assertRedirects(removed, "/shop-checkout.html")
        self.assertContains(self.client.get("/shop-checkout.html"), 'id="checkoutCouponCode"')

    def test_coupon_origin_only_accepts_known_destinations(self):
        self._coupon_client(username="cupon-origen")
        Coupon.objects.create(
            code="ORIGEN", discount_type=Coupon.DiscountType.FIXED, value=5000,
            starts_at=timezone.now() - timedelta(days=1), expires_at=timezone.now() + timedelta(days=1),
        )

        # Un origen inventado no debe poder sacar al cliente del sitio.
        for hostile in ("https://example.com/robo", "//example.com", "checkout/../../"):
            with self.subTest(origen=hostile):
                response = self.client.post("/cart-coupon/apply/", {"code": "ORIGEN", "origen": hostile})
                self.assertRedirects(response, "/shop-cart.html")

    def test_fixed_coupon_never_exceeds_the_subtotal(self):
        user, _ = self._coupon_client(username="cupon-grande")
        Coupon.objects.create(
            code="ENORME", discount_type=Coupon.DiscountType.FIXED, value=Decimal("99999999"),
            starts_at=timezone.now() - timedelta(days=1), expires_at=timezone.now() + timedelta(days=1),
        )

        self.client.post("/cart-coupon/apply/", {"code": "ENORME", "origen": "cart"})
        payload = self.client.get("/api/cart/").json()
        # El descuento se topa en el subtotal: nunca puede generar un total negativo.
        self.assertEqual(payload["discount"], int(self.product.price))
        self.assertEqual(payload["total_after_discount"], 0)
        self.assertGreaterEqual(payload["total"], 0)

        self.client.post("/shop-checkout.html", {
            "address": user.addresses.first().id,
            "payment_method": Order.PaymentMethod.BANK_TRANSFER,
            "notes": "", "accept_terms": "on",
        })
        order = Order.objects.get(user=user)
        self.assertEqual(order.discount_amount, order.subtotal)
        self.assertEqual(order.total, order.shipping_cost)

    def test_coupon_is_dropped_when_the_cart_stops_meeting_the_minimum(self):
        user, cart = self._coupon_client(username="cupon-minimo")
        CartItem.objects.filter(cart=cart).update(quantity=3)
        Coupon.objects.create(
            code="MINIMO", discount_type=Coupon.DiscountType.FIXED, value=10000,
            minimum_purchase=self.product.price * 2,
            starts_at=timezone.now() - timedelta(days=1), expires_at=timezone.now() + timedelta(days=1),
        )

        self.client.post("/cart-coupon/apply/", {"code": "MINIMO", "origen": "cart"})
        self.assertEqual(self.client.get("/api/cart/").json()["coupon_code"], "MINIMO")

        # Al bajar la cantidad el carrito deja de alcanzar la compra minima.
        CartItem.objects.filter(cart=cart).update(quantity=1)
        payload = self.client.get("/api/cart/").json()
        self.assertEqual(payload["coupon_code"], "")
        self.assertEqual(payload["discount"], 0)

    def test_coupon_not_yet_valid_and_usage_limit_are_rejected(self):
        self._coupon_client(username="cupon-vigencia")
        Coupon.objects.create(
            code="FUTURO", discount_type=Coupon.DiscountType.FIXED, value=5000,
            starts_at=timezone.now() + timedelta(days=1), expires_at=timezone.now() + timedelta(days=2),
        )
        agotado = Coupon.objects.create(
            code="AGOTADO", discount_type=Coupon.DiscountType.FIXED, value=5000,
            starts_at=timezone.now() - timedelta(days=1), expires_at=timezone.now() + timedelta(days=1),
            usage_limit=1,
        )
        Coupon.objects.filter(pk=agotado.pk).update(times_used=1)

        future = self.client.post("/cart-coupon/apply/", {"code": "FUTURO", "origen": "cart"}, follow=True)
        self.assertContains(future, "El cupon aun no esta vigente.")

        used_up = self.client.post("/cart-coupon/apply/", {"code": "AGOTADO", "origen": "cart"}, follow=True)
        self.assertContains(used_up, "El cupon alcanzo su limite de usos.")
        self.assertEqual(self.client.get("/api/cart/").json()["coupon_code"], "")

    def test_coupon_admin_rejects_case_insensitive_duplicates_and_invalid_limits(self):
        staff = User.objects.create_superuser(
            username="coupon-admin",
            email="coupon-admin@example.com",
            password="ClaveSegura123!",
        )
        now = timezone.localtime()
        Coupon.objects.create(
            code="SEGURO10",
            discount_type=Coupon.DiscountType.PERCENTAGE,
            value=10,
            minimum_purchase=0,
            starts_at=now - timedelta(days=1),
            expires_at=now + timedelta(days=1),
        )
        self.client.force_login(staff)
        valid_dates = {
            "starts_at_0": (now - timedelta(days=1)).date().isoformat(),
            "starts_at_1": "00:00:00",
            "expires_at_0": (now + timedelta(days=1)).date().isoformat(),
            "expires_at_1": "23:59:59",
        }

        duplicate = self.client.post("/admin/store/coupon/add/", {
            "code": "  seguro10  ",
            "discount_type": Coupon.DiscountType.PERCENTAGE,
            "value": "10",
            "minimum_purchase": "0",
            "usage_limit": "1",
            "once_per_user": "on",
            "is_active": "on",
            **valid_dates,
        })

        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(Coupon.objects.filter(code="SEGURO10").count(), 1)

        invalid = self.client.post("/admin/store/coupon/add/", {
            "code": "LIMITES-INVALIDOS",
            "discount_type": Coupon.DiscountType.PERCENTAGE,
            "value": "101",
            "minimum_purchase": "-1",
            "usage_limit": "0",
            "once_per_user": "on",
            "is_active": "on",
            **valid_dates,
        })

        self.assertEqual(invalid.status_code, 200)
        self.assertFalse(Coupon.objects.filter(code="LIMITES-INVALIDOS").exists())

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

    def test_shipping_type_is_visible_and_status_changes_are_controlled_in_admin(self):
        user = User.objects.create_user(username="seguimiento", password="ClaveSegura123!")
        order = Order.objects.create(
            user=user,
            number="JS-TRACK-0001",
            recipient_name="Cliente Seguimiento",
            phone="300",
            address_line_1="Recogida en tienda",
            department="Huila",
            city="Neiva",
            subtotal=self.product.price,
            total=self.product.price,
            delivery_method=Order.DeliveryMethod.PICKUP,
            fulfillment_status=Order.FulfillmentStatus.PACKING,
        )
        self.client.force_login(user)

        account_response = self.client.get("/account.html?tab=orders")
        self.assertContains(account_response, "Recogida en Neiva")
        self.assertContains(account_response, "Empacando producto")

        detail_response = self.client.get(f"/orders/{order.number}/")
        for label in ("Pendiente de envío", "Empacando producto", "En camino", "Entregado"):
            self.assertContains(detail_response, label)
        self.assertContains(detail_response, "shipping-tracking__step is-current", html=False)

        order_admin = admin.site._registry[Order]
        self.assertNotIn("fulfillment_status", order_admin.list_editable)
        self.assertIn("status", order_admin.get_readonly_fields(None))
        self.assertIn("fulfillment_status", order_admin.list_filter)

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

    def test_order_detail_embeds_a_map_for_courier_deliveries_only(self):
        owner = User.objects.create_user(username="mapa-dueno", password="ClaveSegura123!")
        courier_order = Order.objects.create(
            user=owner, number="JS-MAPA-0001", recipient_name="Cliente Mapa", phone="300",
            address_line_1="Cra 5 # 12-34", address_line_2="Apto 201", department="Huila", city="Neiva",
            subtotal=1000, total=1000, delivery_method=Order.DeliveryMethod.COURIER,
        )
        pickup_order = Order.objects.create(
            user=owner, number="JS-MAPA-0002", recipient_name="Cliente Mapa", phone="300",
            address_line_1="Recogida en tienda", department="Huila", city="Neiva",
            subtotal=1000, total=1000, delivery_method=Order.DeliveryMethod.PICKUP,
        )
        self.client.force_login(owner)

        courier_detail = self.client.get(f"/orders/{courier_order.number}/")
        self.assertContains(courier_detail, "order-delivery-map")
        self.assertContains(courier_detail, "maps?q=Cra%205%20%23%2012-34%2C%20Apto%20201%2C%20Neiva%2C%20Huila%2C%20Colombia&amp;output=embed")

        pickup_detail = self.client.get(f"/orders/{pickup_order.number}/")
        self.assertNotContains(pickup_detail, "order-delivery-map")

        # La confirmación no repite el mapa: el detalle del panel es su lugar propio.
        confirmation = self.client.get(f"/order-confirmation/{courier_order.number}/")
        self.assertNotContains(confirmation, "order-delivery-map")

    def test_order_receipt_pdf_is_downloadable_and_scoped_to_owner(self):
        owner = User.objects.create_user(username="dueno-pdf", password="ClaveSegura123!")
        other = User.objects.create_user(username="ajeno-pdf", password="ClaveSegura123!")
        order = Order.objects.create(
            user=owner, number="JS-PDF-0001", recipient_name="Cliente PDF", phone="300",
            address_line_1="Calle 1", department="Huila", city="Neiva",
            subtotal=self.product.price, total=self.product.price,
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            product_image=self.product.image, unit_price=self.product.price, quantity=1, size="39",
        )
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/orders/{order.number}/comprobante.pdf").status_code, 404)
        self.client.force_login(owner)
        response = self.client.get(f"/orders/{order.number}/comprobante.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f'filename="comprobante-{order.number}.pdf"', response["Content-Disposition"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF"))

    def test_receipt_verification_link_confirms_a_genuine_order(self):
        owner = User.objects.create_user(username="dueno-qr", password="ClaveSegura123!")
        order = Order.objects.create(
            user=owner, number="JS-QR-0001", recipient_name="Cliente QR", phone="300",
            address_line_1="Calle 1", department="Huila", city="Neiva",
            subtotal=self.product.price, total=self.product.price, status=Order.Status.PAID,
        )
        token = receipt_verification_token(order)

        response = self.client.get(f"/verificar-comprobante/{token}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Comprobante autentico")
        self.assertContains(response, order.number)
        # No se filtran datos personales del cliente en la pagina publica.
        self.assertNotContains(response, "Cliente QR")
        self.assertNotContains(response, "Calle 1")

    def test_receipt_verification_rejects_a_tampered_or_unknown_token(self):
        owner = User.objects.create_user(username="dueno-qr-2", password="ClaveSegura123!")
        order = Order.objects.create(
            user=owner, number="JS-QR-0002", recipient_name="Cliente QR 2", phone="300",
            address_line_1="Calle 1", department="Huila", city="Neiva",
            subtotal=self.product.price, total=self.product.price,
        )
        token = receipt_verification_token(order)
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

        tampered_response = self.client.get(f"/verificar-comprobante/{tampered}/")
        self.assertContains(tampered_response, "No pudimos validar este comprobante")

        order.delete()
        deleted_order_response = self.client.get(f"/verificar-comprobante/{token}/")
        self.assertContains(deleted_order_response, "No pudimos validar este comprobante")

    def test_pdf_receipt_includes_the_verification_qr_code(self):
        owner = User.objects.create_user(username="dueno-qr-3", password="ClaveSegura123!")
        order = Order.objects.create(
            user=owner, number="JS-QR-0003", recipient_name="Cliente QR 3", phone="300",
            address_line_1="Calle 1", department="Huila", city="Neiva",
            subtotal=self.product.price, total=self.product.price,
        )
        self.client.force_login(owner)

        response = self.client.get(f"/orders/{order.number}/comprobante.pdf")

        self.assertEqual(response.status_code, 200)
        pdf_bytes = b"".join(response.streaming_content)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        # El QR es un grafico vectorial embebido; confirmamos que el PDF creció
        # respecto a un comprobante sin el bloque de validacion.
        self.assertGreater(len(pdf_bytes), 3000)

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
        self.assertContains(clients_response, 'data-detail-toggle="client-info-')
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

    def test_admin_panel_hides_client_and_sales_data_from_staff_without_permission(self):
        """Una cuenta staff creada para moderar el blog no debe leer la base de clientes."""
        client_user = User.objects.create_user(username="cliente-privado", first_name="Ana", last_name="Reyes", password="ClaveSegura123!")
        CustomerProfile.objects.create(user=client_user, document_number="1075123456", phone="3009998877")
        Address.objects.create(
            user=client_user, label="Casa", first_name="Ana", last_name="Reyes",
            address_line_1="Calle Secreta 42", department="Huila", city="Neiva",
            phone="3009998877", is_default=True,
        )
        sale = Order.objects.create(
            user=client_user, number="JS-PERM-0001", status=Order.Status.PAID,
            recipient_name="Ana Reyes", phone="3009998877", address_line_1="Calle Secreta 42",
            department="Huila", city="Neiva", subtotal=self.product.price, total=self.product.price,
        )

        editor = User.objects.create_user(username="editor-blog", password="ClaveSegura123!", is_staff=True)
        editor.user_permissions.add(Permission.objects.get(codename="view_blogpost", content_type__app_label="store"))
        self.client.force_login(editor)

        overview = self.client.get("/panel-admin/")
        self.assertEqual(overview.status_code, 200)
        self.assertTrue(overview.context["section_access"]["blog"])
        self.assertFalse(overview.context["section_access"]["clients"])
        self.assertFalse(overview.context["section_access"]["sales"])
        # El menú no ofrece las secciones vedadas.
        self.assertNotContains(overview, 'href="panel-admin/?section=clients#admin-panel-content"')
        self.assertNotContains(overview, 'href="panel-admin/?section=sales#admin-panel-content"')

        # Pedirlas por URL cae al resumen, sin cargar ni filtrar los datos.
        for blocked in ("clients", "sales", "reports"):
            response = self.client.get(f"/panel-admin/?section={blocked}")
            self.assertEqual(response.context["section"], "overview")
            self.assertNotContains(response, "1075123456")
            self.assertNotContains(response, "Calle Secreta 42")
            self.assertNotContains(response, sale.number)
        self.assertEqual(list(overview.context["clients"]), [])
        self.assertEqual(list(overview.context["successful_orders"]), [])

        # Su propia sección sigue funcionando.
        blog_response = self.client.get("/panel-admin/?section=blog")
        self.assertEqual(blog_response.context["section"], "blog")

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
        self.assertContains(public_comment, "Respuesta de Nexus Luxury Footwear")
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
        self.assertContains(products_response, "Inventario por variantes")
        self.assertContains(products_response, "/admin/store/productvariant/")
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
            "release_date": "2020-02-29",
            "brand": StoreSection.objects.get(slug="jordan").pk,
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
        combinations = [
            ("38", "Gris oscuro", "#505050", 2),
            ("39", "Gris oscuro", "#505050", 2),
            ("40", "Gris oscuro", "#505050", 2),
            ("38", "Azul", "#586882", 2),
            ("39", "Azul", "#586882", 1),
            ("40", "Azul", "#586882", 1),
        ]
        for size, color_name, color_hex, stock in combinations:
            ProductVariant.objects.create(
                product=product,
                size=size,
                color_name=color_name,
                color_hex=color_hex,
                stock=stock,
            )
        product.refresh_from_db()
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
        self.assertEqual(product.release_date, date(2020, 2, 29))
        self.assertEqual(product.release_date_source, Product.ReleaseDateSource.MANUAL)
        self.assertTrue(product.has_discount)
        self.assertEqual(product.discount_percent, 11)

        response = self.client.get(f"/single-product.html?producto={product.slug}")
        self.assertContains(response, 'data-color="Gris oscuro"')
        self.assertEqual(product.collection, Product.Collection.CLASSICS)
        self.assertEqual(product.tags, ["Retro", "cuero"])
        self.assertContains(response, 'data-bg-color="#586882"')
        self.assertContains(response, 'data-size="38"')
        self.assertContains(response, 'data-size="40"')
        self.assertContains(response, 'id="product-variant-inventory"', html=False)
        self.assertContains(response, '"stock": 2', html=False)
        self.assertContains(response, product.description)
        self.assertContains(response, product.additional_information)
        self.assertContains(response, product.detailed_description)
        self.assertContains(response, product.sku)
        self.assertContains(response, 'datetime="2020-02-29"')
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
            "sku", "release_date", "lookup_release_date", "description", "additional_information", "detailed_description",
            "price", "compare_at_price", "weight_kg", "image",
            "image_alt", "gallery", "sizes", "colors", "tags", "collection", "is_active",
        ):
            self.assertContains(response, f'id="id_{field_name}"', html=False)
        self.assertContains(response, "El inventario total se calcula automáticamente")
        self.assertContains(response, 'id="id_variants-0-stock"', html=False)
        self.assertContains(response, "Dónde se muestra")
        self.assertContains(response, "Marca donde se muestra")
        self.assertContains(response, "Otras secciones donde se muestra")

    def test_product_admin_creates_product_in_selected_brand_and_sections(self):
        custom_section = StoreSection.objects.create(
            title="Destacados",
            slug="destacados",
            description="Productos destacados por el equipo.",
            banner_image_url="https://images.example.com/destacados-banner.webp",
            empty_image_url="https://images.example.com/destacados-empty.webp",
        )
        staff = User.objects.create_superuser(
            username="product-placement-admin",
            email="placement@example.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(staff)

        response = self.client.post("/admin/store/product/add/", {
            "name": "Producto multisección",
            "slug": "producto-multiseccion",
            "sku": "MULTI-001",
            "brand": StoreSection.objects.get(slug="nike").pk,
            "audience": Product.Audience.MEN,
            "product_type": Product.ProductType.FOOTWEAR,
            "collection": Product.Collection.CLASSICS,
            "is_on_sale": "on",
            "store_sections": [custom_section.pk],
            "description": "Producto visible en destinos seleccionados.",
            "additional_information": "",
            "detailed_description": "",
            "price": "320000",
            "compare_at_price": "350000",
            "weight_kg": "1.00",
            "image": "assets/img/shop/jordan423.png",
            "image_alt": "Producto multisección",
            "gallery": "",
            "tags": "Destacado",
            "is_active": "on",
            "uploaded_images-TOTAL_FORMS": "1",
            "uploaded_images-INITIAL_FORMS": "0",
            "uploaded_images-MIN_NUM_FORMS": "0",
            "uploaded_images-MAX_NUM_FORMS": "1000",
            "uploaded_images-0-image_alt": "",
            "uploaded_images-0-position": "0",
            "variants-TOTAL_FORMS": "1",
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "1",
            "variants-MAX_NUM_FORMS": "1000",
            "variants-0-sku": "MULTI-001-40",
            "variants-0-size": "40",
            "variants-0-color_name": "Negro",
            "variants-0-color_hex": "#111111",
            "variants-0-stock": "4",
            "variants-0-is_active": "on",
            "_save": "Guardar",
        })

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(slug="producto-multiseccion")
        self.assertEqual(product.brand.slug, "nike")
        self.assertEqual(list(product.store_sections.values_list("slug", flat=True)), ["destacados"])
        self.assertEqual(product.stock, 4)
        for section_slug in ("nike", "hombre", "clasicas", "ofertas", "destacados"):
            with self.subTest(section=section_slug):
                self.assertIn(product.name, self.section_product_names(section_slug))

    def test_product_admin_can_show_remove_and_clear_sizes_and_colors(self):
        self.product.variants.all().delete()
        black = ProductVariant.objects.create(
            product=self.product,
            sku="VAR-BLACK-38",
            size="38",
            color_name="Negro",
            color_hex="#111111",
            stock=3,
        )
        red = ProductVariant.objects.create(
            product=self.product,
            sku="VAR-RED-40",
            size="40",
            color_name="Rojo",
            color_hex="#CC2222",
            stock=2,
        )
        staff = User.objects.create_superuser(
            username="variants-admin",
            email="variants@example.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(staff)
        change_url = f"/admin/store/product/{self.product.pk}/change/"

        change_page = self.client.get(change_url)
        self.assertContains(change_page, 'value="VAR-BLACK-38"', html=False)
        self.assertContains(change_page, 'value="VAR-RED-40"', html=False)
        self.assertContains(change_page, 'id="id_variants-0-stock"', html=False)

        black.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.sizes, ["40"])
        self.assertEqual(self.product.colors, [{"name": "Rojo", "hex": "#CC2222"}])
        self.assertEqual(self.product.stock, 2)

        detail_url = f"/single-product.html?producto={self.product.slug}"
        detail = self.client.get(detail_url)
        self.assertNotContains(detail, 'data-size="38"')
        self.assertContains(detail, 'data-size="40"')
        self.assertNotContains(detail, 'data-color="Negro"')
        self.assertContains(detail, 'data-color="Rojo"')

        red.delete()
        self.product.refresh_from_db()
        self.assertEqual(self.product.sizes, [])
        self.assertEqual(self.product.colors, [])
        self.assertEqual(self.product.stock, 0)

        detail_without_variants = self.client.get(detail_url)
        self.assertNotContains(detail_without_variants, '<div class="product-size">', html=False)
        self.assertNotContains(detail_without_variants, '<div class="product-color">', html=False)

    def test_session_greets_the_client_by_name(self):
        anonymous = self.client.get("/api/session/").json()
        self.assertFalse(anonymous["authenticated"])
        self.assertEqual(anonymous["greeting"], "")

        client_user = User.objects.create_user(
            username="camila123",
            email="camila@example.com",
            password="ClaveSegura123!",
            first_name="Camila",
        )
        self.client.force_login(client_user)
        greeted = self.client.get("/api/session/").json()
        self.assertEqual(greeted["greeting"], "Hola, Camila")
        self.assertEqual(greeted["username"], "Camila")
        self.assertEqual(greeted["label"], "Mi cuenta")

    def test_session_greeting_falls_back_to_the_username(self):
        nameless = User.objects.create_user(
            username="sinnombre",
            email="sinnombre@example.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(nameless)

        payload = self.client.get("/api/session/").json()
        self.assertEqual(payload["greeting"], "Hola, sinnombre")

    def test_session_keeps_the_admin_panel_destination_for_staff(self):
        staff = User.objects.create_superuser(
            username="staff-saludo",
            email="staff-saludo@example.com",
            password="ClaveSegura123!",
            first_name="Emerson",
        )
        self.client.force_login(staff)

        payload = self.client.get("/api/session/").json()
        self.assertEqual(payload["greeting"], "Hola, Emerson")
        # El encabezado se redibuja con estos datos: si dijera "Mi cuenta" el
        # staff perderia el acceso al panel desde la barra superior.
        self.assertEqual(payload["label"], "Panel admin")
        self.assertEqual(payload["href"], "panel-admin/")

    def test_brand_section_paginates_after_nine_products(self):
        jordan = StoreSection.objects.get(slug="jordan")
        for index in range(12):
            product = Product.objects.create(
                slug=f"jordan-paginado-{index}",
                name=f"Jordan Paginado {index:02d}",
                brand=jordan,
                description="Producto para probar la paginacion.",
                price=Decimal("200000") + index,
                image="assets/img/shop/jordan423.png",
                audience=Product.Audience.UNISEX,
                product_type=Product.ProductType.FOOTWEAR,
                collection=Product.Collection.URBAN,
            )
            ProductVariant.objects.create(product=product, size="41", color_name="Negro", stock=2)

        first_page = self.client.get("/secciones/jordan/")
        self.assertEqual(len(first_page.context["page_obj"].object_list), 9)
        self.assertTrue(first_page.context["page_obj"].has_next())
        self.assertContains(first_page, 'class="pagination')

        names = self.section_product_names("jordan")
        # Ninguna pagina repite ni se salta productos.
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), first_page.context["page_obj"].paginator.count)

    def test_brand_section_filters_by_size_color_and_price(self):
        jordan = StoreSection.objects.get(slug="jordan")
        exclusive = Product.objects.create(
            slug="jordan-filtro-exclusivo",
            name="Jordan Filtro Exclusivo",
            brand=jordan,
            description="Unico con esta talla y color.",
            price=Decimal("999000"),
            image="assets/img/shop/jordan423.png",
            audience=Product.Audience.UNISEX,
            product_type=Product.ProductType.FOOTWEAR,
            collection=Product.Collection.URBAN,
        )
        ProductVariant.objects.create(product=exclusive, size="47", color_name="Turquesa", stock=3)

        by_size = self.client.get("/secciones/jordan/", {"talla": "47"})
        self.assertEqual([item.name for item in by_size.context["page_obj"].object_list], [exclusive.name])

        by_color = self.client.get("/secciones/jordan/", {"color": "Turquesa"})
        self.assertEqual([item.name for item in by_color.context["page_obj"].object_list], [exclusive.name])

        # El precio mas alto del catalogo aisla al mismo producto.
        by_price = self.client.get("/secciones/jordan/", {"precioMin": "900000"})
        self.assertEqual([item.name for item in by_price.context["page_obj"].object_list], [exclusive.name])

        empty = self.client.get("/secciones/jordan/", {"talla": "47", "color": "Bordeaux"})
        self.assertEqual(list(empty.context["page_obj"].object_list), [])
        # Sigue siendo una seccion con productos, no una en preparacion.
        self.assertContains(empty, "No encontramos productos")

        options = by_size.context["catalog_filters"]
        self.assertIn("47", options["sizes"])
        self.assertIn({"name": "Turquesa", "hex": "#17A2A2"}, options["colors"])
        # Solo se ofrecen tallas que existen en la seccion.
        self.assertNotIn("35", options["sizes"])

    def test_brand_section_sorts_by_price_and_keeps_filters_in_pagination(self):
        ascending = self.client.get("/secciones/jordan/", {"orden": "price-asc"})
        prices = [item.price for item in ascending.context["page_obj"].object_list]
        self.assertEqual(prices, sorted(prices))

        descending = self.client.get("/secciones/jordan/", {"orden": "price-desc"})
        prices = [item.price for item in descending.context["page_obj"].object_list]
        self.assertEqual(prices, sorted(prices, reverse=True))

        # El enlace de paginacion conserva el filtro activo y descarta la pagina.
        filtered = self.client.get("/secciones/jordan/", {"talla": "40", "pagina": "1"})
        self.assertEqual(filtered.context["catalog_filters"]["querystring"], "talla=40")

    def test_brand_section_cards_drop_the_brand_badge(self):
        response = self.client.get("/secciones/jordan/")
        # El diseno pasa a ser el de la tienda.
        self.assertContains(response, 'class="product-item"')
        self.assertContains(response, "shop-sidebar")
        # La etiqueta de marca sobre la imagen ya no se dibuja.
        self.assertNotContains(response, "offer-product-card__media")

    def test_color_hex_is_deduced_from_the_name_in_spanish_and_english(self):
        self.assertEqual(color_hex_from_name("Negro"), "#111111")
        self.assertEqual(color_hex_from_name("  BLANCO "), "#F4F4F4")
        self.assertEqual(color_hex_from_name("Bordeaux"), "#6D1F2E")
        # El nombre compuesto mas largo gana sobre el generico que contiene.
        self.assertEqual(color_hex_from_name("Azul marino"), "#17224D")
        self.assertNotEqual(color_hex_from_name("Azul marino"), color_hex_from_name("Azul"))
        self.assertEqual(color_hex_from_name("Negro/Blanco"), "#111111")
        # Los acentos y las mayusculas no deben cambiar el resultado.
        self.assertEqual(color_hex_from_name("Púrpura"), color_hex_from_name("purpura"))
        self.assertIsNone(color_hex_from_name("Color principal"))
        self.assertIsNone(color_hex_from_name(""))

    def test_calculated_color_gets_a_readable_name(self):
        self.assertEqual(nearest_color_name("#111111"), "Negro")
        self.assertEqual(nearest_color_name("#6D1F2E"), "Bordeaux")
        # Un carbon sin saturacion debe nombrarse gris y no "Chocolate", que es
        # el marron mas cercano si solo se mide la distancia entre canales.
        self.assertEqual(nearest_color_name("#363638"), "Gris oscuro")
        self.assertIsNone(nearest_color_name("no es un color"))

    def test_unknown_color_name_falls_back_to_the_dominant_color_of_the_photo(self):
        product = Product.objects.get(slug="nike-sb-dunk-low-travis-scott")
        dominant = dominant_color_from_image(product)

        self.assertIsNotNone(dominant)
        self.assertRegex(dominant, r"^#[0-9A-F]{6}$")
        # El fondo blanco del estudio no puede ganar: seria un swatch invisible.
        self.assertLess(int(dominant[1:3], 16), 235)
        self.assertEqual(resolve_color_hex("Tono exclusivo", product=product), dominant)
        # Un hexadecimal explicito manda sobre el nombre y sobre la foto.
        self.assertEqual(resolve_color_hex("Negro", explicit_hex="#ABCDEF", product=product), "#ABCDEF")
        self.assertEqual(resolve_color_hex("Negro", product=product), "#111111")

    def test_variant_without_hex_takes_the_color_deduced_from_its_name(self):
        self.product.variants.all().delete()
        variant = ProductVariant.objects.create(
            product=self.product,
            size="41",
            color_name="Bordeaux",
            stock=2,
        )

        variant.refresh_from_db()
        self.assertEqual(variant.color_hex, "#6D1F2E")
        self.product.refresh_from_db()
        self.assertEqual(self.product.colors, [{"name": "Bordeaux", "hex": "#6D1F2E"}])

    def test_product_admin_creates_variants_from_manually_written_sizes_and_colors(self):
        staff = User.objects.create_superuser(
            username="variantes-manuales",
            email="manuales@example.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(staff)

        response = self.client.post("/admin/store/product/add/", {
            "name": "Producto escrito a mano",
            "slug": "producto-escrito-a-mano",
            "sku": "MANUAL-001",
            "brand": StoreSection.objects.get(slug="jordan").pk,
            "audience": Product.Audience.UNISEX,
            "product_type": Product.ProductType.FOOTWEAR,
            "collection": Product.Collection.URBAN,
            "description": "Tallas y colores escritos desde el CRUD.",
            "additional_information": "",
            "detailed_description": "",
            "price": "300000",
            "compare_at_price": "",
            "weight_kg": "1.00",
            "image": "assets/img/shop/jordan423.png",
            "image_alt": "Producto escrito a mano",
            "gallery": "",
            "sizes": "40, 41, 42",
            # Sin hexadecimal: se debe deducir del nombre.
            "colors": "Negro\nBlanco",
            "variant_stock": "3",
            "tags": "",
            "is_active": "on",
            "uploaded_images-TOTAL_FORMS": "1",
            "uploaded_images-INITIAL_FORMS": "0",
            "uploaded_images-MIN_NUM_FORMS": "0",
            "uploaded_images-MAX_NUM_FORMS": "1000",
            "uploaded_images-0-image_alt": "",
            "uploaded_images-0-position": "0",
            "variants-TOTAL_FORMS": "1",
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "1",
            "variants-MAX_NUM_FORMS": "1000",
            "variants-0-size": "40",
            "variants-0-color_name": "Negro",
            "variants-0-color_hex": "#111111",
            "variants-0-stock": "5",
            "variants-0-is_active": "on",
            "_save": "Guardar",
        })

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(slug="producto-escrito-a-mano")
        # 3 tallas x 2 colores, sin duplicar la que vino en el inline.
        self.assertEqual(product.variants.count(), 6)
        self.assertEqual(product.variants.get(size="40", color_name="Negro").stock, 5)
        self.assertEqual(product.variants.get(size="42", color_name="Blanco").stock, 3)
        self.assertEqual(product.sizes, ["40", "41", "42"])
        self.assertEqual(product.colors, [
            {"name": "Negro", "hex": "#111111"},
            {"name": "Blanco", "hex": "#F4F4F4"},
        ])
        # 5 de la variante del inline + 5 variantes nuevas de 3 unidades.
        self.assertEqual(product.stock, 20)

        detail = self.client.get(f"/single-product.html?producto={product.slug}")
        self.assertContains(detail, 'data-size="41"')
        self.assertContains(detail, 'data-bg-color="#F4F4F4"')
        self.assertContains(detail, 'data-color="Negro"')
        self.assertNotContains(detail, "Producto agotado")

    def test_product_admin_keeps_variants_when_the_summary_is_left_empty(self):
        staff = User.objects.create_superuser(
            username="resumen-vacio",
            email="vacio@example.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(staff)
        self.product.variants.all().delete()
        kept = ProductVariant.objects.create(
            product=self.product,
            size="43",
            color_name="Verde militar",
            stock=4,
        )

        response = self.client.post(f"/admin/store/product/{self.product.pk}/change/", {
            "name": self.product.name,
            "slug": self.product.slug,
            "sku": self.product.sku,
            "brand": self.product.brand_id,
            "audience": self.product.audience,
            "product_type": self.product.product_type,
            "collection": self.product.collection,
            "description": self.product.description,
            "additional_information": "",
            "detailed_description": "",
            "price": str(self.product.price),
            "compare_at_price": "",
            "weight_kg": "1.00",
            "image": self.product.image,
            "image_alt": "",
            "gallery": "",
            "sizes": "",
            "colors": "",
            "variant_stock": "0",
            "tags": "",
            "is_active": "on",
            "uploaded_images-TOTAL_FORMS": "0",
            "uploaded_images-INITIAL_FORMS": "0",
            "uploaded_images-MIN_NUM_FORMS": "0",
            "uploaded_images-MAX_NUM_FORMS": "1000",
            "variants-TOTAL_FORMS": "0",
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "1",
            "variants-MAX_NUM_FORMS": "1000",
            "_save": "Guardar",
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProductVariant.objects.filter(pk=kept.pk).exists())
        self.assertEqual(self.product.variants.count(), 1)

    @override_settings(
        STOCKX_API_KEY="api-key-prueba",
        STOCKX_ACCESS_TOKEN="access-token-prueba",
        STOCKX_CLIENT_ID="",
        STOCKX_CLIENT_SECRET="",
        STOCKX_REFRESH_TOKEN="",
        STOCKX_TIMEOUT_SECONDS=2,
    )
    @patch("store.stockx.urlopen")
    def test_stockx_lookup_matches_exact_style_id_and_release_date(self, mocked_urlopen):
        mocked_urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({
            "products": [
                {
                    "productId": "stockx-product-1",
                    "styleId": "FV5029-006",
                    "title": "Nike Air",
                    "productAttributes": {"releaseDate": "2024-05-11"},
                }
            ]
        }).encode("utf-8")

        result = lookup_release_date("fv5029-006")

        self.assertEqual(result.release_date, date(2024, 5, 11))
        self.assertEqual(result.product_id, "stockx-product-1")
        request = mocked_urlopen.call_args.args[0]
        self.assertIn("query=fv5029-006", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer access-token-prueba")
        self.assertEqual(request.get_header("X-api-key"), "api-key-prueba")

    @patch("store.admin.lookup_release_date")
    def test_product_admin_can_autocomplete_release_date_from_stockx(self, mocked_lookup):
        mocked_lookup.return_value = StockXReleaseDate(
            release_date=date(2023, 8, 25),
            product_id="stockx-product-admin",
            title="Producto de prueba",
        )
        staff = User.objects.create_superuser(
            username="stockx-admin",
            email="stockx@example.com",
            password="ClaveSegura123!",
        )
        self.client.force_login(staff)

        response = self.client.post("/admin/store/product/add/", {
            "name": "Producto híbrido",
            "slug": "producto-hibrido",
            "sku": "FV5029-006",
            "brand": StoreSection.objects.get(slug="nike").pk,
            "audience": Product.Audience.UNISEX,
            "product_type": Product.ProductType.FOOTWEAR,
            "collection": Product.Collection.URBAN,
            "description": "Producto con fecha automática.",
            "additional_information": "",
            "detailed_description": "",
            "price": "300000",
            "compare_at_price": "",
            "stock": "5",
            "weight_kg": "1.00",
            "image": "assets/img/shop/jordan423.png",
            "image_alt": "Producto híbrido",
            "gallery": "",
            "sizes": "40, 41",
            "colors": "Negro | #111111",
            "tags": "Urbano",
            "is_active": "on",
            "lookup_release_date": "on",
            "uploaded_images-TOTAL_FORMS": "1",
            "uploaded_images-INITIAL_FORMS": "0",
            "uploaded_images-MIN_NUM_FORMS": "0",
            "uploaded_images-MAX_NUM_FORMS": "1000",
            "uploaded_images-0-image_alt": "",
            "uploaded_images-0-position": "0",
            "variants-TOTAL_FORMS": "1",
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "1",
            "variants-MAX_NUM_FORMS": "1000",
            "variants-0-sku": "FV5029-006-40-NEGRO",
            "variants-0-size": "40",
            "variants-0-color_name": "Negro",
            "variants-0-color_hex": "#111111",
            "variants-0-stock": "5",
            "variants-0-is_active": "on",
            "_save": "Guardar",
        })

        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(slug="producto-hibrido")
        self.assertEqual(product.release_date, date(2023, 8, 25))
        self.assertEqual(product.release_date_source, Product.ReleaseDateSource.STOCKX)
        self.assertEqual(product.stockx_product_id, "stockx-product-admin")
        self.assertIsNotNone(product.release_date_checked_at)
        self.assertEqual(product.stock, 5)
        self.assertTrue(product.variants.filter(sku="FV5029-006-40-NEGRO", stock=5).exists())

    def test_cart_validates_and_keeps_color_and_size(self):
        self.product.variants.all().delete()
        ProductVariant.objects.create(
            product=self.product,
            size="38",
            color_name="Negro",
            color_hex="#111111",
            stock=1,
        )
        selected_variant = ProductVariant.objects.create(
            product=self.product,
            size="40",
            color_name="Rojo",
            color_hex="#CC2222",
            stock=3,
        )

        invalid = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "size": "99", "color": "Negro"}),
            content_type="application/json",
        )
        self.assertEqual(invalid.status_code, 400)

        impossible_combination = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "size": "38", "color": "Rojo"}),
            content_type="application/json",
        )
        self.assertEqual(impossible_combination.status_code, 400)

        response = self.client.post(
            "/api/cart/items/",
            data=json.dumps({"product_id": self.product.slug, "quantity": 5, "size": "40", "color": "Rojo"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        item = CartItem.objects.get()
        self.assertEqual(item.variant, selected_variant)
        self.assertEqual(item.size, "40")
        self.assertEqual(item.color, "Rojo")
        self.assertEqual(item.quantity, 3)
        self.assertEqual(response.json()["items"][0]["color"], "Rojo")
        self.assertEqual(response.json()["items"][0]["stock"], 3)

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


def _fake_image_bytes(image_format, size=(2, 2)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(200, 30, 30)).save(buffer, format=image_format)
    return buffer.getvalue()


class UploadedMediaValidationTests(TestCase):
    """FileExtensionValidator solo mira el nombre; esto valida el contenido real."""

    def test_accepts_genuine_images_in_every_allowed_format(self):
        for image_format, extension in (("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")):
            upload = SimpleUploadedFile(f"banner.{extension}", _fake_image_bytes(image_format), content_type=f"image/{extension}")
            validate_uploaded_media(upload)

    def test_rejects_a_script_disguised_with_an_image_extension(self):
        upload = SimpleUploadedFile("banner.jpg", b"<script>alert(document.cookie)</script>", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_uploaded_media(upload)

    def test_rejects_an_image_whose_extension_does_not_match_its_content(self):
        upload = SimpleUploadedFile(
            "banner.jpg",
            _fake_image_bytes("PNG"),
            content_type="image/jpeg",
        )
        with self.assertRaises(ValidationError):
            validate_uploaded_media(upload)

    def test_complex_image_is_compressed_to_the_web_weight_target(self):
        source = io.BytesIO()
        Image.effect_noise((1200, 1200), 100).convert("RGB").save(source, format="PNG")
        upload = SimpleUploadedFile("textura.png", source.getvalue(), content_type="image/png")

        name, optimized = optimize_uploaded_image(upload, max_size=(1600, 1600))

        self.assertEqual(name, "textura.webp")
        self.assertLessEqual(optimized.size, TARGET_IMAGE_BYTES)
        with Image.open(optimized) as image:
            self.assertEqual(image.format, "WEBP")

    def test_accepts_genuine_mp4_and_webm_signatures(self):
        mp4 = SimpleUploadedFile("clip.mp4", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20, content_type="video/mp4")
        validate_uploaded_media(mp4)
        webm = SimpleUploadedFile("clip.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 20, content_type="video/webm")
        validate_uploaded_media(webm)

    def test_rejects_a_video_heavier_than_the_upload_limit(self):
        oversized = SimpleUploadedFile(
            "pesado.mp4",
            b"\x00\x00\x00\x18ftypmp42" + b"\x00" * (MAX_VIDEO_UPLOAD_BYTES + 1),
            content_type="video/mp4",
        )
        # Nginx corta en 20 MB devolviendo un 413 sin explicacion: el limite
        # propio tiene que saltar antes para que el mensaje sea entendible.
        with self.assertRaises(ValidationError) as raised:
            validate_uploaded_media(oversized)
        self.assertIn("15 MB", str(raised.exception))

    def test_banner_media_type_follows_the_uploaded_file(self):
        video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20
        # El desplegable queda en "Imagen" pero el archivo es un MP4: sin
        # corregirlo el banner se dibujaria como una <img> rota.
        banner = HomeBanner(
            name="Banner con video",
            media_type=HomeBanner.MediaType.IMAGE,
            media_file=SimpleUploadedFile("promo.mp4", video_bytes, content_type="video/mp4"),
        )
        banner.full_clean()
        self.assertEqual(banner.media_type, HomeBanner.MediaType.VIDEO)

        image = HomeBanner(
            name="Banner con imagen",
            media_type=HomeBanner.MediaType.VIDEO,
            media_file=SimpleUploadedFile("promo.png", _fake_image_bytes("PNG"), content_type="image/png"),
        )
        image.full_clean()
        self.assertEqual(image.media_type, HomeBanner.MediaType.IMAGE)

        # Una URL sin extension conserva la eleccion manual del administrador.
        streamed = HomeBanner(name="Banner remoto", media_type=HomeBanner.MediaType.VIDEO, media_url="https://cdn.example.com/clip")
        streamed.full_clean()
        self.assertEqual(streamed.media_type, HomeBanner.MediaType.VIDEO)

    def test_rejects_a_video_extension_without_a_matching_signature(self):
        upload = SimpleUploadedFile("clip.mp4", b"esto no es un video real", content_type="video/mp4")
        with self.assertRaises(ValidationError):
            validate_uploaded_media(upload)

    def test_home_banner_full_clean_rejects_a_disguised_media_file(self):
        banner = HomeBanner(
            name="Banner de prueba",
            media_type=HomeBanner.MediaType.IMAGE,
            media_file=SimpleUploadedFile("banner.png", b"esto no es un png", content_type="image/png"),
        )
        with self.assertRaises(ValidationError):
            banner.full_clean()

    def test_home_banner_full_clean_accepts_a_genuine_image(self):
        banner = HomeBanner(
            name="Banner de prueba",
            media_type=HomeBanner.MediaType.IMAGE,
            media_file=SimpleUploadedFile("banner.png", _fake_image_bytes("PNG"), content_type="image/png"),
        )
        banner.full_clean()

    def test_marketing_popup_accepts_video_and_keeps_it_untouched(self):
        video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            popup = MarketingPopup(
                name="Popup con video", title="Lanzamiento", message="Mira el clip.",
                button_label="Ver", button_url="shop.html",
                image_file=SimpleUploadedFile("promo.mp4", video_bytes, content_type="video/mp4"),
            )
            popup.full_clean()
            popup.save()

            self.assertTrue(popup.is_video)
            # Un video no debe pasar por el optimizador de imagenes.
            self.assertTrue(popup.image_file.name.endswith(".mp4"))
            with popup.image_file.open("rb") as stored:
                self.assertEqual(stored.read(), video_bytes)

    def test_marketing_popup_renders_video_instead_of_image(self):
        video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            MarketingPopup.objects.all().delete()
            MarketingPopup.objects.create(
                name="Popup con video", title="Lanzamiento", message="Mira el clip.",
                button_label="Ver", button_url="shop.html", is_active=True,
                image_file=SimpleUploadedFile("promo.mp4", video_bytes, content_type="video/mp4"),
            )
            home = self.client.get("/")
            self.assertContains(home, "<video")
            self.assertContains(home, "promo.mp4")
            self.assertNotContains(home, 'img src="/media/marketing/popups/promo.mp4"')

    def test_marketing_popup_image_is_still_converted_to_webp(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            popup = MarketingPopup.objects.create(
                name="Popup con imagen", title="Oferta", message="Mensaje.",
                button_label="Ver", button_url="shop.html",
                image_file=SimpleUploadedFile("Portada.png", _fake_image_bytes("PNG", size=(2000, 2000)), content_type="image/png"),
            )
            self.assertFalse(popup.is_video)
            self.assertTrue(popup.image_file.name.endswith("portada.webp"))
            with Image.open(popup.image_file.path) as optimized:
                self.assertEqual(optimized.format, "WEBP")
                self.assertLessEqual(optimized.width, 1400)

    def test_marketing_popup_full_clean_rejects_a_disguised_image_file(self):
        popup = MarketingPopup(
            name="Popup de prueba", title="Oferta", message="Mensaje de prueba.",
            button_label="Comprar", button_url="shop.html",
            image_file=SimpleUploadedFile("popup.webp", b"esto no es un webp", content_type="image/webp"),
        )
        with self.assertRaises(ValidationError):
            popup.full_clean()

    def test_product_uploads_are_resized_and_converted_to_webp(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            product = Product.objects.first()
            product.image_file = SimpleUploadedFile(
                "Producto Principal.png",
                _fake_image_bytes("PNG", size=(2200, 1800)),
                content_type="image/png",
            )
            product.save()

            gallery_image = ProductImage.objects.create(
                product=product,
                image_file=SimpleUploadedFile(
                    "Vista Lateral.jpg",
                    _fake_image_bytes("JPEG", size=(1800, 2100)),
                    content_type="image/jpeg",
                ),
                image_alt="Vista lateral",
            )

            self.assertTrue(product.image_file.name.endswith("producto-principal.webp"))
            self.assertTrue(gallery_image.image_file.name.endswith("vista-lateral.webp"))
            with Image.open(product.image_file.path) as optimized:
                self.assertEqual(optimized.format, "WEBP")
                self.assertLessEqual(optimized.width, 1600)
                self.assertLessEqual(optimized.height, 1600)
            with Image.open(gallery_image.image_file.path) as optimized:
                self.assertEqual(optimized.format, "WEBP")
                self.assertLessEqual(optimized.width, 1600)
                self.assertLessEqual(optimized.height, 1600)
            self.assertEqual(product.main_image_source, product.image_file.url)
            self.assertIn(gallery_image.image_file.url, [item["url"] for item in product.product_images])

    def test_image_banner_is_converted_but_video_is_not_modified(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            banner = HomeBanner.objects.create(
                name="Banner optimizado",
                media_type=HomeBanner.MediaType.IMAGE,
                media_file=SimpleUploadedFile(
                    "Portada.png",
                    _fake_image_bytes("PNG", size=(2800, 1800)),
                    content_type="image/png",
                ),
            )
            video_bytes = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 20
            video = HomeBanner.objects.create(
                name="Video intacto",
                media_type=HomeBanner.MediaType.VIDEO,
                media_file=SimpleUploadedFile("portada.mp4", video_bytes, content_type="video/mp4"),
            )

            self.assertTrue(banner.media_file.name.endswith("portada.webp"))
            with Image.open(banner.media_file.path) as optimized:
                self.assertEqual(optimized.format, "WEBP")
                self.assertLessEqual(optimized.width, 2400)
                self.assertLessEqual(optimized.height, 1400)
            self.assertTrue(video.media_file.name.endswith("portada.mp4"))
            with video.media_file.open("rb") as uploaded_video:
                self.assertEqual(uploaded_video.read(), video_bytes)


@override_settings(AXES_ENABLED=True, AXES_FAILURE_LIMIT=3, AXES_COOLOFF_TIME=timedelta(minutes=15))
class LoginLockoutTests(TestCase):
    """django-axes: bloqueo tras contraseñas incorrectas repetidas.

    AXES_ENABLED se apaga durante `manage.py test` (ver settings.py); estas
    pruebas lo reactivan explícitamente. Con el límite en 3, las primeras 2
    fallas se tratan como un intento normal y la 3ª en adelante queda
    bloqueada — confirmado empíricamente contra el backend real de axes.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="frecuente", password="ClaveSegura123!")

    def _fail_login(self, username="frecuente"):
        return self.client.post("/account-login.html", {"username": username, "password": "clave-incorrecta"})

    def test_allows_up_to_the_limit_minus_one_failures_normally(self):
        first = self._fail_login()
        second = self._fail_login()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotContains(first, "Demasiados intentos fallidos")
        self.assertNotContains(second, "Demasiados intentos fallidos")

    def test_locks_out_after_reaching_the_failure_limit(self):
        self._fail_login()
        self._fail_login()
        third = self._fail_login()

        self.assertEqual(third.status_code, 429)
        self.assertContains(third, "Demasiados intentos fallidos", status_code=429)

    def test_lockout_blocks_even_the_correct_password(self):
        self._fail_login()
        self._fail_login()
        self._fail_login()

        response = self.client.post("/account-login.html", {"username": "frecuente", "password": "ClaveSegura123!"})

        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "Demasiados intentos fallidos", status_code=429)

    def test_lockout_is_scoped_to_the_username_not_the_whole_ip(self):
        """Un atacante fallando contra 'frecuente' no debe bloquear a otro usuario en la misma IP."""
        other = User.objects.create_user(username="vecino", password="OtraClaveSegura123!")
        self._fail_login()
        self._fail_login()
        self._fail_login()

        response = self.client.post("/account-login.html", {"username": other.username, "password": "OtraClaveSegura123!"})

        self.assertRedirects(response, "/account.html")

    def test_successful_login_resets_the_failure_count(self):
        self._fail_login()
        self._fail_login()

        ok = self.client.post("/account-login.html", {"username": "frecuente", "password": "ClaveSegura123!"})
        self.assertRedirects(ok, "/account.html")
        self.client.logout()

        # Tras el éxito, el contador se reinicia: dos fallas más no bloquean.
        first_again = self._fail_login()
        second_again = self._fail_login()
        self.assertEqual(first_again.status_code, 200)
        self.assertEqual(second_again.status_code, 200)

    def test_registration_still_works_with_two_authentication_backends(self):
        """login() tras registrarse debe indicar el backend explícitamente (ver register_view)."""
        response = self.client.post("/account-register.html", {
            "first_name": "Nueva", "last_name": "Cuenta", "username": "cuenta-nueva",
            "email": "nueva@example.com", "password1": "ClaveSegura123!", "password2": "ClaveSegura123!",
        })
        self.assertRedirects(response, "/account.html")


@override_settings(
    BOLD_IDENTITY_KEY="llave-identidad-pruebas",
    BOLD_SECRET_KEY="llave-secreta-pruebas",
    BOLD_TEST_MODE=False,
    BOLD_PUBLIC_BASE_URL="",
)
class BoldPaymentTests(TestCase):
    """Cobro en linea con la pasarela Bold."""

    def setUp(self):
        self.product = Product.objects.first()
        self.user = User.objects.create_user(username="pagador", email="pagador@example.com", password="ClaveSegura123!")
        self.address = Address.objects.create(
            user=self.user, first_name="Juan", last_name="Correa", address_line_1="Cra 5 # 12-34",
            department="Huila", city="Neiva", phone="300 555 4433", is_default=True,
        )
        self.client.force_login(self.user)

    def _place_bold_order(self, quantity=1):
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=quantity, size="40")
        response = self.client.post("/shop-checkout.html", {
            "address": self.address.id,
            "payment_method": Order.PaymentMethod.BOLD,
            "accept_terms": "on",
        })
        return response, Order.objects.get(user=self.user)

    def _webhook_request(self, event, secret="llave-secreta-pruebas"):
        body = json.dumps(event).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), base64.b64encode(body), hashlib.sha256).hexdigest()
        return self.client.post(
            "/pago/bold/webhook/",
            data=body,
            content_type="application/json",
            headers={"x-bold-signature": signature},
        )

    def test_integrity_signature_concatenates_reference_amount_currency_and_secret(self):
        expected = hashlib.sha256(b"inv033439400COPllave-secreta-pruebas").hexdigest()
        self.assertEqual(bold.integrity_signature("inv0334", 39400, "COP"), expected)

    def test_amount_drops_decimals(self):
        self.assertEqual(bold.amount_for(Decimal("241000.00")), 241000)
        self.assertEqual(bold.amount_for(Decimal("1999.60")), 2000)

    def test_checkout_with_bold_sends_the_buyer_to_the_payment_page(self):
        response, order = self._place_bold_order()
        self.assertRedirects(response, f"/pago/{order.number}/")
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_method, Order.PaymentMethod.BOLD)

    def test_payment_page_publishes_the_signed_configuration(self):
        _, order = self._place_bold_order()
        page = self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        amount = bold.amount_for(order.total)
        self.assertEqual(order.payment_reference, f"{order.number}-1")
        self.assertContains(page, "llave-identidad-pruebas")
        self.assertContains(page, bold.integrity_signature(order.payment_reference, amount))
        self.assertContains(page, "boldPaymentButton.js")
        # Sin dominio HTTPS publico no se envia retorno automatico a Bold.
        self.assertNotContains(page, "redirectionUrl")
        self.assertNotContains(page, "llave-secreta-pruebas")

    def test_payment_page_sends_https_return_url_when_public_domain_is_set(self):
        _, order = self._place_bold_order()
        with override_settings(BOLD_PUBLIC_BASE_URL="https://tienda.example.com"):
            page = self.client.get(f"/pago/{order.number}/")
        self.assertContains(page, "https://tienda.example.com/pago/bold/retorno/")

    def test_rejected_payment_gets_a_new_reference_on_retry(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        first_reference = order.payment_reference

        apply_payment_status(order, bold.STATUS_REJECTED, transaction_id="TX-1")
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()

        self.assertEqual(first_reference, f"{order.number}-1")
        self.assertEqual(order.payment_reference, f"{order.number}-2")
        self.assertEqual(order.payment_status, "")
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_processing_payment_keeps_the_same_reference(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        apply_payment_status(order, bold.STATUS_PROCESSING)
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        self.assertEqual(order.payment_reference, f"{order.number}-1")

    def test_manual_check_marks_the_order_as_paid(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()

        voucher = {"payment_status": "APPROVED", "transaction_id": "TX-APROBADA", "reference_id": order.payment_reference}
        with patch("store.bold.fetch_payment_status", return_value=voucher) as fetch:
            response = self.client.post(f"/pago/{order.number}/verificar/", follow=True)

        fetch.assert_called_once_with(order.payment_reference)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_status, Order.PaymentStatus.APPROVED)
        self.assertEqual(order.payment_transaction_id, "TX-APROBADA")
        self.assertIsNotNone(order.paid_at)
        self.assertContains(response, "Pago aprobado")

    def test_manual_check_keeps_the_order_pending_when_bold_rejects(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()

        with patch("store.bold.fetch_payment_status", return_value={"payment_status": "REJECTED"}):
            response = self.client.post(f"/pago/{order.number}/verificar/")

        order.refresh_from_db()
        self.assertRedirects(response, f"/pago/{order.number}/", fetch_redirect_response=False)
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.REJECTED)

    def test_manual_check_reports_a_gateway_failure_without_touching_the_order(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")

        with patch("store.bold.fetch_payment_status", side_effect=bold.BoldRequestError("Bold no responde.")):
            response = self.client.post(f"/pago/{order.number}/verificar/", follow=True)

        order.refresh_from_db()
        self.assertEqual(response.redirect_chain[-1][0], f"/pago/{order.number}/")
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, "")
        self.assertContains(response, "Bold no responde.")

    def test_status_endpoint_reports_approved_and_records_it(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()

        with patch("store.bold.fetch_payment_status", return_value={"payment_status": "APPROVED", "transaction_id": "TX-POLL"}):
            response = self.client.get(f"/pago/{order.number}/estado/")

        self.assertEqual(response.json(), {"outcome": "resolved", "redirect": f"/order-confirmation/{order.number}/"})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_status_endpoint_reports_rejected_without_redirecting(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")

        with patch("store.bold.fetch_payment_status", return_value={"payment_status": "REJECTED"}):
            response = self.client.get(f"/pago/{order.number}/estado/")

        self.assertEqual(response.json(), {"outcome": "rejected"})

    def test_status_endpoint_reports_pending_while_bold_has_nothing_yet(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")

        with patch("store.bold.fetch_payment_status", return_value={"payment_status": "NO_TRANSACTION_FOUND"}):
            response = self.client.get(f"/pago/{order.number}/estado/")

        self.assertEqual(response.json(), {"outcome": "pending"})

    def test_status_endpoint_reports_pending_on_gateway_hiccup_instead_of_erroring(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")

        with patch("store.bold.fetch_payment_status", side_effect=bold.BoldRequestError("Bold no responde.")):
            response = self.client.get(f"/pago/{order.number}/estado/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"outcome": "pending"})

    def test_status_endpoint_short_circuits_once_already_resolved(self):
        _, order = self._place_bold_order()
        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-YA-PAGADA")

        with patch("store.bold.fetch_payment_status") as fetch:
            response = self.client.get(f"/pago/{order.number}/estado/")

        fetch.assert_not_called()
        self.assertEqual(response.json(), {"outcome": "resolved", "redirect": f"/order-confirmation/{order.number}/"})

    def test_status_endpoint_is_private_to_its_owner(self):
        _, order = self._place_bold_order()
        other = User.objects.create_user(username="curioso-estado", password="ClaveSegura123!")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/pago/{order.number}/estado/").status_code, 404)

    def test_return_url_confirms_the_payment_against_the_api(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()

        voucher = {"payment_status": "APPROVED", "transaction_id": "TX-RETORNO"}
        with patch("store.bold.fetch_payment_status", return_value=voucher):
            response = self.client.get("/pago/bold/retorno/", {
                "bold-order-id": order.payment_reference,
                "bold-tx-status": "approved",
            })

        self.assertRedirects(response, f"/order-confirmation/{order.number}/")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    def test_return_url_ignores_a_status_that_bold_does_not_confirm(self):
        """La URL de retorno es manipulable: el estado siempre se consulta en la API."""
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()

        with patch("store.bold.fetch_payment_status", return_value={"payment_status": "REJECTED"}):
            self.client.get("/pago/bold/retorno/", {
                "bold-order-id": order.payment_reference,
                "bold-tx-status": "approved",
            })

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.payment_status, Order.PaymentStatus.REJECTED)

    def test_webhook_approves_the_order_and_is_idempotent(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        event = {
            "id": "b8f0c1e4",
            "type": "SALE_APPROVED",
            "subject": "TX-WEBHOOK",
            "data": {"payment_id": "TX-WEBHOOK", "metadata": {"reference": order.payment_reference}},
        }

        first = self._webhook_request(event)
        order.refresh_from_db()
        paid_at = order.paid_at
        second = self._webhook_request(event)
        order.refresh_from_db()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.payment_transaction_id, "TX-WEBHOOK")
        self.assertEqual(order.paid_at, paid_at)

    def test_webhook_rejects_an_invalid_signature(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        event = {"type": "SALE_APPROVED", "data": {"metadata": {"reference": order.payment_reference}}}

        response = self._webhook_request(event, secret="llave-que-no-es-la-nuestra")

        self.assertEqual(response.status_code, 401)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_webhook_void_cancels_the_order_and_returns_the_stock(self):
        stock_before = self.product.stock
        _, order = self._place_bold_order(quantity=2)
        order_item = order.items.select_related("variant").get()
        selected_variant = order_item.variant
        selected_variant_stock_before = selected_variant.stock
        sibling_variant = self.product.variants.exclude(pk=selected_variant.pk).first()
        sibling_variant_stock_before = sibling_variant.stock
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        self.product.refresh_from_db()
        # Crear el pedido no toca el inventario: aún no hay pago.
        self.assertEqual(self.product.stock, stock_before)

        self._webhook_request({
            "type": "SALE_APPROVED",
            "subject": "TX-ANULABLE",
            "data": {"metadata": {"reference": order.payment_reference}},
        })
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, stock_before - 2)
        selected_variant.refresh_from_db()
        sibling_variant.refresh_from_db()
        self.assertEqual(selected_variant.stock, selected_variant_stock_before - 2)
        self.assertEqual(sibling_variant.stock, sibling_variant_stock_before)

        self._webhook_request({
            "type": "VOID_APPROVED",
            "subject": "TX-ANULABLE",
            "data": {"metadata": {"reference": order.payment_reference}},
        })

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertEqual(order.payment_status, Order.PaymentStatus.VOIDED)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(self.product.stock, stock_before)
        selected_variant.refresh_from_db()
        sibling_variant.refresh_from_db()
        self.assertEqual(selected_variant.stock, selected_variant_stock_before)
        self.assertEqual(sibling_variant.stock, sibling_variant_stock_before)

    def test_webhook_accepts_events_without_effect(self):
        response = self._webhook_request({"type": "VOID_REJECTED", "data": {"metadata": {"reference": "JS-0000-1"}}})
        self.assertEqual(response.status_code, 200)

    @override_settings(BOLD_ALLOW_UNSIGNED_WEBHOOKS=True)
    def test_sandbox_flag_accepts_the_empty_key_signature(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        event = {"type": "SALE_APPROVED", "subject": "TX-SANDBOX", "data": {"metadata": {"reference": order.payment_reference}}}

        response = self._webhook_request(event, secret="")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

    @override_settings(BOLD_TEST_MODE=True, BOLD_ALLOW_UNSIGNED_WEBHOOKS=False)
    def test_test_mode_alone_does_not_accept_an_unsigned_webhook(self):
        """El aviso de pruebas no debe abrir la puerta a marcar pedidos como pagados."""
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        event = {"type": "SALE_APPROVED", "subject": "TX-FORJADA", "data": {"metadata": {"reference": order.payment_reference}}}

        response = self._webhook_request(event, secret="")

        self.assertEqual(response.status_code, 401)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertFalse(order.stock_reserved)

    @override_settings(BOLD_SECRET_KEY="", BOLD_ALLOW_UNSIGNED_WEBHOOKS=False)
    def test_webhook_signature_is_never_valid_without_a_secret(self):
        self.assertFalse(bold.verify_webhook_signature(b"{}", hmac.new(b"", base64.b64encode(b"{}"), hashlib.sha256).hexdigest()))

    @override_settings(BOLD_IDENTITY_KEY="", BOLD_SECRET_KEY="")
    def test_checkout_hides_bold_when_the_gateway_is_not_configured(self):
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")
        page = self.client.get("/shop-checkout.html")
        self.assertNotContains(page, 'value="bold"')
        self.assertContains(page, 'value="bank_transfer"')

    def test_paid_order_cannot_be_paid_again(self):
        _, order = self._place_bold_order()
        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-YA-PAGADA")
        response = self.client.get(f"/pago/{order.number}/", follow=True)
        self.assertRedirects(response, f"/order-confirmation/{order.number}/")
        self.assertContains(response, "ya no est")

    def test_payment_page_is_private_to_its_owner(self):
        _, order = self._place_bold_order()
        other = User.objects.create_user(username="curioso", password="ClaveSegura123!")
        self.client.force_login(other)
        self.assertEqual(self.client.get(f"/pago/{order.number}/").status_code, 404)


    def _urlopen_response(self, body):
        response = MagicMock()
        response.read.return_value = json.dumps(body).encode("utf-8")
        response.__enter__ = lambda self_: self_
        response.__exit__ = lambda *args: False
        return response

    def _http_error(self, code, body):
        return HTTPError("https://payments.api.bold.co", code, "error", {}, io.BytesIO(body.encode("utf-8")))

    def test_voucher_query_unwraps_the_payload_envelope(self):
        body = {"payload": {"payment_status": "APPROVED", "transaction_id": "TX-9", "total": 235000}, "errors": []}
        with patch("store.bold.urlopen", return_value=self._urlopen_response(body)) as opener:
            voucher = bold.fetch_payment_status("JS-1-1")

        sent = opener.call_args.args[0]
        self.assertEqual(sent.full_url, "https://payments.api.bold.co/v2/payment-voucher/JS-1-1")
        self.assertEqual(sent.get_header("Authorization"), "x-api-key llave-identidad-pruebas")
        self.assertEqual(voucher["payment_status"], "APPROVED")
        self.assertEqual(voucher["transaction_id"], "TX-9")

    def test_voucher_query_reports_no_transaction_when_bold_has_no_payment_yet(self):
        # Bold responde 400 con un error de validaciÃ³n mientras nadie ha pagado.
        error = self._http_error(400, '{"payload": {}, "errors": [{"message": "1 validation error"}]}')
        with patch("store.bold.urlopen", side_effect=error):
            voucher = bold.fetch_payment_status("JS-1-1")
        self.assertEqual(voucher["payment_status"], bold.STATUS_NO_TRANSACTION)

    def test_voucher_query_raises_when_bold_rejects_the_key(self):
        with patch("store.bold.urlopen", side_effect=self._http_error(401, '{"errors": ["unauthorized"]}')):
            with self.assertRaises(bold.BoldRequestError):
                bold.fetch_payment_status("JS-1-1")

    def test_voucher_query_raises_on_network_failure(self):
        with patch("store.bold.urlopen", side_effect=URLError("timeout")):
            with self.assertRaises(bold.BoldRequestError):
                bold.fetch_payment_status("JS-1-1")


    def test_bold_is_the_preselected_payment_method(self):
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")
        page = self.client.get("/shop-checkout.html")
        self.assertContains(page, '<input type="radio" name="payment_method" value="bold" checked>', html=False)
        self.assertNotContains(page, '<input type="radio" name="payment_method" value="bank_transfer" checked>')

    @override_settings(BOLD_IDENTITY_KEY="", BOLD_SECRET_KEY="")
    def test_bank_transfer_is_preselected_without_the_gateway(self):
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")
        page = self.client.get("/shop-checkout.html")
        self.assertContains(page, '<input type="radio" name="payment_method" value="bank_transfer" checked>')

    def test_checkout_keeps_the_chosen_method_when_the_form_has_errors(self):
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")
        # Sin aceptar los tÃ©rminos el formulario se vuelve a mostrar.
        page = self.client.post("/shop-checkout.html", {
            "address": self.address.id,
            "payment_method": Order.PaymentMethod.BANK_TRANSFER,
        })
        self.assertContains(page, '<input type="radio" name="payment_method" value="bank_transfer" checked>')
        self.assertFalse(Order.objects.filter(user=self.user).exists())

    def test_pickup_order_also_goes_through_the_gateway(self):
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")
        response = self.client.post("/shop-checkout.html", {
            "delivery_method": "pickup",
            "payment_method": Order.PaymentMethod.BOLD,
            "accept_terms": "on",
        })
        order = Order.objects.get(user=self.user)
        self.assertRedirects(response, f"/pago/{order.number}/", fetch_redirect_response=False)
        self.assertEqual(order.delivery_method, Order.DeliveryMethod.PICKUP)
        self.assertEqual(order.shipping_cost, Decimal("0"))
        self.assertEqual(order.total, self.product.price)


    def test_cart_survives_an_unpaid_bold_order(self):
        """Si el cliente se devuelve sin pagar, su carrito sigue completo."""
        stock_before = self.product.stock
        _, order = self._place_bold_order(quantity=2)

        cart = Cart.objects.get(user=self.user, status=Cart.Status.ACTIVE)
        self.product.refresh_from_db()
        self.assertEqual(cart.items.count(), 1)
        self.assertEqual(cart.item_count, 2)
        self.assertEqual(self.product.stock, stock_before)
        self.assertFalse(order.stock_reserved)

        # El resumen del carrito que ve el cliente sigue mostrando el producto.
        payload = self.client.get("/api/cart/").json()
        self.assertEqual(payload["count"], 2)

    def test_approved_payment_consumes_the_cart_and_the_stock(self):
        stock_before = self.product.stock
        _, order = self._place_bold_order(quantity=2)
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()

        with patch("store.bold.fetch_payment_status", return_value={"payment_status": "APPROVED", "transaction_id": "TX-OK"}):
            self.client.post(f"/pago/{order.number}/verificar/")

        order.refresh_from_db()
        self.product.refresh_from_db()
        cart = Cart.objects.get(user=self.user)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertTrue(order.stock_reserved)
        self.assertEqual(self.product.stock, stock_before - 2)
        self.assertEqual(cart.status, Cart.Status.CONVERTED)
        self.assertEqual(cart.items.count(), 0)

    def test_coupon_is_only_redeemed_once_the_payment_is_approved(self):
        coupon = Coupon.objects.create(
            code="BOLD15", discount_type=Coupon.DiscountType.PERCENTAGE, value=15,
            minimum_purchase=1000, starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=1), once_per_user=True,
        )
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")
        self.client.post("/cart-coupon/apply/", {"code": "BOLD15"})
        self.client.post("/shop-checkout.html", {
            "address": self.address.id,
            "payment_method": Order.PaymentMethod.BOLD,
            "accept_terms": "on",
        })
        order = Order.objects.get(user=self.user)

        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 0)
        self.assertFalse(CouponRedemption.objects.filter(order=order).exists())

        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        with patch("store.bold.fetch_payment_status", return_value={"payment_status": "APPROVED"}):
            self.client.post(f"/pago/{order.number}/verificar/")

        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 1)
        self.assertTrue(CouponRedemption.objects.filter(order=order).exists())

    def test_pending_online_payment_reserves_the_last_coupon_use(self):
        coupon = Coupon.objects.create(
            code="ULTIMO-USO",
            discount_type=Coupon.DiscountType.FIXED,
            value=5000,
            minimum_purchase=1000,
            starts_at=timezone.now() - timedelta(days=1),
            expires_at=timezone.now() + timedelta(days=1),
            usage_limit=1,
            once_per_user=False,
        )
        first_cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=first_cart, product=self.product, quantity=1, size="40")
        self.client.post("/cart-coupon/apply/", {"code": coupon.code})
        first_response = self.client.post("/shop-checkout.html", {
            "address": self.address.id,
            "payment_method": Order.PaymentMethod.BOLD,
            "accept_terms": "on",
        })
        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(Order.objects.filter(coupon=coupon, status=Order.Status.PENDING).count(), 1)

        second_user = User.objects.create_user(
            username="segundo-pagador",
            email="segundo-pagador@example.com",
            password="ClaveSegura123!",
        )
        second_address = Address.objects.create(
            user=second_user,
            first_name="Ana",
            last_name="Rojas",
            address_line_1="Calle 8 # 10-20",
            department="Huila",
            city="Neiva",
            phone="300 111 2233",
            is_default=True,
        )
        self.client.force_login(second_user)
        second_cart = Cart.objects.create(user=second_user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=second_cart, product=self.product, quantity=1, size="40")
        self.client.post("/cart-coupon/apply/", {"code": coupon.code})
        second_response = self.client.post("/shop-checkout.html", {
            "address": second_address.id,
            "payment_method": Order.PaymentMethod.BOLD,
            "accept_terms": "on",
        }, follow=True)

        self.assertContains(second_response, "El cupon alcanzo su limite de usos.")
        self.assertEqual(Order.objects.filter(coupon=coupon).count(), 1)
        coupon.refresh_from_db()
        self.assertEqual(coupon.times_used, 0)

    def test_confirming_the_same_cart_twice_reuses_the_pending_order(self):
        _, first = self._place_bold_order()
        response = self.client.post("/shop-checkout.html", {
            "address": self.address.id,
            "payment_method": Order.PaymentMethod.BOLD,
            "accept_terms": "on",
        })

        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertRedirects(response, f"/pago/{first.number}/", fetch_redirect_response=False)

    def test_a_different_cart_creates_its_own_pending_order(self):
        _, first = self._place_bold_order()
        other = Product.objects.exclude(pk=self.product.pk).filter(is_active=True, stock__gt=0).first()
        cart = Cart.objects.get(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=other, quantity=1, size="41")

        self.client.post("/shop-checkout.html", {
            "address": self.address.id,
            "payment_method": Order.PaymentMethod.BOLD,
            "accept_terms": "on",
        })

        self.assertEqual(Order.objects.filter(user=self.user).count(), 2)

    def test_payment_page_opens_the_gateway_on_a_fresh_arrival_only(self):
        _, order = self._place_bold_order()
        page = self.client.get(f"/pago/{order.number}/")
        body = page.content.decode()
        # La apertura automática se condiciona al tipo de navegación para que
        # volver atrás desde Bold no reabra la pasarela en bucle.
        self.assertIn("checkout.open();", body)
        self.assertIn("entries[0].type === 'navigate'", body)
        self.assertIn("if (!isFreshArrival())", body)

    def test_payment_page_is_a_redirect_screen_without_the_order_summary(self):
        """El resumen ya se vio en el checkout: aquí solo se anuncia la redirección."""
        _, order = self._place_bold_order()
        page = self.client.get(f"/pago/{order.number}/")

        self.assertContains(page, "payment-redirect__spinner")
        self.assertContains(page, "Te estamos llevando a Bold")
        self.assertContains(page, f"Pedido {order.number}")
        # Sin tabla de artículos ni bloque de envío duplicados.
        self.assertNotContains(page, "Artículos del pedido")
        self.assertNotContains(page, "order-summary-card")

    def test_payment_page_keeps_a_way_out_if_the_redirect_never_happens(self):
        """Recarga, bloqueo del navegador o caída de Bold: siempre queda un botón."""
        _, order = self._place_bold_order()
        body = self.client.get(f"/pago/{order.number}/").content.decode()

        self.assertIn("Tu pedido espera el pago", body)
        self.assertIn("La pasarela no se abrió sola", body)
        self.assertIn("Bold no está disponible", body)
        self.assertIn("data-redirect-actions hidden", body)
        self.assertIn(f'action="/pago/{order.number}/verificar/"', body)

    def test_offline_payment_still_consumes_the_cart_immediately(self):
        """La transferencia no pasa por pasarela: se confirma al instante como antes."""
        stock_before = self.product.stock
        cart = Cart.objects.create(user=self.user, status=Cart.Status.ACTIVE)
        CartItem.objects.create(cart=cart, product=self.product, quantity=1, size="40")

        self.client.post("/shop-checkout.html", {
            "address": self.address.id,
            "payment_method": Order.PaymentMethod.BANK_TRANSFER,
            "accept_terms": "on",
        })

        order = Order.objects.get(user=self.user)
        cart.refresh_from_db()
        self.product.refresh_from_db()
        self.assertTrue(order.stock_reserved)
        self.assertEqual(self.product.stock, stock_before - 1)
        self.assertEqual(cart.status, Cart.Status.CONVERTED)
        self.assertEqual(cart.items.count(), 0)

    def test_confirmation_announces_the_successful_payment_with_its_receipt_data(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-EXITO")
        order.refresh_from_db()

        page = self.client.get(f"/order-confirmation/{order.number}/")

        self.assertEqual(order.payment_state, "approved")
        self.assertContains(page, "payment-result--approved")
        self.assertContains(page, "¡Pago exitoso!")
        self.assertContains(page, "TX-EXITO")
        self.assertContains(page, order.payment_reference)
        self.assertContains(page, "Fecha del pago")
        # Solo una venta pagada ofrece comprobante y enlace al detalle del panel.
        self.assertContains(page, f"/orders/{order.number}/comprobante.pdf")
        self.assertContains(page, f'href="/orders/{order.number}/"')
        self.assertNotContains(page, "Completar el pago")

    def test_confirmation_of_an_unpaid_order_invites_to_finish_the_payment(self):
        _, order = self._place_bold_order()

        page = self.client.get(f"/order-confirmation/{order.number}/")

        self.assertContains(page, "payment-result--awaiting")
        self.assertContains(page, "Completar el pago")
        self.assertContains(page, f'href="/pago/{order.number}/"')
        self.assertNotContains(page, "¡Pago exitoso!")
        self.assertNotContains(page, "comprobante.pdf")

    def test_confirmation_of_a_rejected_payment_offers_a_retry(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        apply_payment_status(order, bold.STATUS_REJECTED)

        page = self.client.get(f"/order-confirmation/{order.number}/")

        self.assertContains(page, "payment-result--rejected")
        self.assertContains(page, "El pago no se completó")
        self.assertContains(page, "Reintentar el pago")

    def test_account_panel_links_the_paid_order_to_its_detail_view(self):
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-PANEL")

        panel = self.client.get("/account.html?tab=orders")
        detail = self.client.get(f"/orders/{order.number}/")

        self.assertContains(panel, f'href="/orders/{order.number}/"')
        self.assertNotContains(panel, "Completar pago")
        self.assertContains(detail, "payment-result--approved")
        self.assertContains(detail, "¡Pago exitoso!")
        self.assertContains(detail, "TX-PANEL")
        self.assertContains(detail, f"/orders/{order.number}/comprobante.pdf")

    def test_account_panel_offers_to_finish_a_pending_gateway_payment(self):
        _, order = self._place_bold_order()

        panel = self.client.get("/account.html?tab=orders")

        self.assertContains(panel, f'href="/pago/{order.number}/"')
        self.assertContains(panel, "Completar pago")

    def test_admin_sales_expose_customer_shipping_and_product_images(self):
        CustomerProfile.objects.create(user=self.user, document_number="1075998877", phone="3005554433")
        _, order = self._place_bold_order()
        self.client.get(f"/pago/{order.number}/")
        order.refresh_from_db()
        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-ADMIN")

        staff = User.objects.create_superuser(username="admin-ventas", email="ventas@example.com", password="ClaveSegura123!")
        self.client.force_login(staff)
        sales = self.client.get("/panel-admin/?section=sales")

        self.assertContains(sales, f'data-detail-toggle="order-info-{order.id}"')
        # Cliente
        self.assertContains(sales, "pagador@example.com")
        self.assertContains(sales, "1075998877")
        # Datos de envio del pedido (no de la libreta de direcciones)
        self.assertContains(sales, "Cra 5 # 12-34")
        self.assertContains(sales, "Neiva, Huila")
        self.assertContains(sales, "300 555 4433")
        # Imagen y variante de cada articulo vendido, y trazas del cobro
        self.assertContains(sales, self.product.image)
        self.assertContains(sales, "Talla 40")
        self.assertContains(sales, "TX-ADMIN")
        self.assertContains(sales, order.payment_reference)


class OrderOperationsTests(TestCase):
    def setUp(self):
        self.product = Product.objects.filter(is_active=True, variants__isnull=False).distinct().first()
        self.variant = self.product.variants.first()
        self.variant.stock = 20
        self.variant.save(update_fields=("stock", "updated_at"))
        self.user = User.objects.create_user(
            username="operaciones-pedidos",
            email="cliente-operaciones@example.com",
            password="ClaveSegura123!",
        )
        self.staff = User.objects.create_superuser(
            username="admin-operaciones",
            email="admin-operaciones@example.com",
            password="ClaveSegura123!",
        )

    def make_order(self, *, number="JS-OPS-0001", quantity=2, delivery_method=Order.DeliveryMethod.COURIER):
        order = Order.objects.create(
            user=self.user,
            number=number,
            recipient_name="Cliente Operaciones",
            phone="3001234567",
            address_line_1="Calle 10 # 20-30",
            department="Huila",
            city="Neiva",
            subtotal=self.product.price * quantity,
            total=self.product.price * quantity,
            payment_method=Order.PaymentMethod.BOLD,
            delivery_method=delivery_method,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            variant=self.variant,
            variant_sku=self.variant.sku or "",
            product_name=self.product.name,
            product_image=self.product.image,
            unit_price=self.product.price,
            quantity=quantity,
            size=self.variant.size,
            color=self.variant.color_name,
        )
        OrderStatusHistory.objects.create(
            order=order,
            from_status="",
            to_status=Order.Status.PENDING,
            source=OrderStatusHistory.Source.SYSTEM,
            note="Pedido creado correctamente.",
        )
        return order

    def test_controlled_transitions_capture_actor_logistics_and_dates(self):
        order = self.make_order()
        initial_variant_stock = self.variant.stock

        order, paid = transition_order(
            order,
            Order.Status.PAID,
            actor=self.staff,
            source=OrderStatusHistory.Source.ADMIN,
            notify=False,
        )
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, initial_variant_stock - 2)
        self.assertTrue(order.stock_reserved)
        self.assertIsNotNone(order.paid_at)
        self.assertEqual(paid.changed_by, self.staff)
        self.assertEqual(paid.from_status, Order.Status.PENDING)

        with self.assertRaises(OrderTransitionError):
            transition_order(order, Order.Status.SHIPPED, notify=False)

        order, preparing = transition_order(order, Order.Status.PREPARING, notify=False)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.PACKING)
        with self.assertRaisesMessage(OrderTransitionError, "transportadora"):
            transition_order(order, Order.Status.SHIPPED, notify=False)

        order.carrier = "Servientrega"
        order.tracking_number = "GUIA-987654"
        order.save(update_fields=("carrier", "tracking_number", "updated_at"))
        order, shipped = transition_order(order, Order.Status.SHIPPED, notify=False)
        self.assertIsNotNone(order.shipped_at)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.IN_TRANSIT)
        self.assertEqual(shipped.from_status, preparing.to_status)

        order, delivered = transition_order(order, Order.Status.DELIVERED, notify=False)
        self.assertIsNotNone(order.delivered_at)
        self.assertEqual(order.fulfillment_status, Order.FulfillmentStatus.DELIVERED)
        self.assertEqual(delivered.to_status, Order.Status.DELIVERED)

    def test_refund_restores_the_exact_variant_once(self):
        order = self.make_order(number="JS-OPS-0002")
        sibling = self.product.variants.exclude(pk=self.variant.pk).first()
        sibling_stock = sibling.stock if sibling else None
        initial_stock = self.variant.stock

        order, _ = transition_order(order, Order.Status.PAID, notify=False)
        order, _ = transition_order(order, Order.Status.PREPARING, notify=False)
        order, first_refund = transition_order(order, Order.Status.REFUNDED, notify=False)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, initial_stock)
        self.assertFalse(order.stock_reserved)
        self.assertEqual(first_refund.to_status, Order.Status.REFUNDED)

        order, duplicate_refund = transition_order(order, Order.Status.REFUNDED, notify=False)
        self.variant.refresh_from_db()
        self.assertIsNone(duplicate_refund)
        self.assertEqual(self.variant.stock, initial_stock)
        if sibling:
            sibling.refresh_from_db()
            self.assertEqual(sibling.stock, sibling_stock)
        self.assertEqual(order.status_history.filter(to_status=Order.Status.REFUNDED).count(), 1)

    def test_payment_retries_create_only_one_paid_transition_and_one_stock_change(self):
        order = self.make_order(number="JS-OPS-0003", quantity=1)
        initial_stock = self.variant.stock

        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-IDEMPOTENT")
        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-IDEMPOTENT")

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(self.variant.stock, initial_stock - 1)
        self.assertEqual(order.status_history.filter(to_status=Order.Status.PAID).count(), 1)

    def test_late_payment_events_do_not_regress_a_closed_order(self):
        order = self.make_order(number="JS-OPS-0007", quantity=1)
        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-CLOSED")
        order, _ = transition_order(order, Order.Status.REFUNDED, notify=False)
        order.payment_status = bold.STATUS_VOIDED
        order.save(update_fields=("payment_status", "updated_at"))
        restored_stock = self.variant.stock

        apply_payment_status(order, bold.STATUS_APPROVED, transaction_id="TX-LATE")

        order.refresh_from_db()
        self.variant.refresh_from_db()
        self.assertEqual(order.status, Order.Status.REFUNDED)
        self.assertEqual(order.payment_status, bold.STATUS_VOIDED)
        self.assertEqual(order.payment_transaction_id, "TX-CLOSED")
        self.assertEqual(self.variant.stock, restored_stock)

    def test_status_email_is_branded_contains_tracking_and_is_idempotent(self):
        order = self.make_order(number="JS-OPS-0004", quantity=1)
        order, _ = transition_order(order, Order.Status.PAID, notify=False)
        order, _ = transition_order(order, Order.Status.PREPARING, notify=False)
        order.carrier = "Coordinadora"
        order.tracking_number = "CO-123456"
        order.save(update_fields=("carrier", "tracking_number", "updated_at"))
        order, history = transition_order(order, Order.Status.SHIPPED, notify=False)

        self.assertTrue(send_order_status_email(history.pk, order_url=f"http://testserver/orders/{order.number}/"))
        self.assertFalse(send_order_status_email(history.pk, order_url=f"http://testserver/orders/{order.number}/"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn(order.number, message.subject)
        self.assertIn("Coordinadora", message.body)
        self.assertIn("CO-123456", message.body)
        html = message.alternatives[0].content
        self.assertIn("color-scheme", html)
        self.assertIn("cid:nexus-status-logo", html)
        self.assertIn("CO-123456", html)

    def test_dispatch_receipt_validation_rejects_disguised_and_large_files(self):
        validate_dispatch_receipt(SimpleUploadedFile("despacho.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"))
        with self.assertRaises(ValidationError):
            validate_dispatch_receipt(SimpleUploadedFile("despacho.jpg", b"<script>alert(1)</script>", content_type="image/jpeg"))
        with self.assertRaisesMessage(ValidationError, "5 MB"):
            validate_dispatch_receipt(SimpleUploadedFile("grande.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024), content_type="application/pdf"))

    def test_dispatch_receipt_is_optional_owner_protected_and_visible_in_tracking(self):
        order = self.make_order(number="JS-OPS-0005", quantity=1)
        order, _ = transition_order(order, Order.Status.PAID, notify=False)
        order, _ = transition_order(order, Order.Status.PREPARING, notify=False)
        order.carrier = "Inter Rapidisimo"
        order.tracking_number = "IR-778899"
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            order.dispatch_receipt = SimpleUploadedFile(
                "comprobante-despacho.pdf",
                b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF",
                content_type="application/pdf",
            )
            order.full_clean()
            order.save(update_fields=("carrier", "tracking_number", "dispatch_receipt", "updated_at"))
            order, history = transition_order(order, Order.Status.SHIPPED, notify=False)

            self.client.force_login(self.user)
            detail = self.client.get(f"/orders/{order.number}/")
            self.assertContains(detail, "Inter Rapidisimo")
            self.assertContains(detail, "IR-778899")
            self.assertContains(detail, f"/orders/{order.number}/comprobante-despacho/")
            self.assertContains(detail, "Historial del pedido")
            receipt = self.client.get(f"/orders/{order.number}/comprobante-despacho/")
            self.assertEqual(receipt.status_code, 200)
            self.assertEqual(receipt["Content-Type"], "application/pdf")
            receipt.close()

            other = User.objects.create_user(username="otro-cliente", password="ClaveSegura123!")
            self.client.force_login(other)
            self.assertEqual(self.client.get(f"/orders/{order.number}/comprobante-despacho/").status_code, 404)

            self.assertTrue(send_order_status_email(history.pk, order_url=f"http://testserver/orders/{order.number}/"))
            self.assertIn(f"/orders/{order.number}/comprobante-despacho/", mail.outbox[-1].body)

    def test_admin_exposes_logistics_and_keeps_commercial_history_read_only(self):
        order = self.make_order(number="JS-OPS-0006", quantity=1)
        order_admin = admin.site._registry[Order]
        self.assertIn("dispatch_receipt", str(order_admin.fieldsets))
        self.assertIn("carrier", str(order_admin.fieldsets))
        self.assertIn("tracking_number", str(order_admin.fieldsets))
        self.assertIn("status", order_admin.get_readonly_fields(None, order))
        self.assertIn("payment_method", order_admin.get_readonly_fields(None, order))
        self.assertIn("delivery_method", order_admin.get_readonly_fields(None, order))
        self.assertIn("subtotal", order_admin.get_readonly_fields(None, order))
        self.assertIn("mark_preparing", order_admin.actions)
        self.assertIn("mark_shipped", order_admin.actions)
        self.assertIn("cancel_or_refund", order_admin.actions)

        order.status = Order.Status.PAID
        self.assertIn("purchase_value", order_admin.get_readonly_fields(None, order))
        self.assertIn("sale_value", order_admin.get_readonly_fields(None, order))
