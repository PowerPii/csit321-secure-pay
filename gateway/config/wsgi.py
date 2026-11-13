"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Load the fraud model now, not inside the first customer's payment: joblib and scikit-learn
# take about a second to load, which the first screening would otherwise wait for.
from apps.risk.scoring import active_model

active_model()
