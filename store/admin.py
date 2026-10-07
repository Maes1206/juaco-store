from django.contrib import admin, messages
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .forms import ProductAdminForm
from .models import Address, BlogCategory, BlogComment, BlogPost, Cart, CartItem, ContactRequest, Coupon, CouponRedemption, CustomerProfile, Favorite, HomeBanner, MarketingPopup, NewsletterSubscription, Order, OrderItem, OrderStatusHistory, Product, ProductImage, ProductReview, ProductVariant, StoreSection
from .services import OrderTransitionError, transition_order
from .stockx import StockXLookupError, StockXNotConfigured, lookup_release_date


@admin.register(StoreSection)
class StoreSectionAdmin(admin.ModelAdmin):
    list_display = ("title", "section_type", "slug", "product_count", "position", "is_active", "updated_at")
    list_filter = ("section_type", "is_active")
    list_editable = ("position", "is_active")
    search_fields = ("title", "slug", "description", "empty_title", "empty_description")
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    ordering = ("position", "title")
    fieldsets = (
        ("Identidad y navegación", {"fields": ("section_type", "title", "slug", "description", "position", "is_active")}),
        ("Banner de la sección", {"fields": ("banner_image_file", "banner_image_url", "banner_image_alt")}),
        ("Estado vacío", {"fields": ("empty_image_file", "empty_image_url", "empty_image_alt", "empty_title", "empty_description")}),
        ("Auditoría", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _product_count=(
                Count("products", distinct=True)
                + Count("brand_products", distinct=True)
            ),
        )

    @admin.display(description="productos", ordering="_product_count")
    def product_count(self, obj):
        return obj._product_count


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    min_num = 1
    validate_min = True
    fields = ("sku", "size", "color_name", "color_hex", "stock", "is_active", "updated_at")
    readonly_fields = ("updated_at",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image_file", "image_alt", "position")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductAdminForm
    prepopulated_fields = {"slug": ("name",)}
    list_display = ("name", "sku", "brand", "release_date", "audience", "collection", "product_type", "section_names", "price", "stock", "is_on_sale", "is_active")
    list_filter = ("audience", "collection", "product_type", "brand", "store_sections", "is_on_sale", "is_active")
    search_fields = ("name", "brand__title", "sku", "slug", "description", "tags", "store_sections__title")
    filter_horizontal = ("store_sections",)
    readonly_fields = ("release_date_source", "stockx_product_id", "release_date_checked_at", "created_at")
    inlines = (ProductImageInline, ProductVariantInline)
    fieldsets = (
        ("Identidad y publicación", {"fields": ("name", "slug", "sku", "is_active")}),
        ("Dónde se muestra", {
            "fields": ("brand", "audience", "collection", "product_type", "is_on_sale", "store_sections"),
            "description": "Elige la marca y todas las secciones del sitio donde debe aparecer el producto. La marca es obligatoria; las secciones personalizadas permiten selección múltiple.",
        }),
        ("Lanzamiento", {
            "fields": ("release_date", "lookup_release_date", "release_date_source", "stockx_product_id", "release_date_checked_at"),
            "description": "Puedes escribir la fecha manualmente o dejarla vacía y consultar StockX usando la referencia.",
        }),
        ("Contenido de la ficha", {"fields": ("description", "additional_information", "detailed_description")}),
        ("Precio e inventario", {
            "fields": ("price", "compare_at_price", "stock", "weight_kg"),
            "description": "Si el producto ya tiene variantes de talla o color, el inventario que escribas aqui se reparte en partes iguales entre ellas. Para cantidades distintas por variante, ajusta cada una en Variantes de producto.",
        }),
        ("Imagenes", {
            "fields": ("image_file", "image", "image_alt", "gallery"),
            "description": "Sube la imagen principal y la galería inferior. Cada archivo se convierte automáticamente a WebP; las rutas se conservan como alternativa heredada.",
        }),
        ("Variaciones y clasificación", {
            "fields": ("sizes", "colors", "variant_stock", "tags"),
            "description": "Escribe aquí las tallas y colores: al guardar se crean las variantes que falten. El detalle por variante se ajusta abajo, en Variantes de producto.",
        }),
        ("Auditoria", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    @admin.display(description="secciones")
    def section_names(self, obj):
        return ", ".join(obj.store_sections.values_list("title", flat=True)) or "—"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("brand").prefetch_related("store_sections")

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        # El wrapper con el boton "+" se agrega aqui (no en formfield_for_foreignkey,
        # que corre antes de que exista RelatedFieldWidgetWrapper).
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "brand" and isinstance(formfield.widget, RelatedFieldWidgetWrapper):
            # El boton "+" abre el alta generica de StoreSection; sin esto queda
            # en "Sección personalizada" por defecto y hay que corregirla a mano.
            widget = formfield.widget
            original_get_context = widget.get_context

            def get_context(name, value, attrs, _original=original_get_context):
                context = _original(name, value, attrs)
                if context.get("can_add_related"):
                    context["url_params"] += "&section_type=brand"
                return context

            widget.get_context = get_context
        return formfield

    def save_model(self, request, obj, form, change):
        stock_changed = "stock" in form.changed_data
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

        if stock_changed:
            active_variants = list(obj.variants.filter(is_active=True))
            if active_variants:
                # Product.save() reparte obj.stock entre las variantes activas
                # cuando "stock" viene en update_fields; ver store/models.py.
                obj.save(update_fields=["stock"])
                self.message_user(
                    request,
                    f"Inventario ({obj.stock}) repartido en partes iguales entre {len(active_variants)} variante(s). "
                    "Ajusta cada una por separado en Variantes de producto si necesitas cantidades distintas.",
                    level=messages.SUCCESS,
                )

    def save_related(self, request, form, formsets, change):
        # Corre despues de los inlines para que una variante escrita a mano en la
        # tabla de abajo no se duplique con la que generan las tallas y colores.
        super().save_related(request, form, formsets, change)
        created, restored = self._sync_variants_with_summary(form)
        if created:
            self.message_user(
                request,
                f"Se crearon {created} variantes desde las tallas y colores. Revisa su inventario en Variantes de producto.",
                level=messages.SUCCESS,
            )
        if restored:
            self.message_user(request, f"Se reactivaron {restored} variantes que estaban ocultas.", level=messages.SUCCESS)

    @staticmethod
    def _sync_variants_with_summary(form):
        """Crea una variante por cada combinacion de talla y color escrita.

        Sin esto el producto mostraria tallas que no se pueden comprar: el
        inventario y el boton de compra salen de las variantes, no del resumen.
        Nunca borra nada; quitar una talla se sigue haciendo en el inline.
        """
        product = form.instance
        sizes = form.cleaned_data.get("sizes") or []
        colors = form.cleaned_data.get("colors") or []
        if not sizes and not colors:
            return 0, 0

        initial_stock = form.cleaned_data.get("variant_stock") or 0
        # Solo se reactiva cuando el administrador acaba de escribir la talla o el
        # color; de lo contrario se respetaria menos su decision de ocultarla.
        summary_edited = bool({"sizes", "colors"} & set(form.changed_data))
        existing = {
            (variant.size, variant.color_name.casefold()): variant
            for variant in product.variants.all()
        }

        created = restored = 0
        for size in (sizes or [""]):
            for color in (colors or [{"name": "", "hex": ""}]):
                key = (str(size), color["name"].casefold())
                variant = existing.get(key)
                if variant is None:
                    existing[key] = ProductVariant.objects.create(
                        product=product,
                        size=str(size),
                        color_name=color["name"],
                        color_hex=color.get("hex", ""),
                        stock=initial_stock,
                    )
                    created += 1
                elif summary_edited and not variant.is_active:
                    variant.is_active = True
                    variant.save()
                    restored += 1
        return created, restored


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("product", "sku", "size", "color_name", "stock", "is_active", "updated_at")
    list_filter = ("is_active", "product__brand", "size", "color_name")
    list_editable = ("stock", "is_active")
    search_fields = ("sku", "product__name", "product__sku", "size", "color_name")
    autocomplete_fields = ("product",)
    readonly_fields = ("created_at", "updated_at")


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    autocomplete_fields = ("product", "variant")


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
    readonly_fields = ("product", "variant", "variant_sku", "product_name", "product_image", "unit_price", "quantity", "size", "color")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ("created_at", "from_status", "to_status", "source", "changed_by", "note", "notification_sent_at")
    readonly_fields = fields
    can_delete = False
    verbose_name_plural = "Historial y auditoría de estados"

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "recipient_name", "status", "payment_method", "payment_status", "delivery_method", "carrier", "tracking_number", "total", "created_at")
    list_filter = ("status", "fulfillment_status", "payment_method", "payment_status", "delivery_method", "created_at")
    search_fields = ("number", "recipient_name", "user__username", "user__email", "city", "carrier", "tracking_number", "payment_reference", "payment_transaction_id")
    date_hierarchy = "created_at"
    list_select_related = ("user",)
    inlines = [OrderItemInline, OrderStatusHistoryInline]
    actions = ("mark_paid", "mark_preparing", "mark_shipped", "mark_delivered", "cancel_or_refund")
    readonly_fields = (
        "number", "user", "status", "fulfillment_status", "payment_method", "delivery_method", "recipient_name", "phone", "address_line_1", "address_line_2",
        "department", "city", "postal_code", "subtotal", "shipping_cost", "coupon", "coupon_code", "discount_amount", "total", "notes",
        "payment_reference", "payment_status", "payment_transaction_id", "payment_attempts", "paid_at",
        "stock_reserved", "shipped_at", "delivered_at", "confirmation_email_sent_at", "created_at", "updated_at",
    )
    fieldsets = (
        ("Estado operativo", {
            "fields": ("status", "fulfillment_status", "payment_method", "payment_status"),
            "description": "Usa las acciones del listado para avanzar el pedido. Las transiciones quedan registradas en el historial.",
        }),
        ("Despacho", {
            "fields": ("delivery_method", "carrier", "tracking_number", "dispatch_receipt", "shipped_at", "delivered_at"),
            "description": "La transportadora y la guía son obligatorias para despachos a domicilio. El comprobante PDF o imagen es opcional.",
        }),
        ("Cliente y entrega", {"fields": ("number", "user", "recipient_name", "phone", "address_line_1", "address_line_2", "department", "city", "postal_code", "notes")}),
        ("Valores históricos", {"fields": ("subtotal", "shipping_cost", "coupon", "coupon_code", "discount_amount", "total", "purchase_value", "sale_value")}),
        ("Pago e integridad", {"fields": ("payment_reference", "payment_transaction_id", "payment_attempts", "paid_at", "stock_reserved", "confirmation_email_sent_at"), "classes": ("collapse",)}),
        ("Auditoría", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(self.readonly_fields)
        if obj and obj.status != Order.Status.PENDING:
            fields.extend(("purchase_value", "sale_value"))
        return tuple(fields)

    def has_delete_permission(self, request, obj=None):
        return False

    def _transition_queryset(self, request, queryset, target_status, label):
        completed = 0
        for order in queryset.select_related("user"):
            destination = target_status(order) if callable(target_status) else target_status
            try:
                _, history = transition_order(
                    order,
                    destination,
                    actor=request.user,
                    source=OrderStatusHistory.Source.ADMIN,
                    note=f"Cambio realizado desde el panel: {label}.",
                    order_url=request.build_absolute_uri(reverse("order_detail", args=[order.number])),
                )
            except OrderTransitionError as exc:
                self.message_user(request, f"{order.number}: {exc}", level=messages.ERROR)
            else:
                if history is None:
                    continue
                completed += 1
        if completed:
            self.message_user(request, f"{completed} pedido(s) actualizado(s): {label}.", level=messages.SUCCESS)

    @admin.action(description="Confirmar pago de pedidos seleccionados")
    def mark_paid(self, request, queryset):
        self._transition_queryset(request, queryset, Order.Status.PAID, "pago confirmado")

    @admin.action(description="Pasar pedidos seleccionados a preparación")
    def mark_preparing(self, request, queryset):
        self._transition_queryset(request, queryset, Order.Status.PREPARING, "preparando")

    @admin.action(description="Marcar pedidos seleccionados como enviados")
    def mark_shipped(self, request, queryset):
        self._transition_queryset(request, queryset, Order.Status.SHIPPED, "enviado")

    @admin.action(description="Marcar pedidos seleccionados como entregados")
    def mark_delivered(self, request, queryset):
        self._transition_queryset(request, queryset, Order.Status.DELIVERED, "entregado")

    @admin.action(description="Cancelar o reembolsar pedidos seleccionados")
    def cancel_or_refund(self, request, queryset):
        self._transition_queryset(
            request,
            queryset,
            lambda order: Order.Status.CANCELLED if order.status == Order.Status.PENDING else Order.Status.REFUNDED,
            "cancelado o reembolsado",
        )

    @admin.display(description="utilidad bruta")
    def gross_profit_display(self, obj):
        return obj.gross_profit


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("order", "from_status", "to_status", "source", "changed_by", "created_at", "notification_sent_at")
    list_filter = ("to_status", "source", "created_at")
    search_fields = ("order__number", "changed_by__username", "note")
    readonly_fields = ("order", "from_status", "to_status", "source", "note", "changed_by", "notification_sent_at", "created_at")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in {"GET", "HEAD", "OPTIONS"}

    def has_delete_permission(self, request, obj=None):
        return False

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

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["admin_response"].label = "respuesta de Nexus Luxury Footwear"
        return form

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

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["admin_response"].label = "respuesta de Nexus Luxury Footwear"
        return form

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

admin.site.site_header = "Nexus Luxury Footwear - Administracion"
admin.site.site_title = "Nexus Luxury Footwear Admin"
admin.site.index_title = "Ediciones y operaciones"
