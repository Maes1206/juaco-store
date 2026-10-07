from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
import store.models


def seed_order_history(apps, schema_editor):
    Order = apps.get_model("store", "Order")
    OrderStatusHistory = apps.get_model("store", "OrderStatusHistory")

    fulfillment_mapping = {
        "packing": "preparing",
        "in_transit": "shipped",
        "delivered": "delivered",
    }
    for order in Order.objects.all().iterator():
        if order.status == "paid" and order.fulfillment_status in fulfillment_mapping:
            order.status = fulfillment_mapping[order.fulfillment_status]
            update_fields = ["status"]
            if order.status == "shipped":
                order.shipped_at = order.updated_at
                update_fields.append("shipped_at")
            elif order.status == "delivered":
                order.shipped_at = order.updated_at
                order.delivered_at = order.updated_at
                update_fields.extend(("shipped_at", "delivered_at"))
            order.save(update_fields=update_fields)

        history = OrderStatusHistory.objects.create(
            order_id=order.pk,
            from_status="",
            to_status=order.status,
            source="migration",
            note="Estado inicial registrado al habilitar el historial operativo.",
        )
        OrderStatusHistory.objects.filter(pk=history.pk).update(created_at=order.created_at)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("store", "0036_product_variants"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="carrier",
            field=models.CharField(blank=True, max_length=100, verbose_name="transportadora"),
        ),
        migrations.AddField(
            model_name="order",
            name="tracking_number",
            field=models.CharField(blank=True, db_index=True, max_length=120, verbose_name="número de guía"),
        ),
        migrations.AddField(
            model_name="order",
            name="dispatch_receipt",
            field=models.FileField(
                blank=True,
                help_text="Opcional. PDF o imagen de hasta 5 MB; la guía en texto sigue siendo la referencia principal.",
                upload_to="orders/dispatch/%Y/%m/",
                validators=[
                    django.core.validators.FileExtensionValidator(("pdf", "jpg", "jpeg", "png", "webp")),
                    store.models.validate_dispatch_receipt,
                ],
                verbose_name="comprobante de despacho",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="shipped_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="fecha de despacho"),
        ),
        migrations.AddField(
            model_name="order",
            name="delivered_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="fecha de entrega"),
        ),
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pendiente de pago"),
                    ("paid", "Pagado"),
                    ("preparing", "Preparando"),
                    ("shipped", "Enviado"),
                    ("delivered", "Entregado"),
                    ("cancelled", "Cancelado"),
                    ("refunded", "Reembolsado"),
                ],
                db_index=True,
                default="pending",
                max_length=12,
                verbose_name="estado",
            ),
        ),
        migrations.CreateModel(
            name="OrderStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(blank=True, choices=[("pending", "Pendiente de pago"), ("paid", "Pagado"), ("preparing", "Preparando"), ("shipped", "Enviado"), ("delivered", "Entregado"), ("cancelled", "Cancelado"), ("refunded", "Reembolsado")], max_length=12, verbose_name="estado anterior")),
                ("to_status", models.CharField(choices=[("pending", "Pendiente de pago"), ("paid", "Pagado"), ("preparing", "Preparando"), ("shipped", "Enviado"), ("delivered", "Entregado"), ("cancelled", "Cancelado"), ("refunded", "Reembolsado")], max_length=12, verbose_name="nuevo estado")),
                ("source", models.CharField(choices=[("admin", "Panel administrativo"), ("payment", "Confirmación de pago"), ("webhook", "Webhook"), ("system", "Sistema"), ("migration", "Migración")], default="system", max_length=12, verbose_name="origen")),
                ("note", models.CharField(blank=True, max_length=300, verbose_name="nota")),
                ("notification_sent_at", models.DateTimeField(blank=True, editable=False, null=True, verbose_name="notificación enviada")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="fecha")),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="order_status_changes", to=settings.AUTH_USER_MODEL, verbose_name="responsable")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_history", to="store.order", verbose_name="pedido")),
            ],
            options={
                "verbose_name": "cambio de estado del pedido",
                "verbose_name_plural": "historial de estados del pedido",
                "ordering": ("-created_at", "-id"),
            },
        ),
        migrations.RunPython(seed_order_history, migrations.RunPython.noop),
    ]
