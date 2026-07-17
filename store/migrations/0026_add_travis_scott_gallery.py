from django.db import migrations


PRODUCT_SLUG = "nike-sb-dunk-low-travis-scott"
MAIN_IMAGE = "assets/img/shop/541x540/8743.png"
GALLERY = [
    {
        "url": "assets/img/shop/541x540/8276.png",
        "alt": "Vista frontal Nike SB Dunk Low x Travis Scott Cactus Jack",
    },
    {
        "url": "assets/img/shop/541x540/7173.png",
        "alt": "Vista posterior Nike SB Dunk Low x Travis Scott Cactus Jack",
    },
    {
        "url": "assets/img/shop/541x540/823763.png",
        "alt": "Suela Nike SB Dunk Low x Travis Scott Cactus Jack",
    },
]


def add_product_gallery(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.filter(slug=PRODUCT_SLUG).update(
        image=MAIN_IMAGE,
        image_alt="Vista lateral Nike SB Dunk Low x Travis Scott Cactus Jack",
        gallery=GALLERY,
    )


def remove_product_gallery(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.filter(slug=PRODUCT_SLUG).update(
        image_alt="",
        gallery=[],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0025_order_fulfillment_status"),
    ]

    operations = [
        migrations.RunPython(add_product_gallery, remove_product_gallery),
    ]
