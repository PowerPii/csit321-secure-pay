from django.urls import path

from apps.common.views import todo

urlpatterns = [
    path("payments/<str:payment_id>/refunds",
         todo("create full/partial refund; reserve under SELECT FOR UPDATE on the payment"),
         name="refund-create"),
    path("refunds/<str:refund_id>", todo("get refund status"), name="refund-detail"),
]
