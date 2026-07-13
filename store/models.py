from decimal import Decimal

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator


class Product(models.Model):
    class Audience(models.TextChoices):
        MEN = "men", "Hombre"
        WOMEN = "women", "Mujer"
        UNISEX = "unisex", "Unisex"

    class ProductType(models.TextChoices):
        FOOTWEAR = "footwear", "Calzado"
        ACCESSORY = "accessory", "Accesorio"

    slug = models.SlugField(max_length=120, unique=True)
    sku = models.CharField("referencia", max_length=80, blank=True, db_index=True)
    brand = models.CharField("marca", max_length=40)
    name = models.CharField("nombre", max_length=180)
    audience = models.CharField("seccion", max_length=12, choices=Audience.choices, default=Audience.UNISEX, db_index=True)
    product_type = models.CharField("tipo", max_length=12, choices=ProductType.choices, default=ProductType.FOOTWEAR, db_index=True)
    description = models.TextField("descripcion corta", blank=True, help_text="Texto principal junto al precio.")
    detailed_description = models.TextField("descripcion detallada", blank=True, help_text="Contenido de la pestaña Descripcion.")
    additional_information = models.TextField("informacion del producto", blank=True, help_text="Contenido de la pestaña Informacion.")
    price = models.DecimalField("precio de venta", max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField("precio anterior", max_digits=12, decimal_places=2, null=True, blank=True)
    image = models.CharField("imagen principal", max_length=255)
    image_alt = models.CharField("texto alternativo", max_length=180, blank=True)
    gallery = models.JSONField("galeria", default=list, blank=True)
    tags = models.JSONField("etiquetas", default=list, blank=True)
    sizes = models.JSONField("tallas", default=list, blank=True)
    colors = models.JSONField("colores", default=list, blank=True)
    weight_kg = models.DecimalField("peso en kg", max_digits=6, decimal_places=2, default=Decimal("1.00"), validators=(MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("30"))))
    stock = models.PositiveIntegerField("inventario", default=20)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["brand", "name"]

    def clean(self):
        super().clean()
        if self.compare_at_price is not None and self.compare_at_price <= self.price:
            raise ValidationError({"compare_at_price": "El precio anterior debe ser mayor al precio de venta."})

    @property
    def reference(self):
        return self.sku or self.slug.upper()

    @property
    def main_image_alt(self):
        return self.image_alt or self.name

    @property
    def product_images(self):
        images = [{"url": self.image, "alt": self.main_image_alt}]
        images.extend(
            {"url": item.get("url"), "alt": item.get("alt") or self.main_image_alt}
            for item in (self.gallery or [])
            if isinstance(item, dict) and item.get("url")
        )
        return images

    @property
    def has_discount(self):
        return self.compare_at_price is not None and self.compare_at_price > self.price

    @property
    def discount_percent(self):
        if not self.has_discount:
            return 0
        return round((self.compare_at_price - self.price) * 100 / self.compare_at_price)

    def __str__(self):
        return self.name


