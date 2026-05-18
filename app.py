import os
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent


def _load_env() -> None:
    for path in (ROOT / ".env", Path.cwd() / ".env"):
        if path.is_file():
            load_dotenv(path, encoding="utf-8-sig", override=True)
            return
    load_dotenv(encoding="utf-8-sig")


_load_env()

DUFFEL_OFFER_REQUESTS_URL = "https://api.duffel.com/air/offer_requests"
DUFFEL_VERSION = "v2"

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
# Hoteles: Duffel Stays suele requerir contrato comercial; usamos Geoapify (plan gratuito en geoapify.com).
GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
GEOAPIFY_CATEGORIES = (
    "accommodation.hotel,accommodation.motel,accommodation.hostel,"
    "accommodation.guest_house,accommodation.apartment"
)
DUFFEL_STAYS_SEARCH_URL = "https://api.duffel.com/stays/search"


def _get_duffel_token() -> str:
    token = os.getenv("DUFFEL_ACCESS_TOKEN", "").strip()
    if not token:
        env_file = ROOT / ".env"
        raise HTTPException(
            status_code=503,
            detail=(
                "No se encontró DUFFEL_ACCESS_TOKEN. "
                f"Crea el archivo {env_file} con: DUFFEL_ACCESS_TOKEN=duffel_test_..."
            ),
        )
    return token


def _duffel_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Duffel-Version": DUFFEL_VERSION,
    }


def _normalize_duffel_offers(offers: list) -> list:
    out = []
    for offer in offers[:15]:
        total = offer.get("total_amount")
        currency = offer.get("total_currency") or "USD"
        slices = offer.get("slices") or []
        first_slice = slices[0] if slices else {}
        segments = first_slice.get("segments") or []
        first_seg = segments[0] if segments else {}
        last_seg = segments[-1] if segments else {}

        dep_origin = (first_seg.get("origin") or {}).get("iata_code")
        arr_dest = (last_seg.get("destination") or {}).get("iata_code")
        dep_time = first_seg.get("departing_at")
        arr_time = last_seg.get("arriving_at")

        carrier_parts = []
        for s in segments:
            mc = s.get("marketing_carrier") or {}
            code = mc.get("iata_code", "")
            num = s.get("marketing_carrier_flight_number", "")
            if code or num:
                carrier_parts.append(f"{code}{num}".strip())
        carriers_str = ", ".join(carrier_parts) if carrier_parts else None

        out.append(
            {
                "id": offer.get("id"),
                "currency": currency,
                "total": float(total) if total is not None else None,
                "departure_airport": dep_origin,
                "departure_time": dep_time,
                "arrival_airport": arr_dest,
                "arrival_time": arr_time,
                "stops": max(0, len(segments) - 1),
                "carriers": carriers_str,
            }
        )
    return out


def _geocode_city(name: str) -> tuple[float, float]:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Indica una ciudad o zona.")
    with httpx.Client(timeout=20.0) as client:
        r = client.get(
            GEOCODE_URL,
            params={"name": name, "count": 1, "language": "es", "format": "json"},
        )
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No se encontró la ubicación «{name}». Prueba otro nombre.",
        )
    loc = results[0]
    return float(loc["latitude"]), float(loc["longitude"])


