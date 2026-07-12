from decimal import Decimal

from django.conf import settings
from django.db import models


class Product(models.Model):
    slug = models.SlugField(max_length=120, unique=True)
    brand = models.CharField(max_length=40)
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    image = models.CharField(max_length=255)
    tags = models.JSONField("etiquetas", default=list, blank=True)
    sizes = models.JSONField(default=list, blank=True)
    stock = models.PositiveIntegerField(default=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["brand", "name"]

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["cart", "product", "size"], name="unique_cart_product_size")]

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

    class Meta:
        verbose_name = "artículo del pedido"
        verbose_name_plural = "artículos del pedido"

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
