"""The four products on wireframe C1."""
from django.db import migrations

PRODUCTS = [
    ("MOUSE-01", "Wireless mouse", 2990),
    ("HUB-01", "USB-C hub", 6000),
    ("STAND-01", "Laptop stand", 4500),
    ("LAMP-01", "Desk lamp", 3850),
]


def seed(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    for position, (sku, name, price) in enumerate(PRODUCTS):
        Product.objects.update_or_create(sku=sku, defaults={"name": name, "price_cents": price,
                                                            "position": position})


def unseed(apps, schema_editor):
    apps.get_model("shop", "Product").objects.filter(sku__in=[p[0] for p in PRODUCTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
