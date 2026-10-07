from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0007_order_orderitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="tags",
            field=models.JSONField(blank=True, default=list, verbose_name="etiquetas"),
        ),
    ]