class BlogCategory(models.Model):
    name = models.CharField("nombre", max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        verbose_name = "categoría del blog"
        verbose_name_plural = "categorías del blog"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BlogPost(models.Model):
    category = models.ForeignKey(BlogCategory, verbose_name="categoría", on_delete=models.PROTECT, related_name="posts")
    title = models.CharField("título", max_length=180)
    slug = models.SlugField(max_length=200, unique=True)
    summary = models.TextField("resumen", max_length=360)
    content = models.TextField("contenido")
    image = models.CharField("imagen", max_length=255)
    image_alt = models.CharField("texto alternativo de la imagen", max_length=180)
    author = models.CharField("autor", max_length=100, default="Equipo Juaco Store")
    tags = models.JSONField("etiquetas", default=list, blank=True)
    reading_time = models.PositiveSmallIntegerField("minutos de lectura", default=4)
    published_at = models.DateTimeField("fecha de publicación")
    is_published = models.BooleanField("publicar", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "artículo"
        verbose_name_plural = "artículos"
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

class HomeBanner(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Imagen"
        VIDEO = "video", "Video corto"

    class Layout(models.TextChoices):
        EDITORIAL = "editorial", "Estilo actual"
        FLAT = "flat", "Imagen o video plano"

    name = models.CharField("nombre interno", max_length=120)
    title = models.CharField("titulo", max_length=180, blank=True)
    subtitle = models.CharField("comentario", max_length=280, blank=True)
    eyebrow = models.CharField("texto decorativo", max_length=80, blank=True)
    media_type = models.CharField("tipo de medio", max_length=10, choices=MediaType.choices, default=MediaType.IMAGE)
    layout = models.CharField("estilo", max_length=12, choices=Layout.choices, default=Layout.EDITORIAL)
    media_file = models.FileField("archivo de imagen o video", upload_to="marketing/banners/", blank=True, validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp", "mp4", "webm")),), help_text="Puedes subir JPG, PNG, WebP, MP4 o WebM de hasta 10 segundos.")
    media_url = models.CharField("URL de imagen o video", max_length=500, blank=True, help_text="Alternativa al archivo: pega una URL o ruta existente.")
    background_url = models.CharField("URL de fondo", max_length=500, blank=True, default="assets/img/shape/1.webp")
    button_label = models.CharField("texto del boton", max_length=60, blank=True)
    button_url = models.CharField("URL del boton", max_length=500, blank=True, help_text="Puede apuntar a una URL, seccion o video.")
    position = models.PositiveSmallIntegerField("orden", default=0)
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "banner del inicio"
        verbose_name_plural = "banners del inicio"
        ordering = ("position", "id")

    def clean(self):
        super().clean()
        if not self.media_file and not self.media_url:
            raise ValidationError("Debes subir un archivo o indicar una URL para el banner.")

    @property
    def media_source(self):
        return self.media_file.url if self.media_file else self.media_url

    def __str__(self):
        return self.name


class MarketingPopup(models.Model):
    class ImagePosition(models.TextChoices):
        LEFT = "left", "Izquierda"
        RIGHT = "right", "Derecha"

    name = models.CharField("nombre interno", max_length=120)
    title = models.CharField("titulo", max_length=180)
    message = models.TextField("mensaje", max_length=600)
    image_file = models.FileField("imagen", upload_to="marketing/popups/", blank=True, validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp")),))
    image_url = models.CharField("URL de imagen", max_length=500, blank=True)
    image_position = models.CharField("posicion de imagen", max_length=8, choices=ImagePosition.choices, default=ImagePosition.LEFT)
    button_label = models.CharField("texto del boton", max_length=60)
    button_url = models.CharField("URL del boton", max_length=500)
    delay_seconds = models.PositiveSmallIntegerField("espera antes de mostrar", default=2, validators=(MaxValueValidator(30),), help_text="Entre 0 y 30 segundos.")
    position = models.PositiveSmallIntegerField("prioridad", default=0)
    is_active = models.BooleanField("activo", default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "popup promocional"
        verbose_name_plural = "popups promocionales"
        ordering = ("position", "-updated_at")

    def clean(self):
        super().clean()
        if not self.image_file and not self.image_url:
            raise ValidationError("Debes subir una imagen o indicar una URL para el popup.")

    @property
    def image_source(self):
        return self.image_file.url if self.image_file else self.image_url

    def __str__(self):
        return self.name

class ContactRequest(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Nueva"
        IN_PROGRESS = "in_progress", "En proceso"
        RESOLVED = "resolved", "Resuelta"

    name = models.CharField("nombre", max_length=140)
    email = models.EmailField("correo")
    phone = models.CharField("telefono", max_length=30, blank=True)
    subject = models.CharField("asunto", max_length=180, blank=True)
    message = models.TextField("mensaje")
    channel = models.CharField("canal", max_length=30, default="Formulario web")
    status = models.CharField("estado", max_length=16, choices=Status.choices, default=Status.NEW, db_index=True)
    admin_notes = models.TextField("notas internas", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "peticion de atencion"
        verbose_name_plural = "peticiones de atencion"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} - {self.subject or 'Consulta'}"


class BlogComment(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name="comments")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies", verbose_name="respuesta a")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="blog_comments")
    name = models.CharField("nombre", max_length=140)
    email = models.EmailField("correo")
    body = models.TextField("comentario", max_length=2000)
    admin_response = models.TextField("respuesta de Juaco Store", blank=True)
    responded_at = models.DateTimeField("fecha de respuesta", null=True, blank=True, editable=False)
    is_approved = models.BooleanField("aprobado", default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "comentario del blog"
        verbose_name_plural = "comentarios del blog"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.name} en {self.post.title}"


class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="product_reviews")
    name = models.CharField("nombre", max_length=140)
    email = models.EmailField("correo")
    rating = models.PositiveSmallIntegerField("calificacion", validators=(MinValueValidator(1), MaxValueValidator(5)))
    recommends = models.BooleanField("recomienda el producto", default=True)
    title = models.CharField("titulo", max_length=180)
    body = models.TextField("resena", max_length=2000)
    admin_response = models.TextField("respuesta de Juaco Store", blank=True)
    responded_at = models.DateTimeField("fecha de respuesta", null=True, blank=True, editable=False)
    is_approved = models.BooleanField("aprobada", default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "resena de producto"
        verbose_name_plural = "resenas de productos"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.product.name}: {self.title}"

class CustomerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="customer_profile")
    document_number = models.CharField("numero de cedula", max_length=30, blank=True, db_index=True)
    phone = models.CharField("telefono de contacto", max_length=30, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "perfil de cliente"
        verbose_name_plural = "perfiles de clientes"

    def __str__(self):
        return f"Perfil de {self.user.get_username()}"

class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    first_name = models.CharField("nombre", max_length=80)
    last_name = models.CharField("apellidos", max_length=80)
    address_line_1 = models.CharField("dirección", max_length=180)
    address_line_2 = models.CharField("complemento", max_length=180, blank=True)
    department = models.CharField("departamento", max_length=80)
    city = models.CharField("ciudad", max_length=80)
    postal_code = models.CharField("código postal", max_length=12, blank=True)
    phone = models.CharField("teléfono", max_length=30)
    label = models.CharField("nombre de la dirección", max_length=40, default="Dirección de envío")
    is_default = models.BooleanField("dirección principal", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "dirección"
        verbose_name_plural = "direcciones"
        ordering = ["-is_default", "-updated_at"]

    @property
    def recipient_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.label} · {self.recipient_name}"

class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_user_favorite_product")]

    def __str__(self):
        return f"{self.user} · {self.product}"

class Coupon(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Porcentaje"
        FIXED = "fixed", "Valor fijo"

    code = models.CharField("codigo", max_length=40, unique=True)
    discount_type = models.CharField("tipo de descuento", max_length=12, choices=DiscountType.choices, default=DiscountType.PERCENTAGE)
    value = models.DecimalField("valor", max_digits=12, decimal_places=2, validators=(MinValueValidator(Decimal("0.01")),))
    minimum_purchase = models.DecimalField("compra minima", max_digits=12, decimal_places=2, default=Decimal("0"))
    starts_at = models.DateTimeField("inicio de vigencia")
    expires_at = models.DateTimeField("fecha de expiracion")
    usage_limit = models.PositiveIntegerField("limite total de usos", null=True, blank=True)
    times_used = models.PositiveIntegerField("veces canjeado", default=0, editable=False)
    once_per_user = models.BooleanField("un uso por usuario", default=True)
    is_active = models.BooleanField("activo", default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cupon"
        verbose_name_plural = "cupones"
        ordering = ("-created_at",)

    def clean(self):
        super().clean()
        if self.expires_at and self.starts_at and self.expires_at <= self.starts_at:
            raise ValidationError("La fecha de expiracion debe ser posterior al inicio de vigencia.")
        if self.discount_type == self.DiscountType.PERCENTAGE and self.value > 100:
            raise ValidationError("El porcentaje de descuento no puede superar el 100%.")

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def discount_for(self, subtotal):
        subtotal = Decimal(subtotal)
        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = subtotal * self.value / Decimal("100")
        else:
            discount = self.value
        return min(subtotal, discount).quantize(Decimal("0.01"))

    def __str__(self):
        return self.code

class Cart(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        CONVERTED = "converted", "Convertido"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="carts")
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def subtotal(self):
        return sum((item.subtotal for item in self.items.select_related("product")), Decimal("0"))

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    def __str__(self):
        owner = self.user_id or self.session_key or "sin propietario"
        return f"Carrito {self.pk} - {owner}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    size = models.CharField(max_length=12, blank=True)
    color = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["cart", "product", "size", "color"], name="unique_cart_product_variant")]

    @property
    def subtotal(self):
        return self.product.price * self.quantity

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente de pago"
        PAID = "paid", "Pagado"
        SHIPPED = "shipped", "Enviado"
        DELIVERED = "delivered", "Entregado"
        CANCELLED = "cancelled", "Cancelado"

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Transferencia bancaria"
        CASH_ON_DELIVERY = "cash_on_delivery", "Pago contra entrega"
        BOLD = "bold", "Pago con Bold"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    number = models.CharField("número de pedido", max_length=20, unique=True, editable=False)
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment_method = models.CharField("método de pago", max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER)

    # Snapshot de la dirección de envío (para que el historial no cambie si se edita/elimina la dirección)
    recipient_name = models.CharField("destinatario", max_length=161)
    phone = models.CharField("teléfono", max_length=30)
    address_line_1 = models.CharField("dirección", max_length=180)
    address_line_2 = models.CharField("complemento", max_length=180, blank=True)
    department = models.CharField("departamento", max_length=80)
    city = models.CharField("ciudad", max_length=80)
    postal_code = models.CharField("código postal", max_length=12, blank=True)

    subtotal = models.DecimalField("subtotal", max_digits=12, decimal_places=2)
    shipping_cost = models.DecimalField("costo de envío", max_digits=12, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField("total", max_digits=12, decimal_places=2)
    coupon = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", verbose_name="cupon")
    coupon_code = models.CharField("codigo de cupon", max_length=40, blank=True)
    discount_amount = models.DecimalField("descuento", max_digits=12, decimal_places=2, default=Decimal("0"))
    purchase_value = models.DecimalField("valor de compra", max_digits=12, decimal_places=2, null=True, blank=True)
    sale_value = models.DecimalField("valor de venta", max_digits=12, decimal_places=2, null=True, blank=True)
    notes = models.TextField("notas del pedido", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-created_at"]

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def full_address(self):
        parts = [self.address_line_1]
        if self.address_line_2:
            parts.append(self.address_line_2)
        parts.append(f"{self.city}, {self.department}")
        if self.postal_code:
            parts.append(self.postal_code)
        return " · ".join(parts)

    @property
    def gross_profit(self):
        if self.purchase_value is None or self.sale_value is None:
            return None
        return self.sale_value - self.purchase_value

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    product_name = models.CharField("producto", max_length=180)
    product_image = models.CharField("imagen", max_length=255, blank=True)
    unit_price = models.DecimalField("precio unitario", max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField("cantidad", default=1)
    size = models.CharField("talla", max_length=12, blank=True)
    color = models.CharField("color", max_length=60, blank=True)

    class Meta:
        verbose_name = "artículo del pedido"
        verbose_name_plural = "artículos del pedido"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

class CouponRedemption(models.Model):
    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="coupon_redemptions")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="coupon_redemption")
    discount_amount = models.DecimalField("descuento aplicado", max_digits=12, decimal_places=2)
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "canje de cupon"
        verbose_name_plural = "canjes de cupones"
        ordering = ("-redeemed_at",)

    def __str__(self):
        return f"{self.coupon.code} - {self.order.number}"