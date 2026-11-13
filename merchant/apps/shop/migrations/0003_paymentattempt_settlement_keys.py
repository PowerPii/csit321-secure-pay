import uuid

from django.db import migrations, models


def fill_keys(apps, schema_editor):
    """Each existing attempt gets its own keys (a callable default runs once per column)."""
    PaymentAttempt = apps.get_model("shop", "PaymentAttempt")
    for attempt in PaymentAttempt.objects.all():
        attempt.capture_key = uuid.uuid4()
        attempt.cancel_key = uuid.uuid4()
        attempt.save(update_fields=["capture_key", "cancel_key"])


class Migration(migrations.Migration):
    dependencies = [("shop", "0002_seed_products")]

    operations = [
        migrations.AddField("paymentattempt", "capture_key",
                            models.UUIDField(null=True, editable=False)),
        migrations.AddField("paymentattempt", "cancel_key",
                            models.UUIDField(null=True, editable=False)),
        migrations.AddField("paymentattempt", "captured_amount",
                            models.PositiveIntegerField(default=0)),
        migrations.RunPython(fill_keys, migrations.RunPython.noop),
        migrations.AlterField("paymentattempt", "capture_key",
                              models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
        migrations.AlterField("paymentattempt", "cancel_key",
                              models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
    ]
