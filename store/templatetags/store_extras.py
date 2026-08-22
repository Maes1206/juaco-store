import json
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urljoin

from django import template
from django.conf import settings
from django.http import QueryDict
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.text import Truncator

register = template.Library()


SEO_SITE_NAME = "Nexus Luxury Footwear"
SEO_DEFAULT_DESCRIPTION = (
    "Compra sneakers Top Quality y calzado premium en Colombia. Descubre modelos "
    "para hombre y mujer, clásicos, lanzamientos y ofertas en Nexus Luxury Footwear."
)
SEO_DEFAULT_IMAGE = "/assets/img/shop/nexus-logo-vertical.png?v=20260806-centered"


def _absolute_url(request, value, site_url):
    if not value:
        value = SEO_DEFAULT_IMAGE
    if value.startswith(("http://", "https://")):
        return value
    path = "/" + value.lstrip("/")
    return urljoin(f"{site_url}/", path.lstrip("/")) if site_url else request.build_absolute_uri(path)


@register.inclusion_tag("store/_seo_meta.html", takes_context=True)
def seo_meta(
    context,
    title="",
    description="",
    image="",
    content_type="website",
    robots="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1",
    product=None,
    post=None,
):
    """Genera metadatos sociales, canonical y JSON-LD consistentes."""
    request = context["request"]
    site_url = getattr(settings, "PUBLIC_SITE_URL", "").rstrip("/")
    if not site_url:
        site_url = request.build_absolute_uri("/").rstrip("/")

    schema = None
    if product is not None:
        title = product.name
        description = product.description or product.detailed_description
        image = product.main_image_source
        content_type = "product"
        canonical_path = f"{reverse('product_detail')}?producto={quote(product.slug)}"
        availability = "https://schema.org/InStock" if product.stock > 0 else "https://schema.org/OutOfStock"
        schema = {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": product.name,
            "description": strip_tags(description or SEO_DEFAULT_DESCRIPTION),
            "image": [_absolute_url(request, item["url"], site_url) for item in product.product_images],
            "sku": product.reference,
            "brand": {"@type": "Brand", "name": product.brand.title},
            "offers": {
                "@type": "Offer",
                "url": urljoin(f"{site_url}/", canonical_path.lstrip("/")),
                "priceCurrency": "COP",
                "price": str(product.price),
                "availability": availability,
                "itemCondition": "https://schema.org/NewCondition",
            },
        }
    elif post is not None:
        title = post.title
        description = post.summary
        image = post.image
        content_type = "article"
        canonical_path = reverse("blog_detail", kwargs={"slug": post.slug})
        schema = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": post.title,
            "description": strip_tags(post.summary),
            "image": _absolute_url(request, post.image, site_url),
            "datePublished": post.published_at.isoformat(),
            "dateModified": post.updated_at.isoformat(),
            "author": {"@type": "Person", "name": post.author},
            "publisher": {"@type": "Organization", "name": SEO_SITE_NAME},
            "mainEntityOfPage": urljoin(f"{site_url}/", canonical_path.lstrip("/")),
        }
    else:
        canonical_path = request.path

    clean_title = strip_tags(str(title or SEO_SITE_NAME)).strip()
    full_title = clean_title if SEO_SITE_NAME.lower() in clean_title.lower() else f"{clean_title} | {SEO_SITE_NAME}"
    clean_description = Truncator(strip_tags(str(description or SEO_DEFAULT_DESCRIPTION)).strip()).chars(160)
    canonical_url = urljoin(f"{site_url}/", canonical_path.lstrip("/"))
    uses_default_image = not image
    image_url = _absolute_url(request, str(image or SEO_DEFAULT_IMAGE), site_url)

    if schema is None and request.path == reverse("home"):
        schema = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "Organization", "name": SEO_SITE_NAME, "url": site_url, "logo": image_url},
                {
                    "@type": "WebSite",
                    "name": SEO_SITE_NAME,
                    "url": site_url,
                    "potentialAction": {
                        "@type": "SearchAction",
                        "target": f"{site_url}{reverse('search')}?q={{search_term_string}}",
                        "query-input": "required name=search_term_string",
                    },
                },
            ],
        }

    return {
        "seo_title": full_title,
        "seo_description": clean_description,
        "seo_canonical_url": canonical_url,
        "seo_image_url": image_url,
        "seo_image_width": 600 if uses_default_image else None,
        "seo_image_height": 557 if uses_default_image else None,
        "seo_type": content_type,
        "seo_robots": robots,
        "seo_schema_json": json.dumps(schema, ensure_ascii=False).replace("</", "<\\/") if schema else "",
    }


@register.filter
def cop(value):
    """Formatea un valor como pesos colombianos: 430000 -> $430.000 COP."""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    formatted = f"{amount:,.0f}".replace(",", ".")
    return f"${formatted} COP"


@register.filter
def cop_short(value):
    """Precio sin el sufijo COP: 430000 -> $430.000.

    Se usa donde no cabe el formato largo, como las dos etiquetas del filtro de
    precio en la barra lateral.
    """
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    return "$" + f"{amount:,.0f}".replace(",", ".")


@register.filter
def duration_minutes(value):
    """Redondea un timedelta hacia arriba a minutos completos, para mostrarlo al usuario."""
    try:
        seconds = value.total_seconds()
    except AttributeError:
        return value
    return max(1, -(-int(seconds) // 60))


@register.simple_tag(takes_context=True)
def catalog_filter_url(context, **overrides):
    """Querystring de la barra lateral conservando los filtros ya activos.

    Volver a pulsar el filtro seleccionado lo quita, que es como se comporta el
    catalogo de la tienda. Siempre se vuelve a la primera pagina, porque el
    numero de resultados cambia con cada filtro.
    """
    request = context.get("request")
    params = request.GET.copy() if request else QueryDict(mutable=True)
    params.pop("pagina", None)
    for key, value in overrides.items():
        if params.get(key) == str(value):
            params.pop(key, None)
        else:
            params[key] = value
    return params.urlencode()
