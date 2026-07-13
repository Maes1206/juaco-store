from django.db import migrations


DEFAULT_COLOR = [{"name": "Color principal", "hex": "#505050"}]
PARIS_COLORS = [
    {"name": "Azul grisaceo", "hex": "#586882"},
    {"name": "Gris oscuro", "hex": "#505050"},
    {"name": "Gris piedra", "hex": "#73707A"},
    {"name": "Beige", "hex": "#C7BB9B"},
]


def seed_colors(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.filter(colors=[]).update(colors=DEFAULT_COLOR)
    Product.objects.filter(slug="jordan-4-paris-olympics").update(colors=PARIS_COLORS)


def clear_colors(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.all().update(colors=[])


class Migration(migrations.Migration):
    dependencies = [("store", "0018_remove_cartitem_unique_cart_product_size_and_more")]
    operations = [migrations.RunPython(seed_colors, clear_colors)]