def _normalize_duffel_stays_results(results: list) -> list:
    """Resultados de búsqueda Duffel Stays (precios e imágenes si la cuenta tiene acceso)."""
    out = []
    for row in results[:20]:
        acc = row.get("accommodation") or {}
        loc = acc.get("location") or {}
        addr = loc.get("address") or {}
        gc = loc.get("geographic_coordinates") or {}
        lat = gc.get("latitude")
        lon = gc.get("longitude")
        photos = acc.get("photos") or []
        img = photos[0].get("url") if photos else None
        amount = row.get("cheapest_rate_total_amount")
        cur = row.get("cheapest_rate_currency") or row.get(
            "cheapest_rate_public_currency"
        )
        maps_url = None
        if lat is not None and lon is not None:
            maps_url = f"https://www.google.com/maps?q={lat},{lon}"
        out.append(
            {
                "id": acc.get("id"),
                "name": acc.get("name"),
                "description": ((acc.get("description") or "")[:280]),
                "city": addr.get("city_name") or "",
                "address_line": addr.get("line_one") or "",
                "region": addr.get("region") or "",
                "country": addr.get("country_code") or "",
                "review_score": row.get("review_score") or acc.get("review_score"),
                "review_count": acc.get("review_count"),
                "total": float(amount) if amount is not None else None,
                "currency": cur or "USD",
                "photo_url": img,
                "image_type": "property",
                "photo_caption": None,
                "lat": lat,
                "lon": lon,
                "maps_url": maps_url,
                "source": "duffel",
            }
        )
    return out


def _normalize_geoapify_hotels(features: list) -> list:
    """Convierte respuesta Geoapify Places (OSM) al formato de tarjetas del front."""
    out = []
    for idx, feat in enumerate(features[:25]):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        lon = coords[0] if len(coords) >= 2 else None
        lat = coords[1] if len(coords) >= 2 else None
        name = props.get("name") or props.get("street") or "Alojamiento"
        formatted = props.get("formatted") or ""
        cats = props.get("categories") or []
        desc = ", ".join(c.replace("accommodation.", "") for c in cats[:3]) if cats else ""
        pid = props.get("place_id")
        if not pid and lon is not None and lat is not None:
            pid = f"{lat:.5f},{lon:.5f}-{idx}"
        thumb = (
            f"/api/static-map?lat={lat:.6f}&lon={lon:.6f}"
            if lat is not None and lon is not None
            else None
        )
        out.append(
            {
                "id": str(pid or idx),
                "name": name,
                "description": desc[:280],
                "city": "",
                "address_line": formatted,
                "region": "",
                "country": "",
                "review_score": None,
                "review_count": None,
                "total": None,
                "currency": "",
                "photo_url": thumb,
                "image_type": "map_preview",
                "photo_caption": "Mapa del entorno (no es foto del establecimiento)",
                "lat": lat,
                "lon": lon,
                "maps_url": (
                    f"https://www.google.com/maps?q={lat},{lon}"
                    if lat is not None and lon is not None
                    else None
                ),
                "source": "geoapify",
            }
        )
    return out


