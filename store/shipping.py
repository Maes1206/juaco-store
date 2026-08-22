"""Cotizador de envíos nacionales con origen en Neiva, Huila.

Tarifas de referencia de Encomienda Normal publicadas por 4-72 en junio de
2026. La clasificación definitiva de un trayecto especial depende del
municipio y debe confirmarse con el operador antes del despacho.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import unicodedata


DEPARTMENTS = (
    "Amazonas",
    "Antioquia",
    "Arauca",
    "Atlántico",
    "Bolívar",
    "Boyacá",
    "Caldas",
    "Caquetá",
    "Casanare",
    "Cauca",
    "Cesar",
    "Chocó",
    "Córdoba",
    "Cundinamarca",
    "Guainía",
    "Guaviare",
    "Huila",
    "La Guajira",
    "Magdalena",
    "Meta",
    "Nariño",
    "Norte de Santander",
    "Putumayo",
    "Quindío",
    "Risaralda",
    "San Andrés, Providencia y Santa Catalina",
    "Santander",
    "Sucre",
    "Tolima",
    "Valle del Cauca",
    "Vaupés",
    "Vichada",
)
DESTINATIONS = ("Bogotá D.C.",) + DEPARTMENTS


def _normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char for char in value if not unicodedata.combining(char)).strip().casefold()


_DESTINATION_MAP = {_normalize(name): name for name in DESTINATIONS}
_REMOTE_DEPARTMENTS = {
    _normalize(name)
    for name in (
        "Amazonas",
        "Guainía",
        "Guaviare",
        "San Andrés, Providencia y Santa Catalina",
        "Vaupés",
        "Vichada",
    )
}

# Valores COP por rangos de 0-1 kg, 1.001-2 kg, ... 29.001-30 kg.
# Fuente: tabla oficial 4-72, Encomienda Normal, expedición 01/06/2026.
URBAN_RATES = (
    6950, 6950, 6950, 6950, 7150, 7350, 7550, 7800, 8000, 8200,
    8400, 8600, 8800, 9050, 9250, 9450, 9650, 9850, 10050, 10300,
    10500, 10700, 10900, 11100, 11350, 11550, 11750, 11950, 12150, 12350,
)
NATIONAL_RATES = (
    24950, 24950, 24950, 24950, 25700, 26450, 27250, 28000, 28750, 29550,
    30300, 31050, 31850, 32600, 33350, 34150, 34900, 35650, 36450, 37200,
    37950, 38750, 39500, 40250, 41050, 41800, 42550, 43350, 44100, 44850,
)
# La tarifa oficial para trayecto especial de hasta 7 imposiciones al año
# coincide con la tarifa nacional. Es el escenario conservador de una tienda
# que realiza envíos individuales.
SPECIAL_RATES = NATIONAL_RATES

SOURCE_LABEL = "4-72 · Encomienda Normal"
SOURCE_URL = "https://www.4-72.com.co/publicaciones/310/encomienda-normal/"
RATE_REFERENCE = "Tarifas oficiales expedidas el 1 de junio de 2026"


@dataclass(frozen=True)
class ShippingQuote:
    department: str
    city: str
    postal_code: str
    weight_kg: str
    billable_kg: int
    zone: str
    zone_label: str
    cost: int
    delivery_days: str
    method: str
    source_label: str = SOURCE_LABEL
    source_url: str = SOURCE_URL
    rate_reference: str = RATE_REFERENCE
    is_estimate: bool = True

    def session_payload(self):
        return asdict(self)


def calculate_shipping(department, city, weight_kg, postal_code="", method="courier"):
    """Calcula una cotización orientativa desde Neiva para paquetes de hasta 30 kg."""
    method = str(method or "courier").strip().casefold()
    city = str(city or "").strip()
    postal_code = str(postal_code or "").strip()

    if method == "pickup":
        return ShippingQuote(
            department="Huila",
            city="Neiva",
            postal_code=postal_code,
            weight_kg="0",
            billable_kg=0,
            zone="pickup",
            zone_label="Recogida en Neiva, Huila",
            cost=0,
            delivery_days="Disponible según horario de la tienda",
            method="pickup",
        )

    canonical_department = _DESTINATION_MAP.get(_normalize(department))
    if not canonical_department:
        raise ValueError("Selecciona un departamento válido de Colombia.")
    if len(city) < 2:
        raise ValueError("Ingresa la ciudad o municipio de destino.")

    try:
        weight = Decimal(str(weight_kg).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Ingresa un peso válido en kilogramos.") from None
    if weight <= 0 or weight > 30:
        raise ValueError("El peso debe estar entre 0,1 y 30 kg.")

    billable_kg = int(weight.to_integral_value(rounding=ROUND_CEILING))
    department_key = _normalize(canonical_department)
    city_key = _normalize(city)

    if department_key == _normalize("Huila") and city_key == _normalize("Neiva"):
        zone = "urban"
        zone_label = "Trayecto urbano en Neiva"
        rates = URBAN_RATES
        delivery_days = "2 días hábiles estimados"
    elif department_key in _REMOTE_DEPARTMENTS:
        zone = "special"
        zone_label = "Trayecto especial estimado"
        rates = SPECIAL_RATES
        delivery_days = "Hasta 10 días hábiles estimados"
    else:
        zone = "national"
        zone_label = "Trayecto nacional"
        rates = NATIONAL_RATES
        delivery_days = "3 a 7 días hábiles estimados"

    return ShippingQuote(
        department=canonical_department,
        city=city,
        postal_code=postal_code,
        weight_kg=format(weight.normalize(), "f"),
        billable_kg=billable_kg,
        zone=zone,
        zone_label=zone_label,
        cost=rates[billable_kg - 1],
        delivery_days=delivery_days,
        method="courier",
    )
