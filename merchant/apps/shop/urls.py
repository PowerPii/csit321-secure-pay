"""Demo storefront pages (wireframes C1, C2, C8)."""
from django.urls import path

from apps.shop import views

urlpatterns = [
    path("", views.home, name="shop-home"),
    path("cart/add", views.cart_add, name="shop-cart-add"),
    path("cart/remove", views.cart_remove, name="shop-cart-remove"),
    path("checkout", views.checkout, name="shop-checkout"),
    path("orders", views.order_list, name="shop-orders"),
    path("orders/<int:number>", views.order_detail, name="shop-order"),
    path("orders/<int:number>/return", views.order_return, name="shop-order-return"),
    path("orders/<int:number>/pay", views.order_pay, name="shop-order-pay"),
]
