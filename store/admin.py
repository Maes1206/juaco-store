from django.contrib import admin

from .models import Address, BlogCategory, BlogPost, Cart, CartItem, Favorite, Order, OrderItem, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "brand", "price", "stock", "is_active")
    list_filter = ("brand", "is_active")
    search_fields = ("name", "slug")


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
    list_display = ("number", "user", "recipient_name", "city", "total", "status", "payment_method", "created_at")
    list_filter = ("status", "payment_method", "created_at")
    list_editable = ("status",)
    search_fields = ("number", "recipient_name", "user__username", "user__email", "city")
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    readonly_fields = (
        "number", "user", "recipient_name", "phone", "address_line_1", "address_line_2",
        "department", "city", "postal_code", "subtotal", "shipping_cost", "total", "notes",
        "created_at", "updated_at",
    )
