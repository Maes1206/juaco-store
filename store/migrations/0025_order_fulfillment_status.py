from django.db import migrations, models


def copy_existing_shipping_status(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    Order.objects.filter(status="shipped").update(fulfillment_status="in_transit")
    Order.objects.filter(status="delivered").update(fulfillment_status="delivered")


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0024_order_delivery_method"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="fulfillment_status",
            field=models.CharField(
                choices=[
                    ("pending_shipment", "Pendiente de envío"),
                    ("packing", "Empacando producto"),
                    ("in_transit", "En camino"),
                    ("delivered", "Entregado"),
                ],
                db_index=True,
                default="pending_shipment",
                max_length=20,
                verbose_name="estado del envío",
            ),
        ),
        migrations.RunPython(copy_existing_shipping_status, migrations.RunPython.noop),
    ]
