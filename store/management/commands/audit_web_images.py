"""Audita y, opcionalmente, optimiza las imágenes administrables del sitio."""

from pathlib import Path

from django.core.management.base import BaseCommand
from PIL import Image, UnidentifiedImageError

from store.image_optimization import TARGET_IMAGE_BYTES, WEBP_QUALITY, optimize_uploaded_image
from store.models import HomeBanner, MarketingPopup, Product, ProductImage, StoreSection


class Command(BaseCommand):
    help = "Audita imágenes subidas y, con --optimize, las convierte a WebP optimizado."

    def add_arguments(self, parser):
        parser.add_argument(
            "--optimize",
            action="store_true",
            help="Convierte y redimensiona los archivos existentes. Sin esta opción no modifica nada.",
        )
        parser.add_argument(
            "--quality",
            type=int,
            default=WEBP_QUALITY,
            help=f"Calidad WebP entre 60 y 90 (predeterminado: {WEBP_QUALITY}).",
        )

    def handle(self, *args, **options):
        quality = options["quality"]
        if not 60 <= quality <= 90:
            self.stderr.write(self.style.ERROR("La calidad debe estar entre 60 y 90."))
            return

        records = list(self._records())
        inspected = optimized = warnings = errors = 0

        for instance, field_name, max_size, label in records:
            field_file = getattr(instance, field_name, None)
            if not field_file:
                continue
            inspected += 1
            try:
                details = self._inspect(field_file)
                issues = self._issues(details, max_size)
                if issues:
                    warnings += 1
                status = ", ".join(issues) if issues else "correcta"
                self.stdout.write(
                    f"{label}: {details['format']} {details['width']}x{details['height']} "
                    f"· {self._human_bytes(details['size'])} · {status}"
                )

                if options["optimize"] and issues:
                    before_size = details["size"]
                    new_size = self._optimize(instance, field_name, max_size, quality)
                    optimized += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  optimizada: {self._human_bytes(before_size)} → "
                            f"{self._human_bytes(new_size)}"
                        )
                    )
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(f"{label}: no se pudo procesar ({exc})."))

        mode = "optimización" if options["optimize"] else "auditoría sin cambios"
        self.stdout.write(
            self.style.SUCCESS(
                f"Resumen ({mode}): {inspected} revisadas, {warnings} con mejoras, "
                f"{optimized} optimizadas, {errors} errores."
            )
        )

    def _records(self):
        for product in Product.objects.exclude(image_file="").iterator():
            yield product, "image_file", (1600, 1600), f"Producto {product.pk} · principal"
        for item in ProductImage.objects.exclude(image_file="").select_related("product").iterator():
            yield item, "image_file", (1600, 1600), f"Producto {item.product_id} · galería {item.pk}"
        for section in StoreSection.objects.iterator():
            if section.banner_image_file:
                yield section, "banner_image_file", (2400, 1400), f"Sección {section.pk} · banner"
            if section.empty_image_file:
                yield section, "empty_image_file", (1600, 1600), f"Sección {section.pk} · vacío"
        for banner in HomeBanner.objects.exclude(media_file="").iterator():
            if Path(banner.media_file.name).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                yield banner, "media_file", (2400, 1400), f"Banner {banner.pk}"
        for popup in MarketingPopup.objects.exclude(image_file="").iterator():
            yield popup, "image_file", (1400, 1400), f"Popup {popup.pk}"

    @staticmethod
    def _inspect(field_file):
        field_file.open("rb")
        try:
            size = field_file.size
            with Image.open(field_file.file) as image:
                return {
                    "format": image.format or "desconocido",
                    "width": image.width,
                    "height": image.height,
                    "size": size,
                }
        finally:
            field_file.close()

    @staticmethod
    def _issues(details, max_size):
        issues = []
        if details["format"] != "WEBP":
            issues.append("no es WebP")
        if details["width"] > max_size[0] or details["height"] > max_size[1]:
            issues.append("dimensiones excesivas")
        if details["size"] > TARGET_IMAGE_BYTES:
            issues.append("más de 600 KB")
        return issues

    @staticmethod
    def _optimize(instance, field_name, max_size, quality):
        field_file = getattr(instance, field_name)
        old_name = field_file.name
        storage = field_file.storage
        field_file.open("rb")
        try:
            new_name, content = optimize_uploaded_image(
                field_file.file,
                max_size=max_size,
                quality=quality,
            )
        finally:
            field_file.close()

        field_file.save(new_name, content, save=False)
        instance.save(update_fields=(field_name,))
        if old_name != field_file.name and storage.exists(old_name):
            storage.delete(old_name)
        return field_file.size

    @staticmethod
    def _human_bytes(value):
        if value < 1024:
            return f"{value} B"
        if value < 1024 * 1024:
            return f"{value / 1024:.1f} KB"
        return f"{value / (1024 * 1024):.2f} MB"
