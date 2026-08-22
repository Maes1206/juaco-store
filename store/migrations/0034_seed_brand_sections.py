from django.db import migrations


BRAND_SECTIONS = (
    {
        "title": "Jordan",
        "slug": "jordan",
        "description": "La leyenda del baloncesto llevada a la calle.",
        "banner_image_url": "/assets/img/shop/hero-jordan-v2.png",
        "banner_image_alt": "Sneakers Jordan de estilo urbano",
        "empty_image_url": "/assets/img/shop/jordanpanda.png",
        "empty_image_alt": "Sneakers Jordan seleccionadas",
        "position": 10,
    },
    {
        "title": "Adidas",
        "slug": "adidas",
        "description": "Siluetas clásicas y deportivas para todos los días.",
        "banner_image_url": "/assets/img/shop/hero-adidas-v2.png",
        "banner_image_alt": "Sneakers Adidas de estilo urbano",
        "empty_image_url": "/assets/img/shop/adidas.png",
        "empty_image_alt": "Sneakers Adidas seleccionadas",
        "position": 20,
    },
    {
        "title": "Puma",
        "slug": "puma",
        "description": "Diseño deportivo, comodidad y actitud urbana.",
        "banner_image_url": "/assets/img/shop/hero-puma-v2.png",
        "banner_image_alt": "Sneakers Puma de estilo urbano",
        "empty_image_url": "/assets/img/shop/puma.png",
        "empty_image_alt": "Sneakers Puma seleccionadas",
        "position": 30,
    },
)


def seed_brand_sections(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    StoreSection = apps.get_model("store", "StoreSection")

    for data in BRAND_SECTIONS:
        brand = data["title"]
        section, _ = StoreSection.objects.update_or_create(
            slug=data["slug"],
            defaults={
                **data,
                "empty_title": f"Próximamente más productos {brand}",
                "empty_description": (
                    f"Cuando el equipo asigne productos {brand} desde el panel "
                    "administrativo, aparecerán automáticamente aquí."
                ),
                "is_active": True,
            },
        )
        for product in Product.objects.filter(brand=brand):
            product.store_sections.add(section)


def remove_seeded_brand_sections(apps, schema_editor):
    StoreSection = apps.get_model("store", "StoreSection")
    StoreSection.objects.filter(slug__in=[item["slug"] for item in BRAND_SECTIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0033_store_sections"),
    ]

    operations = [
        migrations.RunPython(seed_brand_sections, remove_seeded_brand_sections),
    ]
