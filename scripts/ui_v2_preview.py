"""Isolated UI review server. Uses a temporary DB and fake Gemini, never .env.

Run from the repository root: .venv/bin/python scripts/ui_v2_preview.py
"""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from app.core.config import Settings
from app.db.migrate import upgrade_database
from app.main import create_app
from app.services.gemini_service import ProviderResult, Usage
from tests.fakes import FakeGeminiProvider, intent, memory_result, meal_image_result


def main():
    with TemporaryDirectory(prefix="nutricoach-ui-review-") as directory:
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{directory}/review.db",
            gemini_api_key=None,
            gemini_model="fake-gemini",
            app_environment="test",
        )
        upgrade_database(settings.database_url)
        provider = FakeGeminiProvider(
            intents=[intent() for _ in range(100)],
            replies=[ProviderResult(
                "**Birlikte dengeyi bulalım.**\n\nTek bir öğün, bütün gününü tanımlamaz.\n\n"
                "- Öğünlerini düzenli kaydet.\n- Porsiyon tahminlerini kontrol et.\n- Kendine uygun bir ritim bul.",
                Usage(100, 50, 150),
            ) for _ in range(100)],
            memories=[memory_result() for _ in range(100)],
            images=[meal_image_result() for _ in range(100)],
        )
        application = create_app(settings, provider=provider)
        # Allows the browser harness to refuse to write to a real server.
        @application.get('/ui-review-marker', include_in_schema=False)
        def review_marker():
            return {'isolated_ui_review': True}
        uvicorn.run(application, host="127.0.0.1", port=8766)


if __name__ == "__main__":
    main()
