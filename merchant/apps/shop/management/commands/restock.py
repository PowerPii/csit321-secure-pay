"""Put every Volt & Co. product back on the shelf, for example the morning of a demo.

    python manage.py restock            # every product to 25
    python manage.py restock --to 3     # every product to 3 (shows "Only 3 left")
    python manage.py restock --sku LAPTOP-14 --to 0   # sell one product out
"""
from django.core.management.base import BaseCommand, CommandError

from apps.shop.catalogue import RESTOCK_TO
from apps.shop.models import Product


class Command(BaseCommand):
    help = "Set the stock count of every product (or one SKU)."

    def add_arguments(self, parser):
        parser.add_argument("--to", type=int, default=RESTOCK_TO)
        parser.add_argument("--sku", default="")

    def handle(self, *args, to, sku, **options):
        if not 0 <= to <= 1000:
            raise CommandError("--to must be between 0 and 1000")
        products = Product.objects.all()
        if sku:
            products = products.filter(sku=sku)
            if not products.exists():
                raise CommandError(f"No product with SKU {sku}")
        count = products.update(stock=to)
        self.stdout.write(self.style.SUCCESS(f"{count} product(s) now have {to} in stock."))
