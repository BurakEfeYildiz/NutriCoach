from decimal import Decimal, InvalidOperation

import httpx


NUTRIENT_NUMBERS = {
    "1008": "calories", "1003": "protein_g", "1005": "carbs_g", "1004": "fat_g",
    "1079": "fiber_g", "2000": "sugar_g", "1063": "sugar_g", "1093": "sodium_mg",
    # SR Legacy detail responses retain the original USDA nutrient numbers.
    "208": "calories", "957": "calories", "958": "calories", "2047": "calories", "2048": "calories",
    "203": "protein_g", "205": "carbs_g", "204": "fat_g",
    "291": "fiber_g", "269": "sugar_g", "307": "sodium_mg",
}


def decimal_or_none(value):
    try:
        return Decimal(str(value)).quantize(Decimal(".01")) if value is not None else None
    except (InvalidOperation, ValueError, TypeError):
        return None


class USDAFoodDataProvider:
    def __init__(self, api_key: str, timeout_seconds: int = 15):
        if not api_key:
            raise ValueError("USDA FoodData Central API anahtarı yapılandırılmamış.")
        self.api_key = api_key
        self.timeout = timeout_seconds
        self.base_url = "https://api.nal.usda.gov/fdc/v1"

    def search(self, query: str, page_size: int = 10) -> list[dict]:
        payload = {
            "query": query,
            "pageSize": min(max(page_size, 1), 50),
            "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
        }
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.base_url}/foods/search", params={"api_key": self.api_key}, json=payload)
            response.raise_for_status()
            return response.json().get("foods", [])

    def detail(self, fdc_id: str | int) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/food/{fdc_id}", params={"api_key": self.api_key})
            response.raise_for_status()
            return response.json()

    def normalize(self, raw: dict) -> dict:
        nutrients = {name: None for name in NUTRIENT_NUMBERS.values()}
        for row in raw.get("foodNutrients", []):
            nutrient = row.get("nutrient") or row
            number = str(nutrient.get("number") or row.get("nutrientNumber") or "")
            key = NUTRIENT_NUMBERS.get(number)
            if key:
                nutrients[key] = decimal_or_none(row.get("amount", row.get("value")))
        portions = []
        for row in (raw.get("foodPortions") or raw.get("foodMeasures") or []):
            grams = decimal_or_none(row.get("gramWeight"))
            if not grams or grams <= 0:
                continue
            measure = row.get("measureUnit") or {}
            label = row.get("portionDescription") or row.get("disseminationText") or row.get("modifier") or row.get("measureUnitName") or measure.get("name") or "porsiyon"
            portions.append({
                "label": str(label)[:120], "amount": decimal_or_none(row.get("amount")) or Decimal("1.00"),
                "unit": str(measure.get("abbreviation") or measure.get("name") or row.get("measureUnitName") or "portion")[:40],
                "gram_equivalent": grams, "ml_equivalent": None, "serving_equivalent": None, "source": "usda",
            })
        return {
            "canonical_name": str(raw.get("description") or "").strip(),
            "brand": None,
            "source": "usda", "source_food_id": str(raw.get("fdcId")),
            "source_data_type": raw.get("dataType"), "category": (raw.get("foodCategory") or {}).get("description") if isinstance(raw.get("foodCategory"), dict) else raw.get("foodCategory"),
            "barcode": None, "country": "US", "basis_type": "per_100g", "basis_amount": Decimal("100.00"), "basis_unit": "g",
            **nutrients, "reliability": "government_reference", "source_metadata": {
                "publication_date": raw.get("publicationDate"), "provider": "USDA FoodData Central",
                "license": "CC0 1.0 / public domain",
            },
            "portions": portions,
        }
