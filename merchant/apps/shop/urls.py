"""Demo storefront pages (wireframes C1, C2, C8)."""
from django.http import HttpResponse
from django.urls import path


def todo(screen):
    def view(request, **kwargs):
        return HttpResponse(f"TODO: {screen}", status=501, content_type="text/plain")

    return view


urlpatterns = [
    path("", todo("C1 products and cart"), name="shop-home"),
    path("checkout", todo("C2 order summary; POST creates the gateway payment and redirects"),
         name="shop-checkout"),
    path("orders/<str:order_ref>", todo("C8 order page; paid only after webhook + API check"),
         name="shop-order"),
]
