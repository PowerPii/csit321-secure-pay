"""Volt & Co. storefront pages (wireframes C1, C2, C8)."""
from django.urls import path

from apps.shop import views

urlpatterns = [
    path("", views.home, name="shop-home"),
    path("category/<slug:slug>", views.category, name="shop-category"),
    path("search", views.search, name="shop-search"),
    path("products/<str:sku>", views.product_detail, name="shop-product"),
    path("cart", views.cart_view, name="shop-cart"),
    path("help/<slug:page>", views.info, name="shop-info"),
    path("cart/add", views.cart_add, name="shop-cart-add"),
    path("cart/update", views.cart_update, name="shop-cart-update"),
    path("cart/remove", views.cart_remove, name="shop-cart-remove"),
    path("checkout", views.checkout, name="shop-checkout"),
    path("orders", views.order_list, name="shop-orders"),
    path("orders/<int:number>", views.order_detail, name="shop-order"),
    path("orders/<int:number>/return", views.order_return, name="shop-order-return"),
    path("orders/<int:number>/pay", views.order_pay, name="shop-order-pay"),
]
