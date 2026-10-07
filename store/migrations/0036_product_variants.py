from django.db import migrations, models
import django.db.models.deletion
import django.core.validators


def seed_product_variants(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    ProductVariant = apps.get_model("store", "ProductVariant")
    CartItem = apps.get_model("store", "CartItem")
    OrderItem = apps.get_model("store", "OrderItem")

    for product in Product.objects.all():
        sizes = [str(value).strip() for value in (product.sizes or []) if str(value).strip()] or [""]
        colors = []
        for value in product.colors or []:
            if isinstance(value, dict) and value.get("name"):
                colors.append((str(value["name"]).strip(), str(value.get("hex") or "#505050").upper()))
        colors = colors or [("", "")]
        combinations = [(size, color_name, color_hex) for size in sizes for color_name, color_hex in colors]
        base_stock, remainder = divmod(product.stock, len(combinations))
        created_variants = []
        for index, (size, color_name, color_hex) in enumerate(combinations):
            created_variants.append(ProductVariant.objects.create(
                product_id=product.pk,
                size=size,
                color_name=color_name,
                color_hex=color_hex,
                stock=base_stock + (1 if index < remainder else 0),
                is_active=True,
            ))

        for cart_item in CartItem.objects.filter(product_id=product.pk):
            variant = next((
                entry for entry in created_variants
                if entry.size == cart_item.size and entry.color_name == cart_item.color
            ), created_variants[0])
            cart_item.variant_id = variant.pk
            cart_item.size = variant.size
            cart_item.color = variant.color_name
            cart_item.save(update_fields=("variant", "size", "color"))

        for order_item in OrderItem.objects.filter(product_id=product.pk):
            variant = next((
                entry for entry in created_variants
                if entry.size == order_item.size and entry.color_name == order_item.color
            ), created_variants[0])
            order_item.variant_id = variant.pk
            order_item.variant_sku = variant.sku or ""
            order_item.save(update_fields=("variant", "variant_sku"))


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0035_dynamic_product_brands"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductVariant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku", models.CharField(blank=True, max_length=100, null=True, unique=True, verbose_name="referencia de variante")),
                ("size", models.CharField(blank=True, max_length=12, verbose_name="talla")),
                ("color_name", models.CharField(blank=True, max_length=60, verbose_name="color")),
                ("color_hex", models.CharField(blank=True, max_length=7, validators=[django.core.validators.RegexValidator("^#[0-9A-Fa-f]{6}$", "Usa un color hexadecimal como #505050.")], verbose_name="código de color")),
                ("stock", models.PositiveIntegerField(default=0, verbose_name="existencias")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="disponible")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="variants", to="store.product", verbose_name="producto")),
            ],
            options={
                "verbose_name": "variante de producto",
                "verbose_name_plural": "variantes de producto",
                "ordering": ("product", "size", "color_name", "id"),
                "constraints": [models.UniqueConstraint(fields=("product", "size", "color_name"), name="unique_product_size_color_variant")],
            },
        ),
        migrations.AddField(
            model_name="cartitem",
            name="variant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cart_items", to="store.productvariant", verbose_name="variante"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="variant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="order_items", to="store.productvariant", verbose_name="variante"),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="variant_sku",
            field=models.CharField(blank=True, max_length=100, verbose_name="referencia de variante"),
        ),
        migrations.RunPython(seed_product_variants, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="stock",
            field=models.PositiveIntegerField(default=0, verbose_name="inventario"),
        ),
    ]
