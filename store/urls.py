from django.urls import path

from . import views


urlpatterns = [
    path("", views.page, {"name": "home"}, name="home"),
    path("index.html", views.page, {"name": "home"}),
    path("about-us.html", views.page, {"name": "about"}, name="about"),
    path("contact.html", views.page, {"name": "contact"}, name="contact"),
    path("blog.html", views.page, {"name": "blog"}, name="blog"),
    path("blog-details.html", views.page, {"name": "blog_detail"}, name="blog_detail"),
    path("shop.html", views.shop, name="shop"),
    path("single-product.html", views.product_detail, name="product_detail"),
    path("shop-wishlist.html", views.page, {"name": "wishlist"}, name="wishlist"),
    path("shop-checkout.html", views.page, {"name": "checkout"}, name="checkout"),
    path("page-not-found.html", views.not_found, name="not_found"),
    path("account-login.html", views.login_view, name="login"),
    path("account-register.html", views.register_view, name="register"),
    path("account-logout/", views.logout_view, name="logout"),
    path("account.html", views.account, name="account"),
    path("shop-cart.html", views.cart_view, name="cart"),
    path("api/cart/", views.cart_api, name="cart_api"),
    path("api/cart/items/", views.cart_add_api, name="cart_add_api"),
    path("api/cart/items/<int:item_id>/", views.cart_item_api, name="cart_item_api"),
]

handler404 = views.not_found
