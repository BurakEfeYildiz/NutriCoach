"""Small, repeatable USDA FoodData Central importer.

Examples:
  python scripts/import_usda_foods.py --common
  python scripts/import_usda_foods.py --query "plain yogurt" --alias yoğurt
  python scripts/import_usda_foods.py --fdc-id 171287
"""
import argparse
from collections import Counter
import httpx

from app.core.config import Settings
from app.db.database import create_database
from app.models import activity, auth, chat, food, memory, nutrition, user  # noqa: F401
from app.services.food_data import upsert_external_food
from app.services.food_providers.usda import USDAFoodDataProvider

COMMON = {
    "Eggs, Grade A, Large, egg whole": ["yumurta", "büyük yumurta"],
    "Chicken, broilers or fryers, breast, meat only, cooked, roasted": ["tavuk göğsü", "pişmiş tavuk göğsü"],
    "Rice, white, long-grain, regular, enriched, cooked": ["pirinç", "pişmiş pirinç"],
    "Bananas, ripe and slightly ripe, raw": ["muz", "olgun muz"],
    "Milk, whole, 3.25% milkfat, with added vitamin D": ["süt", "tam yağlı süt"],
    "Yogurt, plain, whole milk": ["yoğurt", "sade yoğurt"],
    "Potatoes, gold, without skin, raw": ["patates", "çiğ patates"],
    "Nuts, almonds, whole, raw": ["badem", "çiğ badem"],
    "Oil, olive, salad or cooking": ["zeytinyağı", "zeytin yağı"],
}
PRIORITY = {"Foundation": 0, "SR Legacy": 1, "Survey (FNDDS)": 2}


def select_best(rows: list[dict], query: str) -> dict:
    if not rows:
        raise LookupError("USDA sorgusu sonuç vermedi.")
    wanted = set(query.casefold().replace(",", " ").split())
    def score(row):
        description = (row.get("description") or "").casefold().replace(",", " ")
        found = sum(word in description.split() for word in wanted)
        return (-found, PRIORITY.get(row.get("dataType"), 9), len(description))
    return sorted(rows, key=score)[0]


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--common", action="store_true")
    mode.add_argument("--query")
    mode.add_argument("--fdc-id")
    parser.add_argument("--alias", action="append", default=[])
    parser.add_argument("--demo-key", action="store_true", help="Yalnızca küçük geliştirme smoke importu için USDA DEMO_KEY kullanır.")
    args = parser.parse_args()
    settings = Settings()
    configured = settings.usda_fdc_api_key.get_secret_value() if settings.usda_fdc_api_key else None
    key = "DEMO_KEY" if args.demo_key else configured
    if not key: parser.error("USDA_FDC_API_KEY ayarla veya küçük yerel deneme için --demo-key kullan.")
    provider = USDAFoodDataProvider(key, settings.food_provider_timeout_seconds)
    engine, factory = create_database(settings.database_url)
    results = []
    skipped = []
    try:
        with factory() as session:
            if args.fdc_id:
                food = upsert_external_food(session, provider.normalize(provider.detail(args.fdc_id)), args.alias)
                results.append(food)
            else:
                queries = COMMON.items() if args.common else [(args.query, args.alias)]
                for query, aliases in queries:
                    try:
                        rows = provider.search(query, page_size=10)
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            skipped.append((query, "USDA API kotası doldu (429); kalan sorgular durduruldu."))
                            break
                        raise
                    exact = next((row for row in rows if (row.get("description") or "").casefold() == query.casefold()), None)
                    if args.common and not exact:
                        skipped.append((query, "USDA tam ad eşleşmesi bulunamadı; farklı hazırlama durumuna alias bağlanmadı."))
                        continue
                    try:
                        best = exact or select_best(rows, query)
                    except LookupError as exc:
                        skipped.append((query, str(exc)))
                        continue
                    # Search rows contain the required per-100 g nutrients. Detail fetches
                    # are reserved for --fdc-id so the common import stays quota-friendly.
                    try:
                        food = upsert_external_food(session, provider.normalize(best), aliases)
                        results.append(food)
                    except ValueError as exc:
                        skipped.append((query, str(exc)))
    finally:
        engine.dispose()
    sources = Counter(food.source_data_type for food in results)
    print(f"{len(results)} gerçek USDA kaydı işlendi: {dict(sources)}")
    print(f"{len(skipped)} kullanılamaz kayıt atlandı.")
    for food in results: print(f"- {food.source_food_id}: {food.canonical_name} [{food.basis_type}]")
    for query, reason in skipped: print(f"- atlandı: {query}: {reason}")


if __name__ == "__main__": main()
