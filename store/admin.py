from django.contrib import admin, messages
from django.utils import timezone

from .forms import ProductAdminForm
from .models import Address, BlogCategory, BlogComment, BlogPost, Cart, CartItem, ContactRequest, Coupon, CouponRedemption, CustomerProfile, Favorite, HomeBanner, MarketingPopup, NewsletterSubscription, Order, OrderItem, Product, ProductReview
from .stockx import StockXLookupError, StockXNotConfigured, lookup_release_date


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    prepopulated_fields = {"slug": ("name",)}
    list_display = ("name", "sku", "brand", "release_date", "audience", "collection", "product_type", "price", "stock", "is_active")
    list_filter = ("audience", "collection", "product_type", "brand", "is_active")
    search_fields = ("name", "brand", "sku", "slug", "description", "tags")
    readonly_fields = ("release_date_source", "stockx_product_id", "release_date_checked_at", "created_at")
    fieldsets = (
        ("Identidad y publicacion", {"fields": ("name", "slug", "sku", "brand", "audience", "collection", "product_type", "is_active")}),
        ("Lanzamiento", {
            "fields": ("release_date", "lookup_release_date", "release_date_source", "stockx_product_id", "release_date_checked_at"),
            "description": "Puedes escribir la fecha manualmente o dejarla vacía y consultar StockX usando la referencia.",
        }),
        ("Contenido de la ficha", {"fields": ("description", "additional_information", "detailed_description")}),
        ("Precio e inventario", {"fields": ("price", "compare_at_price", "stock", "weight_kg")}),
        ("Imagenes", {"fields": ("image", "image_alt", "gallery")}),
        ("Variaciones y clasificacion", {"fields": ("sizes", "colors", "tags")}),
        ("Auditoria", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def save_model(self, request, obj, form, change):
        manual_date_changed = "release_date" in form.changed_data
        lookup_requested = form.cleaned_data.get("lookup_release_date", False)

        if manual_date_changed and obj.release_date:
            obj.release_date_source = Product.ReleaseDateSource.MANUAL
        elif manual_date_changed and not obj.release_date:
            obj.release_date_source = Product.ReleaseDateSource.UNKNOWN

        if lookup_requested and not (manual_date_changed and obj.release_date):
            try:
                result = lookup_release_date(obj.sku)
            except StockXNotConfigured:
                self.message_user(
                    request,
                    "Producto guardado sin consulta externa: StockX aún no está configurado. Puedes usar la fecha manual.",
                    level=messages.WARNING,
                )
            except StockXLookupError as exc:
                self.message_user(request, f"No fue posible consultar StockX: {exc}", level=messages.WARNING)
            else:
                obj.release_date_checked_at = timezone.now()
                if result:
                    obj.release_date = result.release_date
                    obj.release_date_source = Product.ReleaseDateSource.STOCKX
                    obj.stockx_product_id = result.product_id
                    self.message_user(
                        request,
                        f"Lanzamiento completado desde StockX: {result.release_date:%d/%m/%Y}.",
                        level=messages.SUCCESS,
                    )
                else:
                    self.message_user(
                        request,
                        "StockX no encontró una coincidencia exacta para esa referencia. Ingresa la fecha manualmente.",
                        level=messages.WARNING,
                    )

        super().save_model(request, obj, form, change)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "status", "updated_at")
    list_filter = ("status",)
    inlines = [CartItemInline]


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "published_at", "is_published")
    list_filter = ("category", "is_published")
    search_fields = ("title", "summary", "content", "tags")
    list_editable = ("is_published",)
    prepopulated_fields = {"slug": ("title",)}
    date_hierarchy = "published_at"

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "document_number", "phone", "updated_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "document_number", "phone")
    autocomplete_fields = ("user",)
