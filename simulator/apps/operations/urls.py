"""Simulator API, called only by the gateway (authenticated, internal network).

Every call carries the gateway's operation ID; the simulator enforces uniqueness on it,
so a retry or status query never makes a second financial effect.
"""
from django.http import JsonResponse
from django.urls import path


def todo(description):
    def view(request, **kwargs):
        return JsonResponse({"error": "not_implemented", "todo": description}, status=501)

    return view


urlpatterns = [
    path("authorise", todo("authorise by test card behaviour; unique on operation_id"),
         name="sim-authorise"),
    path("operations/<str:operation_id>", todo("status query by original operation ID"),
         name="sim-operation"),
    path("capture", todo("capture an authorisation"), name="sim-capture"),
    path("cancel", todo("void an authorisation"), name="sim-cancel"),
    path("refund", todo("refund against a captured operation"), name="sim-refund"),
]
