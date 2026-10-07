from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import AccountPasswordResetForm


urlpatterns = [
    path("healthz/", views.health, name="health"),
    path("panel-admin/", views.admin_dashboard, name="admin_dashboard"),
    path("", views.page, {"name": "home"}, name="home"),
    path("index.html", views.page, {"name": "home"}),
    path("about-us.html", views.page, {"name": "about"}, name="about"),
    path("contact.html", views.page, {"name": "contact"}, name="contact"),
    path("newsletter/subscribe/", views.newsletter_subscribe, name="newsletter_subscribe"),
    path("buscar/", views.search, name="search"),
    path("blog.html", views.blog, name="blog"),
    path("blog-details.html", views.blog_detail, name="blog_detail_legacy"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("secciones/<slug:section>/", views.catalog_section, name="catalog_section"),
    path("shop.html", views.shop, name="shop"),
    path("single-product.html", views.product_detail, name="product_detail"),
    path("shop-wishlist.html", views.wishlist, name="wishlist"),
    path("shop-checkout.html", views.checkout, name="checkout"),
    path("order-confirmation/<str:number>/", views.order_confirmation, name="order_confirmation"),
    path("pago/bold/retorno/", views.bold_return, name="bold_return"),
    path("pago/bold/webhook/", views.bold_webhook, name="bold_webhook"),
    path("pago/<str:number>/", views.order_payment, name="order_payment"),
    path("pago/<str:number>/estado/", views.order_payment_status, name="order_payment_status"),
    path("pago/<str:number>/verificar/", views.order_payment_check, name="order_payment_check"),
    path("orders/<str:number>/comprobante.pdf", views.order_receipt_pdf, name="order_receipt_pdf"),
    path("orders/<str:number>/comprobante-despacho/", views.order_dispatch_receipt, name="order_dispatch_receipt"),
    path("orders/<str:number>/", views.order_detail, name="order_detail"),
    path("verificar-comprobante/<str:token>/", views.verify_receipt, name="verify_receipt"),
    path("page-not-found.html", views.not_found, name="not_found"),
    path("account-login.html", views.login_view, name="login"),
    path(
        "recuperar-contrasena/",
        auth_views.PasswordResetView.as_view(
            form_class=AccountPasswordResetForm,
            template_name="store/password-reset-form.html",
            email_template_name="store/emails/password-reset-email.txt",
            subject_template_name="store/emails/password-reset-subject.txt",
            success_url=reverse_lazy("password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "recuperar-contrasena/enviado/",
        auth_views.PasswordResetDoneView.as_view(template_name="store/password-reset-done.html"),
        name="password_reset_done",
    ),
    path(
        "restablecer/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="store/password-reset-confirm.html",
            success_url=reverse_lazy("password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "restablecer/completado/",
        auth_views.PasswordResetCompleteView.as_view(template_name="store/password-reset-complete.html"),
        name="password_reset_complete",
    ),
    path("account-register.html", views.register_view, name="register"),
    path(
        "confirmar-admin/<uidb64>/<token>/",
        views.admin_registration_confirm,
        name="admin_registration_confirm",
    ),
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
