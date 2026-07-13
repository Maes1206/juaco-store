from django.urls import path

from . import views


urlpatterns = [
    path("healthz/", views.health, name="health"),
    path("panel-admin/", views.admin_dashboard, name="admin_dashboard"),
    path("", views.page, {"name": "home"}, name="home"),
    path("index.html", views.page, {"name": "home"}),
    path("about-us.html", views.page, {"name": "about"}, name="about"),
    path("contact.html", views.page, {"name": "contact"}, name="contact"),
    path("buscar/", views.search, name="search"),
    path("blog.html", views.blog, name="blog"),
    path("blog-details.html", views.blog_detail, name="blog_detail_legacy"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("shop.html", views.shop, name="shop"),
    path("single-product.html", views.product_detail, name="product_detail"),
    path("shop-wishlist.html", views.wishlist, name="wishlist"),
    path("shop-checkout.html", views.checkout, name="checkout"),
    path("order-confirmation/<str:number>/", views.order_confirmation, name="order_confirmation"),
    path("orders/<str:number>/", views.order_detail, name="order_detail"),
    path("page-not-found.html", views.not_found, name="not_found"),
    path("account-login.html", views.login_view, name="login"),
    path("account-register.html", views.register_view, name="register"),
    path("account-logout/", views.logout_view, name="logout"),
    path("account.html", views.account, name="account"),
    path("account-details/", views.account_details_update, name="account_details_update"),
    path("account-password/", views.account_password_change, name="account_password_change"),
    path("account-addresses/", views.address_create, name="address_create"),
    path("account-addresses/<int:address_id>/", views.address_update, name="address_update"),
    path("account-addresses/<int:address_id>/delete/", views.address_delete, name="address_delete"),
    path("shop-cart.html", views.cart_view, name="cart"),
    path("cart-coupon/apply/", views.coupon_apply, name="coupon_apply"),
    path("cart-coupon/remove/", views.coupon_remove, name="coupon_remove"),
    path("shipping-quote/", views.shipping_quote, name="shipping_quote"),
    path("api/favorites/", views.favorites_api, name="favorites_api"),
    path("api/favorites/<int:favorite_id>/", views.favorite_item_api, name="favorite_item_api"),
    path("api/favorites/<int:favorite_id>/move-to-cart/", views.favorite_move_to_cart_api, name="favorite_move_to_cart_api"),
    path("api/cart/", views.cart_api, name="cart_api"),
    path("api/cart/items/", views.cart_add_api, name="cart_add_api"),
    path("api/cart/items/<int:item_id>/", views.cart_item_api, name="cart_item_api"),
    path("api/session/", views.session_info, name="session_info"),
]

handler404 = views.not_found
