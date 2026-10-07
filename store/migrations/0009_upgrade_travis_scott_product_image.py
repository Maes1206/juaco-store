from django.db import migrations


PRODUCT_SLUG = "nike-sb-dunk-low-travis-scott"
HIGH_RESOLUTION_IMAGE = "assets/img/shop/541x540/8743.png"


def upgrade_product_image(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.filter(slug=PRODUCT_SLUG).update(image=HIGH_RESOLUTION_IMAGE)


def restore_product_image(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.filter(slug=PRODUCT_SLUG).update(image="assets/img/shop/27734.png")


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0008_product_tags"),
    ]

    operations = [
        migrations.RunPython(upgrade_product_image, restore_product_image),
    ]