@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__username", "user__email", "product__name", "product__slug")
    autocomplete_fields = ("user", "product")

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("label", "recipient_name", "city", "department", "phone", "is_default", "user")
    list_filter = ("is_default", "department")
    search_fields = ("first_name", "last_name", "address_line_1", "city", "user__username", "user__email")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "product_image", "unit_price", "quantity", "size")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "user", "recipient_name", "purchase_value", "sale_value", "discount_amount", "gross_profit_display", "status", "payment_method", "delivery_method", "fulfillment_status", "created_at")
    list_filter = ("status", "payment_method", "delivery_method", "fulfillment_status", "created_at")
    list_editable = ("purchase_value", "sale_value", "status", "fulfillment_status")
    search_fields = ("number", "recipient_name", "user__username", "user__email", "city")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    readonly_fields = (
        "number", "user", "recipient_name", "phone", "address_line_1", "address_line_2",
        "department", "city", "postal_code", "subtotal", "shipping_cost", "coupon", "coupon_code", "discount_amount", "total", "notes",
        "created_at", "updated_at",
    )

    @admin.display(description="utilidad bruta")
    def gross_profit_display(self, obj):
        return obj.gross_profit

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "value", "minimum_purchase", "starts_at", "expires_at", "times_used", "usage_limit", "is_active")
    list_filter = ("discount_type", "is_active", "once_per_user", "starts_at", "expires_at")
    list_editable = ("is_active",)
    search_fields = ("code",)
    readonly_fields = ("times_used", "created_at", "updated_at")
    date_hierarchy = "expires_at"


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "user", "order", "discount_amount", "redeemed_at")
    list_filter = ("coupon", "redeemed_at")
    search_fields = ("coupon__code", "user__username", "user__email", "order__number")
    readonly_fields = ("coupon", "user", "order", "discount_amount", "redeemed_at")
    date_hierarchy = "redeemed_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(HomeBanner)
class HomeBannerAdmin(admin.ModelAdmin):
    list_display = ("name", "media_type", "layout", "position", "is_active", "updated_at")
    list_filter = ("media_type", "layout", "is_active")
    list_editable = ("position", "is_active")
    search_fields = ("name", "title", "subtitle", "button_label", "button_url")
    ordering = ("position", "id")


@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "subscribed_at", "updated_at")
    list_filter = ("is_active", "subscribed_at")
    list_editable = ("is_active",)
    search_fields = ("email",)
    readonly_fields = ("subscribed_at", "updated_at")
    date_hierarchy = "subscribed_at"

@admin.register(MarketingPopup)
class MarketingPopupAdmin(admin.ModelAdmin):
    list_display = ("name", "title", "image_position", "button_label", "position", "is_active", "updated_at")
    list_filter = ("image_position", "is_active")
    list_editable = ("position", "is_active")
    search_fields = ("name", "title", "message", "button_label", "button_url")
    ordering = ("position", "-updated_at")

@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "subject", "channel", "status", "created_at")
    list_filter = ("status", "channel", "created_at")
    list_editable = ("status",)
    search_fields = ("name", "email", "phone", "subject", "message")
    readonly_fields = ("name", "email", "phone", "subject", "message", "channel", "created_at", "updated_at")
    date_hierarchy = "created_at"


@admin.register(BlogComment)
class BlogCommentAdmin(admin.ModelAdmin):
    list_display = ("name", "post", "parent", "has_response", "is_approved", "created_at")
    list_filter = ("is_approved", "created_at", "post")
    list_editable = ("is_approved",)
    search_fields = ("name", "email", "body", "admin_response", "post__title")
    date_hierarchy = "created_at"
    readonly_fields = ("responded_at", "created_at")

    @admin.display(boolean=True, description="respondido")
    def has_response(self, obj):
        return bool(obj.admin_response)

    def save_model(self, request, obj, form, change):
        if obj.admin_response.strip():
            obj.responded_at = timezone.now()
            obj.is_approved = True
        else:
            obj.responded_at = None
        super().save_model(request, obj, form, change)


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "name", "rating", "recommends", "title", "has_response", "is_approved", "created_at")
    list_filter = ("is_approved", "recommends", "rating", "created_at", "product")
    list_editable = ("is_approved",)
    search_fields = ("product__name", "name", "email", "title", "body", "admin_response")
    date_hierarchy = "created_at"
    readonly_fields = ("responded_at", "created_at")

    @admin.display(boolean=True, description="respondida")
    def has_response(self, obj):
        return bool(obj.admin_response)

    def save_model(self, request, obj, form, change):
        if obj.admin_response.strip():
            obj.responded_at = timezone.now()
            obj.is_approved = True
        else:
            obj.responded_at = None
        super().save_model(request, obj, form, change)

admin.site.site_header = "Juaco Store - Administracion"
admin.site.site_title = "Juaco Store Admin"
admin.site.index_title = "Ediciones y operaciones"
