import json
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache


TOKEN_URL = "https://accounts.stockx.com/oauth/token"
CATALOG_SEARCH_URL = "https://api.stockx.com/v2/catalog/search"
TOKEN_CACHE_KEY = "stockx_catalog_access_token"


class StockXNotConfigured(Exception):
    pass


class StockXLookupError(Exception):
    pass


@dataclass(frozen=True)
class StockXReleaseDate:
    release_date: date
    product_id: str
    title: str


def _read_json(request):
    try:
        with urlopen(request, timeout=settings.STOCKX_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            cache.delete(TOKEN_CACHE_KEY)
            raise StockXLookupError("las credenciales fueron rechazadas") from exc
        if exc.code == 429:
            raise StockXLookupError("se alcanzó el límite temporal de consultas") from exc
        raise StockXLookupError(f"StockX respondió con el estado {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        raise StockXLookupError("el servicio no respondió a tiempo") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StockXLookupError("StockX devolvió una respuesta inválida") from exc


def _access_token():
    if settings.STOCKX_ACCESS_TOKEN:
        return settings.STOCKX_ACCESS_TOKEN

    cached_token = cache.get(TOKEN_CACHE_KEY)
    if cached_token:
        return cached_token

    if not all((settings.STOCKX_CLIENT_ID, settings.STOCKX_CLIENT_SECRET, settings.STOCKX_REFRESH_TOKEN)):
        raise StockXNotConfigured

    body = urlencode({
        "grant_type": "refresh_token",
        "client_id": settings.STOCKX_CLIENT_ID,
        "client_secret": settings.STOCKX_CLIENT_SECRET,
        "audience": "gateway.stockx.com",
        "refresh_token": settings.STOCKX_REFRESH_TOKEN,
    }).encode("utf-8")
    request = Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    payload = _read_json(request)
    token = payload.get("access_token")
    if not token:
        raise StockXLookupError("no se recibió un token de acceso")
    expires_in = int(payload.get("expires_in") or 43200)
    cache.set(TOKEN_CACHE_KEY, token, timeout=max(60, expires_in - 60))
    return token


def lookup_release_date(reference):
    reference = str(reference or "").strip()
    if not reference:
        return None
    if not settings.STOCKX_API_KEY:
        raise StockXNotConfigured

    query = urlencode({"query": reference, "pageNumber": 1, "pageSize": 10})
    request = Request(
        f"{CATALOG_SEARCH_URL}?{query}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {_access_token()}",
            "x-api-key": settings.STOCKX_API_KEY,
        },
        method="GET",
    )
    payload = _read_json(request)
    products = payload.get("products") or []
    normalized_reference = reference.casefold()
    product = next(
        (item for item in products if str(item.get("styleId") or "").strip().casefold() == normalized_reference),
        None,
    )
    if product is None and reference.isdigit() and len(products) == 1:
        product = products[0]
    if product is None:
        return None

    raw_release_date = str((product.get("productAttributes") or {}).get("releaseDate") or "").strip()
    if not raw_release_date:
        return None
    try:
        parsed_release_date = date.fromisoformat(raw_release_date[:10])
    except ValueError as exc:
        raise StockXLookupError("la fecha recibida no tiene un formato válido") from exc

    return StockXReleaseDate(
        release_date=parsed_release_date,
        product_id=str(product.get("productId") or ""),
        title=str(product.get("title") or ""),
    )
