"""Resolución del color que se muestra en la ficha de producto.

El swatch del catálogo solía mostrar siempre el mismo gris de relleno porque el
color se sembró como "Color principal | #505050" para todos los productos. Aquí
se resuelve un color real siguiendo tres pasos, del más explícito al más
automático:

1. El hexadecimal escrito por el administrador.
2. El nombre del color, traducido con un diccionario orientado a sneakers.
3. El color dominante de la imagen del producto, ignorando el fondo.
"""

import unicodedata
from pathlib import Path

from django.conf import settings


# Gris neutro que se usa solo cuando ninguna de las tres estrategias da un color.
NEUTRAL_COLOR = "#6E6E6E"

# Nombres en español e inglés que aparecen en las colorways de sneakers. Las
# claves se comparan sin acentos ni mayúsculas.
COLOR_NAMES = {
    "negro": "#111111",
    "black": "#111111",
    "panda": "#111111",
    "blanco": "#F4F4F4",
    "white": "#F4F4F4",
    "hueso": "#EDE8DE",
    "off white": "#EDE8DE",
    "crema": "#E8DCC8",
    "cream": "#E8DCC8",
    "beige": "#D9C7A7",
    "gris": "#808080",
    "gray": "#808080",
    "grey": "#808080",
    "gris oscuro": "#4A4A4A",
    "gris claro": "#C4C4C4",
    "gris piedra": "#9A958C",
    "humo": "#8C8C8C",
    "rojo": "#C62828",
    "red": "#C62828",
    "bordeaux": "#6D1F2E",
    "burdeos": "#6D1F2E",
    "burgundy": "#6D1F2E",
    "vino": "#6D1F2E",
    "wine": "#6D1F2E",
    "granate": "#6D1F2E",
    "azul": "#1E4FA3",
    "blue": "#1E4FA3",
    "azul marino": "#17224D",
    "navy": "#17224D",
    "azul claro": "#4FA3E3",
    "celeste": "#4FA3E3",
    "azul grisaceo": "#5A6B85",
    "obsidian": "#1F2A44",
    "verde": "#2E7D32",
    "green": "#2E7D32",
    "verde militar": "#4B5320",
    "oliva": "#4B5320",
    "olive": "#4B5320",
    "menta": "#8FD5B4",
    "amarillo": "#F2C200",
    "yellow": "#F2C200",
    "mostaza": "#C9932A",
    "naranja": "#E86A17",
    "orange": "#E86A17",
    "coral": "#F0705A",
    "morado": "#6A2C8F",
    "purpura": "#6A2C8F",
    "purple": "#6A2C8F",
    "violeta": "#7B52AB",
    "lila": "#B39DDB",
    "rosa": "#E87DA8",
    "rosado": "#E87DA8",
    "pink": "#E87DA8",
    "cafe": "#6B4423",
    "marron": "#6B4423",
    "brown": "#6B4423",
    "chocolate": "#4E342E",
    "camel": "#B0813B",
    "dorado": "#C9A227",
    "gold": "#C9A227",
    "plateado": "#C0C4C8",
    "plata": "#C0C4C8",
    "silver": "#C0C4C8",
    "turquesa": "#17A2A2",
    "teal": "#17A2A2",
}

# Píxeles casi blancos o casi transparentes se descartan: en las fotos de
# catálogo son el fondo, no el producto.
BACKGROUND_LUMINANCE = 235
SAMPLE_SIZE = 72
MIN_SAMPLE_PIXELS = 40
# Ancho de cada cubo de color al agrupar los píxeles para buscar el más repetido.
BUCKET_WIDTH = 40
# Umbral de "claro y apagado": descarta blancos, sombras y bordes difuminados.
PALE_LUMINANCE = 175
PALE_SATURATION = 28
# Debajo de esta diferencia entre canales el color se considera un neutro.
NEUTRAL_SATURATION = 12


# Un nombre visible por color, para bautizar un hexadecimal calculado desde la
# foto. Es la lista de arriba sin sinónimos y con la escritura que ve el cliente.
CANONICAL_COLOR_NAMES = (
    ("Negro", "#111111"),
    ("Blanco", "#F4F4F4"),
    ("Hueso", "#EDE8DE"),
    ("Crema", "#E8DCC8"),
    ("Beige", "#D9C7A7"),
    ("Gris", "#808080"),
    ("Gris oscuro", "#4A4A4A"),
    ("Gris claro", "#C4C4C4"),
    ("Rojo", "#C62828"),
    ("Bordeaux", "#6D1F2E"),
    ("Azul", "#1E4FA3"),
    ("Azul marino", "#17224D"),
    ("Azul claro", "#4FA3E3"),
    ("Verde", "#2E7D32"),
    ("Verde militar", "#4B5320"),
    ("Amarillo", "#F2C200"),
    ("Mostaza", "#C9932A"),
    ("Naranja", "#E86A17"),
    ("Morado", "#6A2C8F"),
    ("Rosa", "#E87DA8"),
    ("Cafe", "#6B4423"),
    ("Chocolate", "#4E342E"),
    ("Dorado", "#C9A227"),
    ("Plateado", "#C0C4C8"),
    ("Turquesa", "#17A2A2"),
)


def _rgb(value):
    text = (value or "").lstrip("#")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def _saturation(rgb):
    return max(rgb) - min(rgb)


