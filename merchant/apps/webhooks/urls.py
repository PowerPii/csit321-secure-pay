from django.http import JsonResponse
from django.urls import path


def receive(request):
    return JsonResponse({"todo": "verify signature, dedupe event ID, confirm via API"}, status=501)


urlpatterns = [path("securepay", receive, name="webhook-securepay")]
