"""Validación y optimización de imágenes subidas por administradores."""

from io import BytesIO
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import Image, ImageOps, UnidentifiedImageError, features


IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
IMAGE_FORMATS_BY_EXTENSION = {
    "jpg": "JPEG",
    "jpeg": "JPEG",
    "png": "PNG",
    "webp": "WEBP",
}
MAX_IMAGE_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
WEBP_QUALITY = 82
TARGET_IMAGE_BYTES = 600 * 1024


def validate_image_upload(upload):
    """Rechaza archivos falsos, animados, excesivos o con extensión incorrecta."""
    extension = Path(upload.name).suffix.lstrip(".").lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ValidationError("Sube una imagen JPG, PNG o WebP.")
    if upload.size > MAX_IMAGE_UPLOAD_BYTES:
        raise ValidationError("La imagen no puede superar 15 MB.")

    upload.seek(0)
    try:
        with Image.open(upload) as image:
            if image.format != IMAGE_FORMATS_BY_EXTENSION[extension]:
                raise ValidationError("La extensión no coincide con el contenido real de la imagen.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValidationError("La imagen supera el límite de 40 megapíxeles.")
            if getattr(image, "is_animated", False):
                raise ValidationError("Las imágenes animadas no están permitidas.")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("El archivo no contiene una imagen válida.") from exc
    finally:
        upload.seek(0)


def optimize_uploaded_image(upload, *, max_size, quality=WEBP_QUALITY):
    """Corrige orientación, reduce dimensiones y elimina metadatos al convertir a WebP."""
    if not features.check("webp"):
        raise RuntimeError("Pillow no tiene soporte WebP en este servidor.")

    validate_image_upload(upload)
    upload.seek(0)
    try:
        with Image.open(upload) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            has_alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")
            candidate_qualities = list(range(quality, 59, -4))
            if candidate_qualities[-1] != 60:
                candidate_qualities.append(60)
            while True:
                for candidate_quality in candidate_qualities:
                    output = BytesIO()
                    image.save(
                        output,
                        format="WEBP",
                        quality=candidate_quality,
                        method=6,
                        optimize=True,
                    )
                    if output.tell() <= TARGET_IMAGE_BYTES:
                        break
                if output.tell() <= TARGET_IMAGE_BYTES or max(image.size) <= 800:
                    break
                next_long_edge = max(800, int(max(image.size) * 0.85))
                scale = next_long_edge / max(image.size)
                image.thumbnail(
                    (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
                    Image.Resampling.LANCZOS,
                )
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("No fue posible optimizar la imagen.") from exc
    finally:
        upload.seek(0)

    stem = slugify(Path(upload.name).stem) or "imagen"
    return f"{stem}.webp", ContentFile(output.getvalue())


def optimize_field_file(instance, field_name, *, max_size, quality=WEBP_QUALITY):
    """Optimiza solo cargas nuevas; las referencias ya guardadas no se reprocesan."""
    field_file = getattr(instance, field_name, None)
    if not field_file or getattr(field_file, "_committed", True):
        return False
    optimized_name, optimized_content = optimize_uploaded_image(
        field_file.file,
        max_size=max_size,
        quality=quality,
    )
    field_file.save(optimized_name, optimized_content, save=False)
    return True
