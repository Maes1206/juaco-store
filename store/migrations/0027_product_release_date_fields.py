from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0026_add_travis_scott_gallery"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="release_date",
            field=models.DateField(blank=True, null=True, verbose_name="fecha de lanzamiento"),
        ),
        migrations.AddField(
            model_name="product",
            name="release_date_checked_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="última consulta de lanzamiento"),
        ),
        migrations.AddField(
            model_name="product",
            name="release_date_source",
            field=models.CharField(
                blank=True,
                choices=[("", "Sin definir"), ("manual", "Ingresada manualmente"), ("stockx", "StockX")],
                default="",
                editable=False,
                max_length=12,
                verbose_name="origen de la fecha",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="stockx_product_id",
            field=models.CharField(blank=True, editable=False, max_length=80, verbose_name="ID de producto en StockX"),
        ),
    ]
