"""The table behind settings.CACHES (rate-limit counters shared by every gunicorn worker)."""
from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    if schema_editor.connection.alias == "default":
        call_command("createcachetable", database="default", verbosity=0)


class Migration(migrations.Migration):
    dependencies = [("security", "0003_data_keys_and_maintenance_runs")]

    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
