from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BlogCategory, BlogPost, Product, StoreSection


class SeoMetadataTests(TestCase):
    def test_home_has_canonical_social_metadata_and_website_schema(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, '<link rel="canonical" href="http://testserver/">', html=True)
        self.assertContains(response, 'property="og:locale" content="es_CO"')
        self.assertContains(response, 'name="twitter:card" content="summary_large_image"')
        self.assertContains(
            response,
            'property="og:image" content="http://testserver/assets/img/shop/nexus-logo-vertical.png?v=20260806-centered"',
        )
        self.assertContains(response, 'property="og:image:width" content="600"')
        self.assertContains(response, 'property="og:image:height" content="557"')
        self.assertContains(response, "Sneakers Top Quality y calzado premium en Colombia")
        self.assertNotContains(response, "sneakers originales")
        self.assertContains(response, '"@type": "WebSite"')
        self.assertNotContains(response, 'name="keywords"')
        self.assertNotContains(response, "codecarnival")

    def test_search_is_not_indexable(self):
        response = self.client.get(reverse("search"), {"q": "Jordan"})

        self.assertContains(response, 'name="robots" content="noindex, follow"')
        self.assertContains(response, f'<link rel="canonical" href="http://testserver{reverse("search")}">', html=True)

    def test_product_has_product_schema_and_stable_canonical(self):
        brand = StoreSection.objects.get(slug="nike")
        product = Product.objects.create(
            slug="air-jordan-1",
            sku="AJ1-001",
            brand=brand,
            name="Air Jordan 1",
            description="Sneaker clásico de cuero.",
            price=Decimal("799900"),
            image="/assets/img/shop/air-jordan-1.png",
            stock=3,
        )

        response = self.client.get(reverse("product_detail"), {"producto": product.slug})

        canonical = f'http://testserver{reverse("product_detail")}?producto={product.slug}'
        self.assertContains(response, f'<link rel="canonical" href="{canonical}">', html=True)
        self.assertContains(response, 'property="og:type" content="product"')
        self.assertContains(response, '"@type": "Product"')
        self.assertContains(response, '"priceCurrency": "COP"')
        self.assertContains(response, '"availability": "https://schema.org/InStock"')

    def test_blog_post_has_article_metadata(self):
        category = BlogCategory.objects.create(name="Guías", slug="guias")
        post = BlogPost.objects.create(
            category=category,
            title="Cómo elegir tus sneakers",
            slug="como-elegir-sneakers",
            summary="Consejos para elegir la talla y el estilo ideales.",
            content="Contenido",
            image="/assets/img/blog/guia.png",
            image_alt="Sneakers blancos",
            published_at=timezone.now(),
        )

        response = self.client.get(reverse("blog_detail", kwargs={"slug": post.slug}))

        self.assertContains(response, 'property="og:type" content="article"')
        self.assertContains(response, '"@type": "BlogPosting"')
        self.assertContains(response, f'http://testserver/blog/{post.slug}/')