def nearest_color_name(value):
    """Nombre visible más cercano a un hexadecimal, o None si no es válido.

    Sirve para ponerle un nombre entendible al color que se calcula desde la
    foto, en vez de mostrarle al cliente un código.
    """
    try:
        sample = _rgb(value)
    except (ValueError, IndexError):
        return None

    # Un tono sin saturación solo puede llamarse gris, negro o blanco: por
    # cercanía numérica un carbón neutro caería en "Chocolate", que es marrón.
    candidates = CANONICAL_COLOR_NAMES
    if _saturation(sample) < NEUTRAL_SATURATION:
        neutrals = tuple(item for item in candidates if _saturation(_rgb(item[1])) < NEUTRAL_SATURATION)
        candidates = neutrals or candidates

    return min(
        candidates,
        key=lambda item: sum(
            (channel - reference) ** 2 for channel, reference in zip(sample, _rgb(item[1]))
        ),
    )[0]


def normalize_color_name(value):
    """Minúsculas y sin acentos, para comparar 'Gris Oscuro' con 'gris oscuro'."""
    text = (value or "").strip().lower()
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(stripped.split())


def color_hex_from_name(value):
    """Traduce el nombre de un color a su hexadecimal, o None si no se reconoce.

    Acepta nombres compuestos como "Negro/Blanco" o "Azul marino premium":
    primero busca la coincidencia exacta y luego la expresión más larga que
    aparezca dentro del texto, para que "azul marino" gane sobre "azul".
    """
    name = normalize_color_name(value)
    if not name:
        return None
    if name in COLOR_NAMES:
        return COLOR_NAMES[name]

    separators = "/-,+&"
    for separator in separators:
        name = name.replace(separator, " ")
    words = name.split()
    if not words:
        return None

    for length in (3, 2, 1):
        for start in range(len(words) - length + 1):
            candidate = " ".join(words[start:start + length])
            if candidate in COLOR_NAMES:
                return COLOR_NAMES[candidate]
    return None


def _image_path_for_product(product):
    """Ruta en disco de la imagen principal, sea subida al admin o estática."""
    image_file = getattr(product, "image_file", None)
    if image_file:
        try:
            return Path(image_file.path)
        except (NotImplementedError, ValueError):
            return None

    reference = (getattr(product, "image", "") or "").strip()
    if not reference or reference.startswith(("http://", "https://", "//")):
        return None
    relative = reference.lstrip("/")
    prefix = settings.STATIC_URL.strip("/")
    if prefix and relative.startswith(f"{prefix}/"):
        relative = relative[len(prefix) + 1:]
    for directory in settings.STATICFILES_DIRS:
        candidate = Path(directory) / relative
        if candidate.is_file():
            return candidate
    return None


def dominant_color_from_image(product):
    """Color más repetido del producto, ignorando el fondo claro de la foto.

    Se agrupan los píxeles en cubos de color y gana el cubo más poblado. Se usa
    la moda y no el promedio porque promediar un zapato blanco y negro da un
    gris que no existe en la foto.

    Devuelve None ante cualquier problema: es una ayuda estética, nunca debe
    impedir que se guarde un producto.
    """
    path = _image_path_for_product(product)
    if path is None or not path.is_file():
        return None

    try:
        from PIL import Image

        with Image.open(path) as source:
            image = source.convert("RGBA")
            image.thumbnail((SAMPLE_SIZE, SAMPLE_SIZE))
            pixels = list(image.getdata())
    except Exception:
        return None

    # Primer intento sin los claros apagados: fondo de estudio, sombras suaves y
    # bordes difuminados. Si el producto es blanco no queda nada que medir, y el
    # segundo intento conserva esos tonos para no devolver un color vacío.
    return _most_common_color(pixels, drop_pale=True) or _most_common_color(pixels, drop_pale=False)


def _most_common_color(pixels, *, drop_pale):
    """Promedio del cubo de color más poblado, o None si no hay muestra suficiente."""
    buckets = {}
    counted = 0
    for red, green, blue, alpha in pixels:
        if alpha < 128:
            continue
        luminance = 0.299 * red + 0.587 * green + 0.114 * blue
        saturation = max(red, green, blue) - min(red, green, blue)
        if luminance >= BACKGROUND_LUMINANCE and saturation < 12:
            continue
        if drop_pale and luminance >= PALE_LUMINANCE and saturation < PALE_SATURATION:
            continue
        key = (red // BUCKET_WIDTH, green // BUCKET_WIDTH, blue // BUCKET_WIDTH)
        totals = buckets.setdefault(key, [0, 0, 0, 0])
        totals[0] += red
        totals[1] += green
        totals[2] += blue
        totals[3] += 1
        counted += 1

    if counted < MIN_SAMPLE_PIXELS:
        return None
    # Los empates se resuelven por el cubo más oscuro: en una foto de catálogo
    # el color de la silueta describe mejor el producto que un reflejo claro.
    red_total, green_total, blue_total, size = max(
        buckets.values(),
        key=lambda totals: (totals[3], -(totals[0] + totals[1] + totals[2])),
    )
    return "#{:02X}{:02X}{:02X}".format(
        round(red_total / size),
        round(green_total / size),
        round(blue_total / size),
    )


def resolve_color_hex(name, *, explicit_hex="", product=None):
    """Color definitivo del swatch: hex escrito, luego nombre, luego imagen."""
    chosen = (explicit_hex or "").strip().upper()
    if chosen:
        return chosen
    from_name = color_hex_from_name(name)
    if from_name:
        return from_name
    if product is not None:
        from_image = dominant_color_from_image(product)
        if from_image:
            return from_image
    return NEUTRAL_COLOR