def _rapidapi_find_list(payload: object) -> list:
    """Extrae la primera lista de objetos tipo hotel de respuestas JSON variables."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    preferred_keys = (
        "properties",
        "results",
        "searchResults",
        "hotels",
        "data",
        "sr",
        "entities",
        "suggestions",
        "propertySearchListing",
        "hotelsList",
    )
    for k in preferred_keys:
        v = payload.get(k)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        if isinstance(v, dict):
            inner = _rapidapi_find_list(v)
            if inner:
                return inner
    for v in payload.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        if isinstance(v, dict):
            inner = _rapidapi_find_list(v)
            if inner:
                return inner
    return []


def _normalize_rapidapi_item(item: dict) -> dict:
    """Unifica un ítem de RapidAPI al formato de tarjetas del front."""
    name = (
        item.get("name")
        or item.get("hotelName")
        or item.get("title")
        or item.get("displayName")
        or "Hotel"
    )
    hid = (
        item.get("id")
        or item.get("propertyId")
        or item.get("gaiaId")
        or item.get("hotel_id")
    )
    lat = item.get("latitude") or item.get("lat")
    lon = item.get("longitude") or item.get("lon") or item.get("lng")
    coord = item.get("coordinate") or item.get("coordinates") or item.get("geo") or {}
    if isinstance(coord, dict):
        lat = lat or coord.get("latitude") or coord.get("lat")
        lon = lon or coord.get("longitude") or coord.get("lng") or coord.get("lon")

    photo = None
    caption = None
    for key in ("featuredImage", "featuredPhoto", "image", "thumbnail"):
        img = item.get(key)
        if isinstance(img, str) and img.startswith("http"):
            photo = img
            break
        if isinstance(img, dict):
            photo = img.get("url") or img.get("imageUrl")
            if photo:
                break
    if not photo:
        imgs = item.get("images") or item.get("photos") or item.get("media") or []
        if isinstance(imgs, list) and imgs:
            first = imgs[0]
            if isinstance(first, str) and first.startswith("http"):
                photo = first
            elif isinstance(first, dict):
                photo = (
                    first.get("url")
                    or first.get("imageUrl")
                    or first.get("thumbnailUrl")
                )

    total = None
    cur = item.get("currency") or os.getenv("RAPIDAPI_CURRENCY", "USD")
    for key in ("price", "rate", "lowestPrice"):
        v = item.get(key)
        if isinstance(v, dict):
            total = v.get("amount") or v.get("value") or v.get("total")
            cur = v.get("currency") or cur
            break
        if isinstance(v, (int, float)):
            total = float(v)
            break
    ps = item.get("priceSummary")
    if total is None and isinstance(ps, dict):
        total = ps.get("minPrice") or ps.get("price") or ps.get("displayPrice")
        if isinstance(total, str):
            try:
                total = float(total.replace(",", ""))
            except ValueError:
                total = None

    addr = item.get("address") or {}
    line = ""
    if isinstance(addr, str):
        line = addr
    elif isinstance(addr, dict):
        line = (
            addr.get("line1")
            or addr.get("addressLine")
            or addr.get("street")
            or ""
        )
    city = item.get("city") or (
        addr.get("city") if isinstance(addr, dict) else ""
    ) or ""
    country = item.get("country") or (
        addr.get("country") if isinstance(addr, dict) else ""
    ) or ""

    review = (
        item.get("reviewScore")
        or item.get("guestRating")
        or item.get("rating")
        or item.get("starRating")
    )

    maps_url = None
    if lat is not None and lon is not None:
        maps_url = f"https://www.google.com/maps?q={lat},{lon}"

    geo_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not photo and lat is not None and lon is not None and geo_key:
        photo = f"/api/static-map?lat={float(lat):.6f}&lon={float(lon):.6f}"
        caption = "Vista mapa (Geoapify)"

    return {
        "id": str(hid) if hid is not None else str(name)[:40],
        "name": str(name)[:200],
        "description": (
            (item.get("description") or item.get("shortDescription") or "")[:280]
        ),
        "city": str(city)[:120],
        "address_line": str(line)[:240],
        "region": "",
        "country": str(country)[:80],
        "review_score": float(review) if review is not None else None,
        "review_count": item.get("reviewCount") or item.get("review_count"),
        "total": float(total) if total is not None else None,
        "currency": str(cur)[:8] if total is not None else "",
        "photo_url": photo,
        "image_type": (
            "property"
            if photo and "/api/static-map" not in str(photo)
            else "map_preview"
        ),
        "photo_caption": caption,
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "maps_url": maps_url,
        "source": "rapidapi",
    }


def _search_hotels_rapidapi(
    city: str,
    check_in: date,
    check_out: date,
    guests: int,
    rooms: int,
) -> dict:
    key = os.getenv("RAPIDAPI_KEY", "").strip()
    host = os.getenv("RAPIDAPI_HOTEL_HOST", "").strip()
    path = os.getenv("RAPIDAPI_SEARCH_PATH", "").strip()
    if not key or not host or not path:
        raise HTTPException(
            status_code=503,
            detail=(
                "Modo rapidapi: define RAPIDAPI_KEY, RAPIDAPI_HOTEL_HOST y "
                "RAPIDAPI_SEARCH_PATH en .env (GET de búsqueda en RapidAPI)."
            ),
        )
    if not path.startswith("/"):
        path = "/" + path
    url = f"https://{host}{path}"
    style = os.getenv("RAPIDAPI_QUERY_STYLE", "hotels_com").strip().lower()
    if style in ("hotels_com", "hotels4", "default", ""):
        params = {
            "q": city,
            "locale": os.getenv("RAPIDAPI_LOCALE", "en_US"),
            "currency": os.getenv("RAPIDAPI_CURRENCY", "USD"),
        }
    elif style in ("dates", "with_dates", "full"):
        params = {
            "q": city,
            "checkIn": check_in.isoformat(),
            "checkOut": check_out.isoformat(),
            "adults": str(guests),
            "rooms": str(rooms),
            "locale": os.getenv("RAPIDAPI_LOCALE", "en_US"),
            "currency": os.getenv("RAPIDAPI_CURRENCY", "USD"),
        }
    elif style == "minimal":
        params = {"q": city}
    else:
        params = {
            "q": city,
            "locale": os.getenv("RAPIDAPI_LOCALE", "en_US"),
            "currency": os.getenv("RAPIDAPI_CURRENCY", "USD"),
        }

    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": host,
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.get(url, headers=headers, params=params)

    if r.status_code != 200:
        try:
            err = r.json()
            detail = str(err)[:1200]
        except Exception:
            detail = r.text[:1200]
        raise HTTPException(status_code=r.status_code, detail=detail)

    try:
        payload = r.json()
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="La API de RapidAPI no devolvió JSON válido.",
        )

    items = _rapidapi_find_list(payload)
    if not items and isinstance(payload, dict):
        if any(k in payload for k in ("name", "hotelName", "title", "propertyId")):
            items = [payload]

    normalized = [_normalize_rapidapi_item(x) for x in items[:25]]
    note = (
        "RapidAPI: si no ves hoteles, cambia RAPIDAPI_SEARCH_PATH o "
        "RAPIDAPI_QUERY_STYLE (minimal / dates / hotels_com) según la doc. de tu API."
    )
    return {
        "hotels": normalized,
        "provider": "rapidapi",
        "note": note,
    }


app = FastAPI(title="ATLAS GUIDE API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/flights")
def search_flights(
    origin: str = Query(..., min_length=3, max_length=3, description="IATA origen"),
    destination: str = Query(..., min_length=3, max_length=3, description="IATA destino"),
    departure_date: date = Query(..., description="Fecha de salida"),
    adults: int = Query(1, ge=1, le=9),
):
    origin = origin.upper()
    destination = destination.upper()
    token = _get_duffel_token()
    dep_str = departure_date.isoformat()

    passengers = [{"type": "adult"} for _ in range(adults)]

    body = {
        "data": {
            "slices": [
                {
                    "origin": origin,
                    "destination": destination,
                    "departure_date": dep_str,
                }
            ],
            "passengers": passengers,
            "cabin_class": "economy",
        }
    }

    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            DUFFEL_OFFER_REQUESTS_URL,
            headers=_duffel_headers(token),
            json=body,
        )

    if r.status_code not in (200, 201):
        try:
            err = r.json()
            errors = err.get("errors") or []
            if errors:
                msgs = [
                    e.get("message") or e.get("title") or str(e) for e in errors
                ]
                detail = " | ".join(msgs)
            else:
                detail = str(err)[:800]
        except Exception:
            detail = r.text[:800]
        raise HTTPException(status_code=r.status_code, detail=detail)

    payload = r.json()
    data = payload.get("data") or {}
    offers = data.get("offers") or []
    return {"offers": _normalize_duffel_offers(offers)}


@app.get("/api/hotels")
def search_hotels(
    city: str = Query(..., min_length=2, max_length=120, description="Ciudad o zona"),
    check_in: date = Query(..., description="Entrada"),
    check_out: date = Query(..., description="Salida"),
    guests: int = Query(2, ge=1, le=9),
    rooms: int = Query(1, ge=1, le=5),
    radius_km: int = Query(15, ge=5, le=50),
):
    if check_out <= check_in:
        raise HTTPException(
            status_code=400,
            detail="La fecha de salida debe ser posterior a la de entrada.",
        )

    provider = os.getenv("HOTELS_PROVIDER", "geoapify").strip().lower()

    if provider in ("duffel", "stays", "duffel_stays"):
        lat, lon = _geocode_city(city)
        token = _get_duffel_token()
        guest_list = [{"type": "adult"} for _ in range(guests)]
        body = {
            "data": {
                "location": {
                    "radius": radius_km,
                    "geographic_coordinates": {
                        "latitude": lat,
                        "longitude": lon,
                    },
                },
                "check_in_date": check_in.isoformat(),
                "check_out_date": check_out.isoformat(),
                "guests": guest_list,
                "rooms": rooms,
            }
        }
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                DUFFEL_STAYS_SEARCH_URL,
                headers=_duffel_headers(token),
                json=body,
            )
        if r.status_code not in (200, 201):
            try:
                err = r.json()
                errors = err.get("errors") or []
                if errors:
                    msgs = [
                        e.get("message") or e.get("title") or str(e)
                        for e in errors
                    ]
                    detail = " | ".join(msgs)
                else:
                    detail = str(err)[:800]
            except Exception:
                detail = r.text[:800]
            raise HTTPException(status_code=r.status_code, detail=detail)
        payload = r.json()
        data = payload.get("data") or {}
        results = data.get("results") or []
        return {
            "hotels": _normalize_duffel_stays_results(results),
            "provider": "duffel",
            "note": "Duffel Stays: requiere que el producto Stays esté activado en tu cuenta Duffel.",
        }

    if provider in ("rapidapi", "rapid"):
        return _search_hotels_rapidapi(city, check_in, check_out, guests, rooms)

    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Modo geoapify: añade GEOAPIFY_API_KEY en .env. "
                "O usa HOTELS_PROVIDER=duffel y el mismo DUFFEL_ACCESS_TOKEN "
                "(si Duffel te activó Stays). "
                "O HOTELS_PROVIDER=rapidapi con RAPIDAPI_* en .env."
            ),
        )

    lat, lon = _geocode_city(city)
    radius_m = max(1000, min(radius_km * 1000, 50000))
    circle_filter = f"circle:{lon},{lat},{radius_m}"

    params = {
        "categories": GEOAPIFY_CATEGORIES,
        "filter": circle_filter,
        "limit": 25,
        "apiKey": api_key,
    }

    with httpx.Client(timeout=45.0) as client:
        r = client.get(GEOAPIFY_PLACES_URL, params=params)

    if r.status_code != 200:
        try:
            err = r.json()
            detail = str(err)[:800]
        except Exception:
            detail = r.text[:800]
        raise HTTPException(status_code=r.status_code, detail=detail)

    payload = r.json()
    features = payload.get("features") or []
    return {
        "hotels": _normalize_geoapify_hotels(features),
        "provider": "geoapify",
        "note": "Datos OSM; la imagen es mapa estático. Precios: enlaces de reserva.",
    }


@app.get("/api/hotels/rapidapi-test")
def rapidapi_hotel_test(request: Request):
    """
    Prueba rápida con cualquier API de hoteles en RapidAPI.
    En RapidAPI → tu API → Code snippets: copia X-RapidAPI-Host y la ruta del GET (ej. /v1/hotels/locations).
    Llama: /api/hotels/rapidapi-test?name=london&locale=en-gb (los query params se reenvían tal cual).
    """
    key = os.getenv("RAPIDAPI_KEY", "").strip()
    host = os.getenv("RAPIDAPI_HOTEL_HOST", "").strip()
    path = os.getenv("RAPIDAPI_TEST_PATH", "").strip()
    if not key or not host or not path:
        raise HTTPException(
            status_code=503,
            detail=(
                "Configura en .env: RAPIDAPI_KEY, RAPIDAPI_HOTEL_HOST, RAPIDAPI_TEST_PATH "
                "(Host y ruta salen de la página de la API en rapidapi.com → Code snippets)."
            ),
        )
    if not path.startswith("/"):
        path = "/" + path
    url = f"https://{host}{path}"
    params = dict(request.query_params)
    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": host,
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.get(url, headers=headers, params=params)
    if r.status_code != 200:
        try:
            err = r.json()
            detail = str(err)[:1200]
        except Exception:
            detail = r.text[:1200]
        raise HTTPException(status_code=r.status_code, detail=detail)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:2000]}


@app.get("/api/static-map")
def geoapify_static_map_proxy(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
):
    """
    Descarga el mapa estático en el servidor (la clave no va al navegador y
    evita bloqueos al cargar la imagen desde Geoapify en <img>.
    """
    api_key = os.getenv("GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Falta GEOAPIFY_API_KEY para generar el mapa.",
        )
    upstream = (
        "https://maps.geoapify.com/v1/staticmap?"
        + urlencode(
            {
                "style": "osm-bright",
                "width": 400,
                "height": 250,
                "scaleFactor": 2,
                "center": f"lonlat:{lon},{lat}",
                "zoom": 15,
                "apiKey": api_key,
            }
        )
    )
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        r = client.get(upstream)
    if r.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Geoapify static map ({r.status_code}): {r.text[:300]}",
        )
    ct = r.headers.get("content-type", "image/png")
    return Response(content=r.content, media_type=ct)


@app.get("/api/airbnb-link")
def airbnb_search_link(
    query: str = Query(..., min_length=2, description="Destino o zona"),
    check_in: date = Query(...),
    check_out: date = Query(...),
    adults: int = Query(2, ge=1, le=16),
    children: int = Query(0, ge=0, le=5),
    infants: int = Query(0, ge=0, le=5),
):
    """
    Airbnb no ofrece API pública de listados: solo armamos la URL de búsqueda en airbnb.com.
    """
    if check_out <= check_in:
        raise HTTPException(
            status_code=400,
            detail="La fecha de salida debe ser posterior a la de entrada.",
        )
    params = {
        "checkin": check_in.isoformat(),
        "checkout": check_out.isoformat(),
        "adults": adults,
        "query": query.strip(),
    }
    if children > 0:
        params["children"] = children
    if infants > 0:
        params["infants"] = infants
    url = "https://www.airbnb.com/s/homes?" + urlencode(params)
    return {"url": url, "note": "Búsqueda en Airbnb (listados en su web; sin API de ofertas)."}


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=12000)


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(..., min_length=1, max_length=40)


ATLAS_CHAT_SYSTEM = (
    "Eres el asistente de ATLAS GUIDE, una aplicación web para buscar vuelos "
    "(Duffel, códigos aeropuerto IATA de 3 letras) y hoteles (Geoapify por defecto, "
    "Duffel Stays, o RapidAPI con HOTELS_PROVIDER=rapidapi en .env). La pestaña Airbnb abre "
    "búsqueda en airbnb.com (sin API de listados). Responde en español, claro y breve."
)


def _local_atlas_reply(user_text: str) -> str:
    t = user_text.lower().strip()
    if not t:
        return "Escribe una pregunta sobre vuelos, hoteles o cómo usar la app."

    if any(x in t for x in ("hola", "buenos", "buenas", "hey", "hi")):
        return (
            "¡Hola! Soy el asistente de ATLAS GUIDE. Puedo explicarte cómo buscar "
            "vuelos (pestaña Vuelos), hoteles (pestaña Hoteles) o Airbnb (pestaña Airbnb). "
            "¿Qué necesitas?"
        )
    if "gracias" in t or "thanks" in t:
        return "De nada. Si surge otra duda sobre ATLAS GUIDE, aquí estaré."

    if any(x in t for x in ("vuelo", "vuelos", "iata", "duffel", "aeropuerto", "avión")):
        return (
            "En la pestaña Vuelos introduce origen y destino en código IATA de 3 letras "
            "(ej. MEX → CUN), la fecha de salida y número de adultos, luego Buscar vuelos. "
            "Necesitas DUFFEL_ACCESS_TOKEN en el archivo .env. Los resultados vienen de la API de Duffel."
        )
    if any(x in t for x in ("hotel", "hoteles", "alojamiento", "geoapify", "rapidapi", "habitacion", "habitación")):
        return (
            "En la pestaña Hoteles escribe la ciudad, fechas de entrada/salida, huéspedes y habitaciones. "
            "Por defecto se usa Geoapify (GEOAPIFY_API_KEY en .env). "
            "Duffel Stays: HOTELS_PROVIDER=duffel. RapidAPI: HOTELS_PROVIDER=rapidapi y RAPIDAPI_* según .env.example."
        )
    if "airbnb" in t:
        return (
            "Airbnb no ofrece API pública de listados. Usa la pestaña Airbnb: destino, fechas y huéspedes; "
            "se abre airbnb.com con esa búsqueda. También hay un acceso rápido desde Hoteles."
        )
    if any(x in t for x in (".env", "token", "clave", "api key", "configur")):
        return (
            "Configura un archivo .env en la carpeta del proyecto. Para vuelos: DUFFEL_ACCESS_TOKEN. "
            "Para hoteles: GEOAPIFY_API_KEY, o HOTELS_PROVIDER=duffel, o HOTELS_PROVIDER=rapidapi con RAPIDAPI_KEY, "
            "RAPIDAPI_HOTEL_HOST y RAPIDAPI_SEARCH_PATH. Copia .env.example como referencia."
        )
    if any(x in t for x in ("qué es", "que es", "atlas", "app", "aplicación", "aplicacion")):
        return (
            "ATLAS GUIDE te ayuda a comparar vuelos (Duffel) y hoteles (Geoapify, Duffel Stays o RapidAPI), "
            "con acceso rápido a búsqueda en Airbnb."
        )

    return (
        "Puedo orientarte sobre: vuelos (códigos IATA, Duffel), hoteles (Geoapify, Duffel o RapidAPI), "
        "el botón de Airbnb o la configuración (.env). Reformula tu pregunta con esas palabras "
        "o añade OPENAI_API_KEY en .env para respuestas más flexibles con IA."
    )


def _openai_chat_completion(dialog: list[dict]) -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    model = (os.getenv("OPENAI_CHAT_MODEL") or "gpt-4o-mini").strip()
    api_messages = [{"role": "system", "content": ATLAS_CHAT_SYSTEM}]
    api_messages.extend(dialog)
    body = {
        "model": model,
        "messages": api_messages,
        "max_tokens": 700,
        "temperature": 0.45,
    }
    with httpx.Client(timeout=90.0) as client:
        r = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    if r.status_code != 200:
        err = r.text[:500]
        raise RuntimeError(f"OpenAI HTTP {r.status_code}: {err}")
    payload = r.json()
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("Respuesta vacía de OpenAI")
    msg = (choices[0].get("message") or {}).get("content") or ""
    return msg.strip() or "No pude generar una respuesta. Intenta de nuevo."


@app.post("/api/chat")
def chat(req: ChatRequest):
    raw = [{"role": m.role, "content": m.content.strip()} for m in req.messages]
    dialog = [m for m in raw if m["role"] in ("user", "assistant") and m["content"]]
    if not dialog or dialog[-1]["role"] != "user":
        raise HTTPException(
            status_code=400,
            detail="Debe haber al menos un mensaje y el último debe ser del usuario.",
        )
    last_user = dialog[-1]["content"]
    window = dialog[-24:]

    if os.getenv("OPENAI_API_KEY", "").strip():
        try:
            reply = _openai_chat_completion(window)
            return {"reply": reply, "source": "openai"}
        except Exception as exc:
            reply = _local_atlas_reply(last_user)
            return {
                "reply": reply,
                "source": "local",
                "note": f"IA no disponible; respuesta local. ({str(exc)[:180]})",
            }

    return {"reply": _local_atlas_reply(last_user), "source": "local"}


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


app.mount("/assets", StaticFiles(directory=ROOT / "assets"), name="assets")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
