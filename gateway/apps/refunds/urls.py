from django.urls import path

from apps.refunds.views import PaymentRefundsView, RefundDetailView

urlpatterns = [
    path("payments/<str:payment_id>/refunds", PaymentRefundsView.as_view(),
         name="refund-create"),
    path("refunds/<str:refund_id>", RefundDetailView.as_view(), name="refund-detail"),
]
