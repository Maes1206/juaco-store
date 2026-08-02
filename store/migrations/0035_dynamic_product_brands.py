from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


BRANDS = {
    "Jordan": {
        "slug": "jordan",
        "description": "La leyenda del baloncesto llevada a la calle.",
        "banner_image_url": "/assets/img/shop/hero-jordan-v2.png",
        "banner_image_alt": "Sneakers Jordan de estilo urbano",
        "empty_image_url": "/assets/img/shop/jordanpanda.png",
        "empty_image_alt": "Sneakers Jordan seleccionadas",
        "position": 10,
    },
    "Adidas": {
        "slug": "adidas",
        "description": "Siluetas clásicas y deportivas para todos los días.",
        "banner_image_url": "/assets/img/shop/hero-adidas-v2.png",
        "banner_image_alt": "Sneakers Adidas de estilo urbano",
        "empty_image_url": "/assets/img/shop/adidas.png",
        "empty_image_alt": "Sneakers Adidas seleccionadas",
        "position": 20,
    },
    "Puma": {
        "slug": "puma",
        "description": "Diseño deportivo, comodidad y actitud urbana.",
        "banner_image_url": "/assets/img/shop/hero-puma-v2.png",
        "banner_image_alt": "Sneakers Puma de estilo urbano",
        "empty_image_url": "/assets/img/shop/puma.png",
        "empty_image_alt": "Sneakers Puma seleccionadas",
        "position": 30,
    },
    "Nike": {
        "slug": "nike",
        "description": "Siluetas icónicas que marcaron la cultura sneaker.",
        "banner_image_url": "https://unsplash.com/photos/GXNOb23Jon8/download?force=true&w=1800",
        "banner_image_alt": "Sneakers Nike en entorno urbano",
        "empty_image_url": "/assets/img/shop/nike-card-v2.png",
        "empty_image_alt": "Sneaker Nike Dunk en tonos blanco, café y beige",
        "position": 5,
    },
}


def migrate_brands(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    StoreSection = apps.get_model("store", "StoreSection")

    known_sections = {}
    for title, data in BRANDS.items():
        section, _ = StoreSection.objects.update_or_create(
            slug=data["slug"],
            defaults={
                "section_type": "brand",
                "title": title,
                "description": data["description"],
                "banner_image_url": data["banner_image_url"],
                "banner_image_alt": data["banner_image_alt"],
                "empty_image_url": data["empty_image_url"],
                "empty_image_alt": data["empty_image_alt"],
                "empty_title": f"Próximamente más productos {title}",
                "empty_description": (
                    f"Cuando el equipo asigne productos {title} desde el panel administrativo, "
                    "aparecerán automáticamente aquí."
                ),
                "position": data["position"],
                "is_active": True,
            },
        )
        known_sections[title.casefold()] = section

    for product in Product.objects.all():
        brand_name = (product.legacy_brand or "").strip()
        section = known_sections.get(brand_name.casefold())
        if section is None:
            slug = slugify(brand_name) or f"marca-{product.pk}"
            section, _ = StoreSection.objects.get_or_create(
                slug=slug,
                defaults={
                    "section_type": "brand",
                    "title": brand_name or f"Marca {product.pk}",
                    "description": f"Productos seleccionados de {brand_name}.",
                    "banner_image_url": product.image,
                    "banner_image_alt": f"Productos {brand_name}",
                    "empty_image_url": product.image,
                    "empty_image_alt": f"Próximos productos {brand_name}",
                    "is_active": True,
                },
            )
            if section.section_type != "brand":
                section.section_type = "brand"
                section.save(update_fields=("section_type",))
            known_sections[brand_name.casefold()] = section
        product.brand_id = section.pk
        product.save(update_fields=("brand",))
        product.store_sections.remove(section)


def restore_legacy_brands(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    StoreSection = apps.get_model("store", "StoreSection")

    for product in Product.objects.select_related("brand").all():
        if product.brand_id:
            product.legacy_brand = product.brand.title
            product.store_sections.add(product.brand)
            product.brand_id = None
            product.save(update_fields=("legacy_brand", "brand"))
    StoreSection.objects.filter(slug="nike", section_type="brand").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0034_seed_brand_sections"),
    ]

    operations = [
        migrations.RenameField(
            model_name="product",
            old_name="brand",
            new_name="legacy_brand",
        ),
        migrations.AlterField(
            model_name="product",
            name="legacy_brand",
            field=models.CharField(blank=True, default="", editable=False, max_length=40, verbose_name="marca anterior"),
        ),
        migrations.AddField(
            model_name="storesection",
            name="section_type",
            field=models.CharField(
                choices=[("brand", "Marca"), ("custom", "Sección personalizada")],
                db_index=True,
                default="custom",
                help_text="Las marcas aparecen automáticamente en el selector de productos.",
                max_length=12,
                verbose_name="tipo de sección",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="brand",
            field=models.ForeignKey(
                limit_choices_to={"section_type": "brand"},
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="brand_products",
                to="store.storesection",
                verbose_name="marca",
            ),
        ),
        migrations.RunPython(migrate_brands, restore_legacy_brands),
        migrations.AlterField(
            model_name="product",
            name="brand",
            field=models.ForeignKey(
                limit_choices_to={"section_type": "brand"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="brand_products",
                to="store.storesection",
                verbose_name="marca",
            ),
        ),
        migrations.AlterModelOptions(
            name="product",
            options={"ordering": ["brand__title", "name"]},
        ),
    ]
