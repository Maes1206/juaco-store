import os
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator, RegexValidator
from django.db.models.functions import Lower
from PIL import Image, UnidentifiedImageError

from .colors import resolve_color_hex
from .image_optimization import IMAGE_EXTENSIONS, optimize_field_file, validate_image_upload


# Firmas mínimas de contenedor para los formatos de video aceptados. No hay una
# libreria de video en el proyecto, así que en vez de decodificar el archivo se
# comprueba su cabecera, igual que Pillow hace estructuralmente con imágenes.
_VIDEO_SIGNATURE_CHECKS = {
    "mp4": lambda header: header[4:8] == b"ftyp",
    "webm": lambda header: header.startswith(b"\x1a\x45\xdf\xa3"),
}
_IMAGE_EXTENSIONS = IMAGE_EXTENSIONS
_VIDEO_EXTENSIONS = frozenset(_VIDEO_SIGNATURE_CHECKS)
# Nginx corta las subidas en 20 MB. El limite propio se queda por debajo para
# que el administrador vea un mensaje del formulario y no un error 413 crudo.
MAX_VIDEO_UPLOAD_BYTES = 15 * 1024 * 1024
RESERVED_STORE_SECTION_SLUGS = {"hombre", "mujer", "clasicas", "ofertas", "accesorios"}


def media_extension(reference):
    """Extension de un archivo subido o de una ruta/URL, sin query ni punto."""
    name = getattr(reference, "name", reference) or ""
    return os.path.splitext(str(name).split("?")[0])[1].lstrip(".").lower()


def looks_like_video(reference):
    return media_extension(reference) in _VIDEO_EXTENSIONS


def validate_uploaded_media(file):
    """Verifica que el contenido de un archivo subido coincida con su extensión.

    FileExtensionValidator solo mira el nombre; un archivo con contenido
    distinto (por ejemplo HTML o un script disfrazado de "banner.jpg") pasaría
    esa comprobación igual. Aquí se abre y valida la firma real del archivo.
    """
    extension = os.path.splitext(file.name)[1].lstrip(".").lower()
    file.seek(0)
    try:
        if extension in _IMAGE_EXTENSIONS:
            validate_image_upload(file)
            return
        signature_check = _VIDEO_SIGNATURE_CHECKS.get(extension)
        if signature_check:
            if file.size > MAX_VIDEO_UPLOAD_BYTES:
                raise ValidationError(
                    f"El video no puede superar {MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)} MB. "
                    "Recorta el clip o bajale la calidad."
                )
            if not signature_check(file.read(12)):
                raise ValidationError("El archivo no tiene un formato de video válido.")
            return
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("El archivo no es una imagen válida.") from exc
    finally:
        file.seek(0)


def validate_dispatch_receipt(file):
    """Acepta comprobantes PDF o imagen, con contenido real y hasta 5 MB."""
    if file.size > 5 * 1024 * 1024:
        raise ValidationError("El comprobante de despacho no puede superar 5 MB.")
    extension = os.path.splitext(file.name)[1].lstrip(".").lower()
    file.seek(0)
    try:
        if extension == "pdf":
            if not file.read(5).startswith(b"%PDF-"):
                raise ValidationError("El archivo no es un PDF válido.")
        elif extension in _IMAGE_EXTENSIONS:
            with Image.open(file) as image:
                image.verify()
        else:
            raise ValidationError("Adjunta un PDF o una imagen JPG, PNG o WebP.")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("El comprobante no contiene una imagen válida.") from exc
    finally:
        file.seek(0)


