"""Simulator API, called only by the gateway (authenticated, internal network).

Every call carries the gateway's operation ID; the simulator enforces uniqueness on it,
so a retry or status query never makes a second financial effect.
"""
from django.urls import path

from apps.operations import views

urlpatterns = [
    path("authorise", views.authorise, name="sim-authorise"),
    path("operations/<str:operation_id>", views.operation_status, name="sim-operation"),
    path("capture", views.capture, name="sim-capture"),
    path("cancel", views.cancel, name="sim-cancel"),
    path("refund", views.refund, name="sim-refund"),
]
