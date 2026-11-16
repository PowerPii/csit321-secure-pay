"""The Volt & Co. catalogue: twelve products whose prices suit the demo stories.

A S$19 cable for a quick small payment (S1), a S$2,399 laptop for a verification code
(S2), and cheap accessories a card tester would try (S3). The old wireframe products keep
their SKUs and prices so existing orders still read well; the desk lamp leaves the shelf.
"""
from django.db import migrations

# sku, name, price, category, art, badge, blurb, description, details
PRODUCTS = [
    ("LAPTOP-14", "Volt Book 14", 239900, "computing", "laptop", "New",
     "14-inch ultralight laptop, 16 GB memory, 1 TB SSD.",
     "Our own-brand ultralight for work and study. An all-day battery, a bright 2.8K screen "
     "and a keyboard you will actually enjoy typing on, in a 1.2 kg aluminium body.",
     "14-inch 2.8K display, 120 Hz\n16 GB memory, 1 TB SSD\nUp to 18 hours of battery\n"
     "Two USB-C ports, one USB-A, headphone jack\n1.2 kg, 15 mm thin\n2-year Volt warranty"),
    ("HEAD-01", "Volt Quiet Over-ear Headphones", 24900, "audio", "headphones", "Bestseller",
     "Active noise cancelling with 40-hour battery.",
     "Shut out the MRT and the open-plan office. Adaptive noise cancelling, soft memory-foam "
     "cushions and a fold-flat design that fits in a laptop bag.",
     "Adaptive active noise cancelling\nUp to 40 hours of playback\nUSB-C fast charge: "
     "10 minutes for 5 hours\nBluetooth 5.3, two devices at once\nFolds flat, case included"),
    ("BUDS-01", "Volt Buds Pro", 14900, "audio", "earbuds", "",
     "True wireless earbuds with a pocket-sized case.",
     "Small, light and sweat resistant. Three sizes of tips in the box and a case that "
     "charges wirelessly.",
     "Noise cancelling and transparency modes\n8 hours of playback, 32 with the case\n"
     "IPX4 sweat resistant\nWireless charging case"),
    ("SPK-01", "Volt Go Speaker", 8900, "audio", "speaker", "",
     "Waterproof portable speaker for East Coast picnics.",
     "Big sound from a speaker the size of a water bottle. Waterproof, dustproof and it "
     "floats, so the pool party is safe too.",
     "IP67 waterproof and dustproof\n12 hours of playback\nPair two for stereo\n"
     "Strap for bags and bikes"),
    ("KEY-01", "Volt Keys Mechanical Keyboard", 16900, "computing", "keyboard", "",
     "Compact 75% layout, hot-swappable switches.",
     "A compact mechanical keyboard with a satisfying, quiet click. Works with Mac and "
     "Windows over Bluetooth or cable.",
     "75% layout with a volume knob\nHot-swappable tactile switches\nBluetooth and USB-C\n"
     "White backlight\nMac and Windows keycaps included"),
    ("MON-27", "Volt View 27-inch 4K Monitor", 54900, "computing", "monitor", "",
     "Sharp 4K screen with one-cable USB-C charging.",
     "One USB-C cable charges your laptop and carries picture and sound. A height-adjustable "
     "stand saves your neck during long study sessions.",
     "27-inch 4K IPS panel\n65 W USB-C power delivery\nHeight, tilt and swivel stand\n"
     "HDMI, DisplayPort, USB-C"),
    ("HUB-01", "USB-C hub", 6000, "computing", "hub", "",
     "Seven ports from one USB-C plug.",
     "Turns one USB-C port into everything a desk needs: HDMI, card readers, USB-A and "
     "pass-through charging.",
     "4K HDMI\n2 USB-A, 1 USB-C data\nSD and microSD readers\n100 W pass-through charging"),
    ("STAND-01", "Laptop stand", 4500, "computing", "laptop-stand", "",
     "Aluminium stand that lifts your screen to eye level.",
     "Raise your laptop by 15 cm, keep it cool and free up desk space. Folds flat for the "
     "commute.",
     "Six height settings\nFits 11 to 16-inch laptops\nAluminium, folds flat\nNon-slip pads"),
    ("CHG-65", "Volt 65W GaN Charger", 5900, "accessories", "charger", "Bestseller",
     "Charges a laptop, phone and earbuds at once.",
     "One small charger for everything in your bag. Gallium nitride keeps it cool and half "
     "the size of the brick that came with your laptop.",
     "65 W total, three ports (2 USB-C, 1 USB-A)\nFoldable Singapore plug\nOver-heat and "
     "over-current protection"),
    ("MOUSE-01", "Wireless mouse", 2990, "accessories", "mouse", "",
     "Quiet clicks, 70-day battery.",
     "A comfortable everyday mouse with silent buttons, so your study group does not hear "
     "every click.",
     "Silent left and right buttons\nUp to 70 days per charge\nBluetooth and USB receiver"),
    ("STAND-PH", "Phone stand", 2400, "accessories", "phone-stand", "",
     "Adjustable stand for video calls and recipes.",
     "Holds any phone upright or sideways at the angle you choose. Weighted base, no "
     "wobble.",
     "Fits phones 4 to 7 inches\nAdjustable angle\nWeighted aluminium base"),
    ("CABLE-01", "USB-C cable, 2 m", 1900, "accessories", "cable", "",
     "Braided cable, 100 W charging.",
     "Long enough to reach from the wall to your bed. Braided so it survives being stuffed "
     "into bags.",
     "2 m braided nylon\nUp to 100 W charging\nUSB 2.0 data"),
]

RETIRED = ["LAMP-01"]


def seed(apps, schema_editor):
    Product = apps.get_model("shop", "Product")
    Product.objects.filter(sku__in=RETIRED).delete()
    for position, (sku, name, price, category, art, badge, blurb, description,
                   details) in enumerate(PRODUCTS):
        Product.objects.update_or_create(sku=sku, defaults={
            "name": name, "price_cents": price, "position": position, "category": category,
            "art": art, "badge": badge, "blurb": blurb, "description": description,
            "details": details})


def unseed(apps, schema_editor):
    # Keep the products a reverse migration to 0002 would expect.
    keep = {"MOUSE-01", "HUB-01", "STAND-01"}
    apps.get_model("shop", "Product").objects.filter(
        sku__in=[p[0] for p in PRODUCTS if p[0] not in keep]).delete()


class Migration(migrations.Migration):
    dependencies = [("shop", "0004_product_catalogue_fields")]
    operations = [migrations.RunPython(seed, unseed)]