class StoreSection(models.Model):
    class SectionType(models.TextChoices):
        BRAND = "brand", "Marca"
        CUSTOM = "custom", "Sección personalizada"

    section_type = models.CharField(
        "tipo de sección",
        max_length=12,
        choices=SectionType.choices,
        default=SectionType.CUSTOM,
        db_index=True,
        help_text="Las marcas aparecen automáticamente en el selector de productos.",
    )
    title = models.CharField("título", max_length=120, unique=True)
    slug = models.SlugField("identificador URL", max_length=130, unique=True)
    description = models.TextField("descripción", max_length=320)
    banner_image_file = models.FileField(
        "archivo del banner",
        upload_to="store/sections/banners/",
        blank=True,
        validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp")), validate_uploaded_media),
        help_text="Sube una imagen JPG, PNG o WebP. También puedes usar una URL en el campo siguiente.",
    )
    banner_image_url = models.CharField(
        "URL del banner",
        max_length=500,
        blank=True,
        help_text="Alternativa al archivo: pega una URL o ruta existente.",
    )
    banner_image_alt = models.CharField("texto alternativo del banner", max_length=180, blank=True)
    empty_image_file = models.FileField(
        "archivo de estado vacío",
        upload_to="store/sections/empty/",
        blank=True,
        validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp")), validate_uploaded_media),
        help_text="Imagen editorial que se muestra cuando la sección no tiene productos.",
    )
    empty_image_url = models.CharField(
        "URL de estado vacío",
        max_length=500,
        blank=True,
        help_text="Alternativa al archivo: pega una URL o ruta existente.",
    )
    empty_image_alt = models.CharField("texto alternativo de estado vacío", max_length=180, blank=True)
    empty_title = models.CharField(
        "título de estado vacío",
        max_length=180,
        blank=True,
        help_text="Si lo dejas vacío se generará automáticamente con el nombre de la sección.",
    )
    empty_description = models.TextField(
        "descripción de estado vacío",
        max_length=320,
        blank=True,
        help_text="Mensaje opcional que acompaña la imagen cuando todavía no hay productos.",
    )
    position = models.PositiveSmallIntegerField("orden en Tienda", default=0)
    is_active = models.BooleanField("visible en la tienda", default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "sección de la tienda"
        verbose_name_plural = "secciones de la tienda"
        ordering = ("position", "title", "id")

    def clean(self):
        super().clean()
        errors = {}
        if self.slug in RESERVED_STORE_SECTION_SLUGS:
            errors["slug"] = "Este identificador está reservado por una sección principal de la tienda."
        if not self.banner_image_file and not self.banner_image_url:
            errors["banner_image_file"] = "Sube un banner o indica una URL para el banner."
        if not self.empty_image_file and not self.empty_image_url:
            errors["empty_image_file"] = "Sube una imagen de estado vacío o indica una URL."
        if self.pk and self.section_type != self.SectionType.BRAND and self.brand_products.exists():
            errors["section_type"] = "No puedes cambiar esta marca mientras tenga productos asignados."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        optimize_field_file(self, "banner_image_file", max_size=(2400, 1400))
        optimize_field_file(self, "empty_image_file", max_size=(1600, 1600))
        super().save(*args, **kwargs)

    @property
    def banner_source(self):
        return self.banner_image_file.url if self.banner_image_file else self.banner_image_url

    @property
    def empty_image_source(self):
        return self.empty_image_file.url if self.empty_image_file else self.empty_image_url

    @property
    def resolved_empty_title(self):
        return self.empty_title or f"Aún no hemos agregado productos en {self.title}"

    @property
    def resolved_empty_description(self):
        return self.empty_description or "Cuando el equipo asigne productos a esta sección desde el panel administrativo, aparecerán automáticamente aquí."

    def __str__(self):
        return self.title


class Product(models.Model):
    class Audience(models.TextChoices):
        MEN = "men", "Hombre"
        WOMEN = "women", "Mujer"
        UNISEX = "unisex", "Unisex"

    class Collection(models.TextChoices):
        CLASSICS = "classics", "Clasicas"
        URBAN = "urban", "Urbanas"
        SPORT = "sport", "Deportivas"
        LIMITED = "limited", "Edicion limitada"

    class ProductType(models.TextChoices):
        FOOTWEAR = "footwear", "Calzado"
        ACCESSORY = "accessory", "Accesorio"

    class ReleaseDateSource(models.TextChoices):
        UNKNOWN = "", "Sin definir"
        MANUAL = "manual", "Ingresada manualmente"
        STOCKX = "stockx", "StockX"

    slug = models.SlugField(max_length=120, unique=True)
    sku = models.CharField("referencia", max_length=80, blank=True, db_index=True)
    release_date = models.DateField("fecha de lanzamiento", null=True, blank=True)
    release_date_source = models.CharField(
        "origen de la fecha",
        max_length=12,
        choices=ReleaseDateSource.choices,
        default=ReleaseDateSource.UNKNOWN,
        blank=True,
        editable=False,
    )
    stockx_product_id = models.CharField("ID de producto en StockX", max_length=80, blank=True, editable=False)
    release_date_checked_at = models.DateTimeField("última consulta de lanzamiento", null=True, blank=True, editable=False)
    legacy_brand = models.CharField("marca anterior", max_length=40, blank=True, default="", editable=False)
    brand = models.ForeignKey(
        StoreSection,
        on_delete=models.PROTECT,
        related_name="brand_products",
        limit_choices_to={"section_type": StoreSection.SectionType.BRAND},
        verbose_name="marca",
    )
    name = models.CharField("nombre", max_length=180)
    audience = models.CharField("seccion", max_length=12, choices=Audience.choices, default=Audience.UNISEX, db_index=True)
    product_type = models.CharField("tipo", max_length=12, choices=ProductType.choices, default=ProductType.FOOTWEAR, db_index=True)
    collection = models.CharField("coleccion", max_length=16, choices=Collection.choices, blank=True, db_index=True)
    description = models.TextField("descripcion corta", blank=True, help_text="Texto principal junto al precio.")
    detailed_description = models.TextField("descripcion detallada", blank=True, help_text="Contenido de la pestaña Descripcion.")
    additional_information = models.TextField("informacion del producto", blank=True, help_text="Contenido de la pestaña Informacion.")
    price = models.DecimalField("precio de venta", max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField("precio anterior", max_digits=12, decimal_places=2, null=True, blank=True)
    image_file = models.FileField(
        "archivo de imagen principal",
        upload_to="products/main/",
        blank=True,
        validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp")), validate_uploaded_media),
        help_text="Se redimensiona y convierte automáticamente a WebP.",
    )
    image = models.CharField(
        "URL o ruta de imagen principal",
        max_length=255,
        blank=True,
        help_text="Alternativa al archivo subido para imágenes externas o heredadas.",
    )
    image_alt = models.CharField("texto alternativo", max_length=180, blank=True)
    gallery = models.JSONField("galeria", default=list, blank=True)
    tags = models.JSONField("etiquetas", default=list, blank=True)
    sizes = models.JSONField("tallas", default=list, blank=True)
    colors = models.JSONField("colores", default=list, blank=True)
    store_sections = models.ManyToManyField(
        StoreSection,
        verbose_name="secciones personalizadas de Tienda",
        related_name="products",
        blank=True,
        help_text="Selecciona una o varias secciones dinámicas en las que debe aparecer el producto.",
    )
    weight_kg = models.DecimalField("peso en kg", max_digits=6, decimal_places=2, default=Decimal("1.00"), validators=(MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("30"))))
    stock = models.PositiveIntegerField("inventario", default=0)
    is_on_sale = models.BooleanField(
        "mostrar en Ofertas",
        default=False,
        db_index=True,
        help_text="Activa esta opcion para publicar el producto en la seccion Ofertas.",
    )
    is_active = models.BooleanField("activo", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["brand__title", "name"]

    def clean(self):
        super().clean()
        if not self.image_file and not self.image:
            raise ValidationError({"image_file": "Sube una imagen principal o indica una URL."})
        if self.brand_id and self.brand.section_type != StoreSection.SectionType.BRAND:
            raise ValidationError({"brand": "Selecciona una sección configurada como marca."})
        if self.compare_at_price is not None and self.compare_at_price <= self.price:
            raise ValidationError({"compare_at_price": "El precio anterior debe ser mayor al precio de venta."})

    def save(self, *args, **kwargs):
        optimize_field_file(self, "image_file", max_size=(1600, 1600))
        update_fields = kwargs.get("update_fields")
        if self.brand_id:
            self.legacy_brand = self.brand.title
            if update_fields and "brand" in update_fields:
                kwargs["update_fields"] = tuple(set(update_fields) | {"legacy_brand"})
        super().save(*args, **kwargs)
        if update_fields and "stock" in update_fields:
            active_variants = list(self.variants.filter(is_active=True).order_by("id"))
            if active_variants:
                base_stock, remainder = divmod(self.stock, len(active_variants))
                for index, variant in enumerate(active_variants):
                    variant.stock = base_stock + (1 if index < remainder else 0)
                ProductVariant.objects.bulk_update(active_variants, ("stock",))

    @property
    def reference(self):
        return self.sku or self.slug.upper()

    @property
    def release_year(self):
        return self.release_date.year if self.release_date else None

    @property
    def main_image_alt(self):
        return self.image_alt or self.name

    @property
    def main_image_source(self):
        return self.image_file.url if self.image_file else self.image

    @property
    def product_images(self):
        images = [{"url": self.main_image_source, "alt": self.main_image_alt}]
        images.extend(
            {"url": item.image_file.url, "alt": item.image_alt or self.main_image_alt}
            for item in self.uploaded_images.all()
            if item.image_file
        )
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


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="uploaded_images",
        verbose_name="producto",
    )
    image_file = models.FileField(
        "archivo",
        upload_to="products/gallery/",
        validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp")), validate_uploaded_media),
        help_text="Se redimensiona y convierte automáticamente a WebP.",
    )
    image_alt = models.CharField("texto alternativo", max_length=180, blank=True)
    position = models.PositiveSmallIntegerField("orden", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "imagen de producto"
        verbose_name_plural = "imágenes de producto"
        ordering = ("position", "id")

    def save(self, *args, **kwargs):
        optimize_field_file(self, "image_file", max_size=(1600, 1600))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} · imagen {self.position + 1}"


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants", verbose_name="producto")
    sku = models.CharField("referencia de variante", max_length=100, unique=True, null=True, blank=True)
    size = models.CharField("talla", max_length=12, blank=True)
    color_name = models.CharField("color", max_length=60, blank=True)
    color_hex = models.CharField(
        "código de color",
        max_length=7,
        blank=True,
        help_text="Opcional: si escribes un color y lo dejas vacío, se usará #505050 por defecto.",
        validators=(RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Usa un color hexadecimal como #505050."),),
    )
    stock = models.PositiveIntegerField("existencias", default=0)
    is_active = models.BooleanField("disponible", default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "variante de producto"
        verbose_name_plural = "variantes de producto"
        ordering = ("product", "size", "color_name", "id")
        constraints = (
            models.UniqueConstraint(
                fields=("product", "size", "color_name"),
                name="unique_product_size_color_variant",
            ),
        )

    def clean(self):
        super().clean()
        self.size = self.size.strip()
        self.color_name = self.color_name.strip()
        self.color_hex = self.color_hex.strip().upper()
        if self.color_hex and not self.color_name:
            raise ValidationError({"color_name": "Indica el nombre de este color."})
        if self.color_name and not self.color_hex:
            # El hexadecimal es opcional: se deduce del nombre y, si no se
            # reconoce, del color dominante de la foto del producto.
            self.color_hex = resolve_color_hex(
                self.color_name,
                product=self.product if self.product_id else None,
            )

    @classmethod
    def sync_product_summary(cls, product_id):
        variants = list(cls.objects.filter(product_id=product_id, is_active=True).order_by("id"))
        sizes = []
        colors = []
        for variant in variants:
            if variant.size and variant.size not in sizes:
                sizes.append(variant.size)
            if variant.color_name and not any(
                item["name"].casefold() == variant.color_name.casefold() for item in colors
            ):
                colors.append({
                    "name": variant.color_name,
                    "hex": variant.color_hex or resolve_color_hex(variant.color_name, product=variant.product),
                })
        Product.objects.filter(pk=product_id).update(
            sizes=sizes,
            colors=colors,
            stock=sum(variant.stock for variant in variants),
        )

    def save(self, *args, **kwargs):
        previous_product_id = None
        if self.pk:
            previous_product_id = type(self).objects.filter(pk=self.pk).values_list("product_id", flat=True).first()
        self.full_clean()
        super().save(*args, **kwargs)
        self.sync_product_summary(self.product_id)
        if previous_product_id and previous_product_id != self.product_id:
            self.sync_product_summary(previous_product_id)
        self.cart_items.update(product_id=self.product_id, size=self.size, color=self.color_name)

    def delete(self, *args, **kwargs):
        product_id = self.product_id
        result = super().delete(*args, **kwargs)
        self.sync_product_summary(product_id)
        return result

    @property
    def label(self):
        details = " / ".join(value for value in (self.size, self.color_name) if value)
        return details or "Única"

    def __str__(self):
        return f"{self.product.name} · {self.label}"


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
    media_file = models.FileField("archivo de imagen o video", upload_to="marketing/banners/", blank=True, validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp", "mp4", "webm")), validate_uploaded_media), help_text="Las imágenes se redimensionan y convierten a WebP. También puedes subir MP4 o WebM de hasta 10 segundos.")
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
        # El tipo se deduce del archivo en vez de confiar en el desplegable: si
        # se sube un MP4 y queda seleccionado "Imagen", el banner saldria como
        # una <img> rota. Una URL sin extension conserva la eleccion manual.
        if self.media_file:
            self.media_type = self.MediaType.VIDEO if looks_like_video(self.media_file.name) else self.MediaType.IMAGE
        elif looks_like_video(self.media_url):
            self.media_type = self.MediaType.VIDEO

    def save(self, *args, **kwargs):
        # Los videos se guardan tal cual: optimize_field_file solo sabe de imagenes.
        if self.media_file and media_extension(self.media_file) in _IMAGE_EXTENSIONS:
            optimize_field_file(self, "media_file", max_size=(2400, 1400))
        super().save(*args, **kwargs)

    @property
    def media_source(self):
        return self.media_file.url if self.media_file else self.media_url

    def __str__(self):
        return self.name


class NewsletterSubscription(models.Model):
    email = models.EmailField("correo electrónico", unique=True)
    is_active = models.BooleanField("suscripción activa", default=True)
    subscribed_at = models.DateTimeField("fecha de suscripción", auto_now_add=True)
    updated_at = models.DateTimeField("última actualización", auto_now=True)

    class Meta:
        verbose_name = "suscripción al newsletter"
        verbose_name_plural = "suscripciones al newsletter"
        ordering = ("-subscribed_at",)

    def __str__(self):
        return self.email

class MarketingPopup(models.Model):
    class ImagePosition(models.TextChoices):
        LEFT = "left", "Izquierda"
        RIGHT = "right", "Derecha"

    name = models.CharField("nombre interno", max_length=120)
    title = models.CharField("titulo", max_length=180)
    message = models.TextField("mensaje", max_length=600)
    image_file = models.FileField(
        "imagen o video",
        upload_to="marketing/popups/",
        blank=True,
        validators=(FileExtensionValidator(("jpg", "jpeg", "png", "webp", "mp4", "webm")), validate_uploaded_media),
        help_text="Las imágenes se redimensionan y convierten a WebP. También puedes subir un MP4 o WebM corto.",
    )
    image_url = models.CharField("URL de imagen o video", max_length=500, blank=True)
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

    def save(self, *args, **kwargs):
        # Los videos se guardan tal cual: optimize_field_file solo sabe de imagenes.
        if self.image_file and media_extension(self.image_file) in _IMAGE_EXTENSIONS:
            optimize_field_file(self, "image_file", max_size=(1400, 1400))
        super().save(*args, **kwargs)

    @property
    def image_source(self):
        return self.image_file.url if self.image_file else self.image_url

    @property
    def is_video(self):
        """El tipo se deduce del archivo, sin un campo aparte que se desincronice."""
        return looks_like_video(self.image_file.name if self.image_file else self.image_url)

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
    minimum_purchase = models.DecimalField(
        "compra minima",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        validators=(MinValueValidator(Decimal("0")),),
    )
    starts_at = models.DateTimeField("inicio de vigencia")
    expires_at = models.DateTimeField("fecha de expiracion")
    usage_limit = models.PositiveIntegerField(
        "limite total de usos",
        null=True,
        blank=True,
        validators=(MinValueValidator(1),),
    )
    times_used = models.PositiveIntegerField("veces canjeado", default=0, editable=False)
    once_per_user = models.BooleanField("un uso por usuario", default=True)
    is_active = models.BooleanField("activo", default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cupon"
        verbose_name_plural = "cupones"
        ordering = ("-created_at",)
        constraints = (
            models.UniqueConstraint(Lower("code"), name="unique_coupon_code_ci"),
            models.CheckConstraint(
                condition=models.Q(minimum_purchase__gte=0),
                name="coupon_minimum_purchase_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(value__gt=0),
                name="coupon_value_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_type="fixed") | models.Q(value__lte=100),
                name="coupon_percentage_at_most_100",
            ),
            models.CheckConstraint(
                condition=models.Q(expires_at__gt=models.F("starts_at")),
                name="coupon_expiry_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(usage_limit__isnull=True) | models.Q(usage_limit__gte=1),
                name="coupon_usage_limit_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(usage_limit__isnull=True) | models.Q(usage_limit__gte=models.F("times_used")),
                name="coupon_usage_not_over_limit",
            ),
        )

    def clean(self):
        self.code = (self.code or "").strip().upper()
        super().clean()
        errors = {}
        if not self.code:
            errors["code"] = "Ingresa un codigo de cupon."
        if self.expires_at and self.starts_at and self.expires_at <= self.starts_at:
            errors["expires_at"] = "La fecha de expiracion debe ser posterior al inicio de vigencia."
        if self.discount_type == self.DiscountType.PERCENTAGE and self.value is not None and self.value > 100:
            errors["value"] = "El porcentaje de descuento no puede superar el 100%."
        if self.usage_limit is not None and self.usage_limit < self.times_used:
            errors["usage_limit"] = "El limite no puede ser menor que la cantidad de usos ya registrados."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.code = (self.code or "").strip().upper()
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
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cart_items",
        verbose_name="variante",
    )
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

    @property
    def available_stock(self):
        if self.variant_id:
            return self.variant.stock if self.variant.is_active else 0
        return self.product.stock

    def save(self, *args, **kwargs):
        if not self.variant_id and self.product_id:
            candidates = ProductVariant.objects.filter(product_id=self.product_id, is_active=True)
            if self.size:
                candidates = candidates.filter(size=self.size)
            if self.color:
                candidates = candidates.filter(color_name=self.color)
            self.variant = candidates.filter(stock__gt=0).first() or candidates.first()
        if self.variant_id:
            self.product_id = self.variant.product_id
            self.size = self.variant.size
            self.color = self.variant.color_name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente de pago"
        PAID = "paid", "Pagado"
        PREPARING = "preparing", "Preparando"
        SHIPPED = "shipped", "Enviado"
        DELIVERED = "delivered", "Entregado"
        CANCELLED = "cancelled", "Cancelado"
        REFUNDED = "refunded", "Reembolsado"

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = "bank_transfer", "Transferencia bancaria"
        CASH_ON_DELIVERY = "cash_on_delivery", "Pago contra entrega"
        BOLD = "bold", "Pago con Bold"

    class DeliveryMethod(models.TextChoices):
        COURIER = "courier", "Domicilio"
        PICKUP = "pickup", "Recogida en Neiva"

    class FulfillmentStatus(models.TextChoices):
        PENDING_SHIPMENT = "pending_shipment", "Pendiente de envío"
        PACKING = "packing", "Empacando producto"
        IN_TRANSIT = "in_transit", "En camino"
        DELIVERED = "delivered", "Entregado"

    class PaymentStatus(models.TextChoices):
        """Estados que reporta Bold para una venta."""

        PROCESSING = "PROCESSING", "En proceso"
        PENDING = "PENDING", "Pendiente por el banco"
        APPROVED = "APPROVED", "Aprobado"
        REJECTED = "REJECTED", "Rechazado"
        FAILED = "FAILED", "Fallido"
        VOIDED = "VOIDED", "Anulado"
        NO_TRANSACTION_FOUND = "NO_TRANSACTION_FOUND", "Sin intentos de pago"

    # Estados en los que el cobro ya está confirmado y la venta cuenta como exitosa.
    SUCCESSFUL_STATUSES = (Status.PAID, Status.PREPARING, Status.SHIPPED, Status.DELIVERED)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    number = models.CharField("número de pedido", max_length=20, unique=True, editable=False)
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    payment_method = models.CharField("método de pago", max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER)
    delivery_method = models.CharField("tipo de envío", max_length=10, choices=DeliveryMethod.choices, default=DeliveryMethod.COURIER)
    fulfillment_status = models.CharField(
        "estado del envío",
        max_length=20,
        choices=FulfillmentStatus.choices,
        default=FulfillmentStatus.PENDING_SHIPMENT,
        db_index=True,
    )

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

    # Datos logísticos controlados desde el panel. Las fechas se asignan al
    # realizar una transición, no se escriben manualmente.
    carrier = models.CharField("transportadora", max_length=100, blank=True)
    tracking_number = models.CharField("número de guía", max_length=120, blank=True, db_index=True)
    dispatch_receipt = models.FileField(
        "comprobante de despacho",
        upload_to="orders/dispatch/%Y/%m/",
        blank=True,
        validators=(
            FileExtensionValidator(("pdf", "jpg", "jpeg", "png", "webp")),
            validate_dispatch_receipt,
        ),
        help_text="Opcional. PDF o imagen de hasta 5 MB; la guía en texto sigue siendo la referencia principal.",
    )
    shipped_at = models.DateTimeField("fecha de despacho", null=True, blank=True, editable=False)
    delivered_at = models.DateTimeField("fecha de entrega", null=True, blank=True, editable=False)

    # Seguimiento del cobro en la pasarela. La referencia es el identificador que
    # viaja a Bold e incluye el número de intento para permitir reintentos.
    payment_reference = models.CharField("referencia de pago", max_length=60, blank=True, db_index=True, editable=False)
    payment_status = models.CharField("estado del pago", max_length=24, choices=PaymentStatus.choices, blank=True, editable=False)
    payment_transaction_id = models.CharField("transacción de la pasarela", max_length=80, blank=True, editable=False)
    payment_attempts = models.PositiveSmallIntegerField("intentos de pago", default=0, editable=False)
    paid_at = models.DateTimeField("fecha de pago", null=True, blank=True, editable=False)
    # Los pedidos con pasarela no descuentan inventario ni vacían el carrito hasta
    # que el pago se aprueba, para no perder la compra si el cliente se devuelve.
    stock_reserved = models.BooleanField("inventario descontado", default=False, editable=False)
    confirmation_email_sent_at = models.DateTimeField("confirmación enviada", null=True, blank=True, editable=False)

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
    def map_query(self):
        """Dirección en formato apto para geocodificar (Google Maps embed sin API key)."""
        parts = [self.address_line_1]
        if self.address_line_2:
            parts.append(self.address_line_2)
        parts += [self.city, self.department, "Colombia"]
        return ", ".join(part for part in parts if part)

    @property
    def gross_profit(self):
        if self.purchase_value is None or self.sale_value is None:
            return None
        return self.sale_value - self.purchase_value

    @property
    def awaiting_online_payment(self):
        return self.payment_method == self.PaymentMethod.BOLD and self.status == self.Status.PENDING

    @property
    def payment_in_progress(self):
        return self.payment_status in {self.PaymentStatus.PROCESSING, self.PaymentStatus.PENDING}

    @property
    def payment_failed(self):
        return self.payment_status in {self.PaymentStatus.REJECTED, self.PaymentStatus.FAILED}

    @property
    def is_paid(self):
        return self.status in self.SUCCESSFUL_STATUSES

    @property
    def is_closed(self):
        return self.status in {self.Status.CANCELLED, self.Status.REFUNDED}

    @property
    def available_transition_values(self):
        """Estados siguientes permitidos por el flujo operativo."""
        transitions = {
            self.Status.PENDING: (self.Status.PAID, self.Status.CANCELLED),
            self.Status.PAID: (self.Status.PREPARING, self.Status.REFUNDED),
            self.Status.PREPARING: (
                (self.Status.DELIVERED, self.Status.REFUNDED)
                if self.delivery_method == self.DeliveryMethod.PICKUP
                else (self.Status.SHIPPED, self.Status.REFUNDED)
            ),
            self.Status.SHIPPED: (self.Status.DELIVERED, self.Status.REFUNDED),
            self.Status.DELIVERED: (self.Status.REFUNDED,),
            self.Status.CANCELLED: (),
            self.Status.REFUNDED: (),
        }
        return transitions.get(self.status, ())

    @property
    def available_transitions(self):
        labels = dict(self.Status.choices)
        return tuple({"value": value, "label": labels[value]} for value in self.available_transition_values)

    @property
    def payment_state(self):
        """Resultado del cobro; decide qué confirmación ve el cliente.

        `awaiting` cubre tanto los métodos offline (transferencia, contra entrega)
        como una compra con pasarela que todavía no registra ningún intento.
        """
        if self.is_paid:
            return "approved"
        if self.is_closed:
            return "cancelled"
        if self.payment_in_progress:
            return "processing"
        if self.payment_failed:
            return "rejected"
        return "awaiting"

    @property
    def fulfillment_steps(self):
        steps = tuple(self.FulfillmentStatus.choices)
        current_index = next((index for index, (value, _) in enumerate(steps) if value == self.fulfillment_status), 0)
        return tuple(
            {
                "value": value,
                "label": label,
                "completed": index < current_index,
                "current": index == current_index,
            }
            for index, (value, label) in enumerate(steps)
        )

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_items",
        verbose_name="variante",
    )
    variant_sku = models.CharField("referencia de variante", max_length=100, blank=True)
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


class OrderStatusHistory(models.Model):
    class Source(models.TextChoices):
        ADMIN = "admin", "Panel administrativo"
        PAYMENT = "payment", "Confirmación de pago"
        WEBHOOK = "webhook", "Webhook"
        SYSTEM = "system", "Sistema"
        MIGRATION = "migration", "Migración"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history", verbose_name="pedido")
    from_status = models.CharField("estado anterior", max_length=12, choices=Order.Status.choices, blank=True)
    to_status = models.CharField("nuevo estado", max_length=12, choices=Order.Status.choices)
    source = models.CharField("origen", max_length=12, choices=Source.choices, default=Source.SYSTEM)
    note = models.CharField("nota", max_length=300, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
        verbose_name="responsable",
    )
    notification_sent_at = models.DateTimeField("notificación enviada", null=True, blank=True, editable=False)
    created_at = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "cambio de estado del pedido"
        verbose_name_plural = "historial de estados del pedido"
        ordering = ("-created_at", "-id")

    def __str__(self):
        return f"{self.order.number}: {self.get_to_status_display()}"

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
