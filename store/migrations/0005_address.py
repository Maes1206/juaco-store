from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("store", "0004_add_more_blog_posts"),
    ]

    operations = [
        migrations.CreateModel(
            name="Address",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("first_name", models.CharField(max_length=80, verbose_name="nombre")),
                ("last_name", models.CharField(max_length=80, verbose_name="apellidos")),
                ("address_line_1", models.CharField(max_length=180, verbose_name="dirección")),
                ("address_line_2", models.CharField(blank=True, max_length=180, verbose_name="complemento")),
                ("department", models.CharField(max_length=80, verbose_name="departamento")),
                ("city", models.CharField(max_length=80, verbose_name="ciudad")),
                ("postal_code", models.CharField(blank=True, max_length=12, verbose_name="código postal")),
                ("phone", models.CharField(max_length=30, verbose_name="teléfono")),
                ("label", models.CharField(default="Dirección de envío", max_length=40, verbose_name="nombre de la dirección")),
                ("is_default", models.BooleanField(default=False, verbose_name="dirección principal")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="addresses", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "dirección",
                "verbose_name_plural": "direcciones",
                "ordering": ["-is_default", "-updated_at"],
            },
        ),
    ]
