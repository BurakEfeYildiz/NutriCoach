from decimal import Decimal, InvalidOperation
import time

import httpx


def number(value):
    try:
        return Decimal(str(value)).quantize(Decimal(".01")) if value is not None else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def sodium_mg(value):
    try:
        return (Decimal(str(value)) * Decimal("1000")).quantize(Decimal(".01")) if value is not None else None
    except (InvalidOperation, TypeError, ValueError):
        return None


class OpenFoodFactsProvider:
    def __init__(self, user_agent: str, timeout_seconds: int = 15):
        self.headers = {"User-Agent": user_agent}
        self.timeout = timeout_seconds

    def _get(self, client: httpx.Client, url: str, params: dict) -> httpx.Response:
        response = client.get(url, params=params)
        if response.status_code in (429, 502, 503, 504):
            time.sleep(0.25)
            response = client.get(url, params=params)
        response.raise_for_status()
        return response

    def search(self, query: str, page_size: int = 8) -> list[dict]:
        # OFF's v2 structured endpoint does not currently apply a generic `q`
        # parameter. The documented legacy full-text endpoint remains the
        # supported route for an explicit user search.
        params = {"search_terms": query, "search_simple": 1, "action": "process", "json": 1,
                  "page_size": min(max(page_size, 1), 20),
                  "fields": "code,product_name,brands,countries,nutriments,nutrition_data_per"}
        with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
            response = self._get(client, "https://world.openfoodfacts.org/cgi/search.pl", params)
            return [self.normalize(p) for p in response.json().get("products", []) if p.get("code")]

    def detail(self, barcode: str) -> dict:
        params = {"fields": "code,product_name,brands,countries,nutriments,nutrition_data_per,serving_size"}
        with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
            response = self._get(client, f"https://world.openfoodfacts.org/api/v3/product/{barcode}", params)
            body = response.json()
            product = body.get("product")
            if not product:
                raise LookupError("Ürün Open Food Facts üzerinde bulunamadı.")
            return self.normalize(product)

    def normalize(self, raw: dict) -> dict:
        n = raw.get("nutriments") or {}
        energy = number(n.get("energy-kcal_100g"))
        basis = "per_100g"
        suffix = "_100g"
        if raw.get("nutrition_data_per") == "serving" and energy is None:
            basis, suffix = "per_serving", "_serving"
            energy = number(n.get("energy-kcal_serving"))
        macros = {
            "calories": energy,
            "protein_g": number(n.get(f"proteins{suffix}")),
            "carbs_g": number(n.get(f"carbohydrates{suffix}")),
            "fat_g": number(n.get(f"fat{suffix}")),
            "fiber_g": number(n.get(f"fiber{suffix}")),
            "sugar_g": number(n.get(f"sugars{suffix}")),
            "sodium_mg": sodium_mg(n.get(f"sodium{suffix}")),
        }
        code = str(raw.get("code") or "")
        return {
            "canonical_name": str(raw.get("product_name") or "İsimsiz ürün").strip(), "brand": (raw.get("brands") or None),
            "source": "open_food_facts", "source_food_id": code, "source_data_type": "branded_product",
            "category": None, "barcode": code, "country": raw.get("countries"),
            "basis_type": basis, "basis_amount": Decimal("100.00") if basis == "per_100g" else Decimal("1.00"),
            "basis_unit": "g" if basis == "per_100g" else "serving", **macros,
            "reliability": "crowdsourced_label", "source_metadata": {
                "serving_size": raw.get("serving_size"), "provider": "Open Food Facts",
                "database_license": "ODbL 1.0", "content_license": "Database Contents License",
            }, "portions": [],
        }
