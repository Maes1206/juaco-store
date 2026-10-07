from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0030_alter_homebanner_media_file_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="confirmation_email_sent_at",
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name="confirmación enviada"),
        ),
    ]
