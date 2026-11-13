from django.urls import path

from apps.webhooks.views import receive

urlpatterns = [path("securepay", receive, name="webhook-securepay")]
