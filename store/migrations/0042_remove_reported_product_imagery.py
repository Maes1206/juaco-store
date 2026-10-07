from django.db import migrations


REPORTED_PRODUCT_SLUGS = (
    "nike-air-force-1-triple-white",
    "jordan-4-paris-olympics",
    "nike-dunk-low-year-rabbit",
    "nike-sb-dunk-low-travis-scott",
    "jordan-1-obsidian",
)


def remove_reported_product_imagery(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.filter(slug__in=REPORTED_PRODUCT_SLUGS).update(
        image="",
        image_file="",
        image_alt="",
        gallery=[],
        is_active=False,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0041_alter_marketingpopup_image_file_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_reported_product_imagery, migrations.RunPython.noop),
    ]
