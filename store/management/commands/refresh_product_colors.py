"""Reemplaza el color de relleno que se sembró en todo el catálogo.

La migración 0019 asignó "Color principal | #505050" a cada producto, así que
todas las fichas muestran el mismo círculo gris. Este comando recalcula esas
variantes con el color dominante de su propia foto y les pone un nombre
entendible.

Por seguridad solo informa lo que haría; escribe en la base con --apply.
"""

from django.core.management.base import BaseCommand

from ...colors import dominant_color_from_image, nearest_color_name
from ...models import ProductVariant


# Nombre exacto que dejó la migración semilla. Se compara solo el nombre y no el
# hexadecimal: hay productos con colores reales que también usan #505050, y
# renombrarlos borraría la distinción entre sus variantes.
PLACEHOLDER_NAME = "color principal"


class Command(BaseCommand):
    help = "Recalcula los colores de relleno del catálogo usando la foto de cada producto."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Guarda los cambios. Sin esta opción solo se muestra el resultado.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        variants = ProductVariant.objects.select_related("product").order_by("product__name", "size")
        pending = [
            variant for variant in variants if variant.color_name.strip().casefold() == PLACEHOLDER_NAME
        ]

        if not pending:
            self.stdout.write("No hay colores de relleno por corregir.")
            return

        updated = skipped = 0
        # Una sola lectura de imagen por producto: las tallas comparten la foto.
        resolved_by_product = {}
        for variant in pending:
            product_id = variant.product_id
            if product_id not in resolved_by_product:
                dominant = dominant_color_from_image(variant.product)
                resolved_by_product[product_id] = (dominant, nearest_color_name(dominant) if dominant else None)
            dominant, name = resolved_by_product[product_id]

            if not dominant or not name:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(f"  sin foto legible: {variant.product.name} · talla {variant.size or '-'}")
                )
                continue

            self.stdout.write(
                f"  {variant.product.name} · talla {variant.size or '-'}: "
                f"{variant.color_name or 'sin nombre'} {variant.color_hex} -> {name} {dominant}"
            )
            if apply_changes:
                variant.color_name = name
                variant.color_hex = dominant
                variant.save()
            updated += 1

        summary = f"{updated} variantes actualizadas, {skipped} sin cambio."
        if apply_changes:
            self.stdout.write(self.style.SUCCESS(summary))
        else:
            self.stdout.write(self.style.WARNING(f"Simulación: {summary} Repite con --apply para guardar."))
