# NutriCoach

Kalıcı beslenme kayıtları ve Gemini destekli koçluk için adım adım geliştirilen uygulama. **Aşama 7.5 tamamlandı:** Akıllı girdiler eklendi: Fotoğraftan Öğün Analizi (multimodal vision + önizleme/onay akışı, sıfır DB resim saklama), Web Araması / Google Search Grounding (markalı gıdalar ve güncel bilgiler için canlı web doğrulaması ve kaynak bağlantıları). Ayrıntılar [Aşama 7.5 rehberinde](docs/phase7_5.md) ve [Aşama 7 rehberinde](docs/phase7.md).

## Çalıştırma

Python 3.11 veya üzeri gerekir. Proje klasöründe:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env  # Yalnızca .env henüz yoksa; mevcut dosyanın üzerine yazma.
python -m app.db.migrate
uvicorn app.main:app --reload --host 127.0.0.1
```

Web Uygulaması: http://127.0.0.1:8000/
API dokümantasyonu: http://127.0.0.1:8000/docs
Sağlık kontrolü: http://127.0.0.1:8000/health

İlk migration çalıştırıldığında çalışma klasöründe `nutricoach.db` oluşturulur. Sunucu açılışta şema sürümünü kontrol eder; migration otomatik çalışmaz. Aynı klasörden yeniden başlatıldığında kayıtlar korunur. Farklı klasörlerden çalıştıracaksan `.env` içindeki URL'yi mutlak dosya yolu ile ayarla. Beslenme API’si için API anahtarı gerekmez. Gerçek AI sohbeti ve görsel analiz için backend `.env` dosyasında `GEMINI_API_KEY` ve `GEMINI_MODEL` ayarlanmalıdır; ayrıntılar [Aşama 3 rehberinde](docs/phase3.md).

## Kullanım
Web tarayıcınızdan http://127.0.0.1:8000/ adresini açtığınızda:
- Oturumunuz yoksa güvenli `/login` ekranına yönlendirilirsiniz.
- `/register` sayfasından yeni hesap oluşturabilir ve doğrudan giriş yapabilirsiniz.
- Giriş sonrasında oturum token'ı `HttpOnly`, `SameSite=Lax` cookie (`nutricoach_session`) olarak taşınır.
- Dashboard, Koç Sohbeti, Öğünler, İlerleme ve Profil sayfaları kullanıcı bazlı izole çalışır.
- **Fotoğraftan Öğün Analizi**: Koç sayfasındaki kamera butonundan veya Bugün sayfasındaki "Fotoğraftan Ekle" butonundan yemek fotoğrafı yükleyebilir, AI tahminlerini inceleyip düzenledikten sonra öğün olarak kaydedebilirsiniz. Fotoğraflar sunucuda veya veritabanında ASLA saklanmaz.
- **Web-aware Koç**: Koça zincir restoran/kahve markaları veya güncel beslenme bilgileri sorduğunuzda yanıtlar Google Arama ile doğrulanır ve kaynak bağlantılarıyla sunulur.

Ayrıca Swagger `/docs` ekranından doğrudan API kullanılabilir:
- `POST /api/v1/auth/register` veya `POST /api/v1/auth/login` ile oturum açılabilir.
- Giriş yapan kullanıcı için `/api/v1/me/...` uç noktaları kullanılır.
- Eski `/api/v1/users/{user_id}/...` uç noktaları varsayılan olarak kimlik doğrulama gerektirir (`allow_unauthenticated_legacy=False`) ve yetkisiz çapraz erişimler `403 Forbidden` ile engellenir.

## Testler

```sh
python -m pytest -q
```

Testler geçici SQLite dosyaları kullanır. 156 test ile şifreleme (Argon2id), session token yönetimi, CSRF koruması, kullanıcı izolasyonu (A ve B kullanıcıları), fotoğraf analizi/doğrulaması, Google arama grounding ve idempotency doğrulanır.

## Güvenlik ve Mimari

- Şifreler `Argon2id` ile hash'lenir, düz metin asla veritabanına kaydedilmez veya loglanmaz.
- Session token'ları 256-bit kriptografik rastgelelikle üretilir ve DB'de yalnızca `SHA-256` özeti saklanır.
- Değişiklik yapan (POST/PUT/PATCH/DELETE) tarayıcı isteklerinde session'a bağlı `X-CSRF-Token` zorunludur.
- Veritabanı seviyesinde `user_id` izolasyonu ve API seviyesinde `assert_user_access` uygulanır.
- Güvenlik başlıkları (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`) tüm yanıtlara eklenir.

Migration akışı: sunucuyu durdur, `python -m app.db.migrate` çalıştır, sonra sunucuyu başlat. Komut mevcut SQLite dosyasını backup API ile yedekler. `0001` temel kullanıcı/profil şemasını, `0002` beslenme tablolarını, `0003` sohbet tablolarını, `0004` uzun vadeli hafıza tablosunu, `0005` ise kimlik doğrulama tablolarını (`auth_sessions` ve şifre hash alanını) ekler. `alembic current` sürümü, `alembic check` model/şema farklarını gösterir.

Beslenme endpointleri ve veri sözleşmesi: [Aşama 2 rehberi](docs/phase2.md). Yeni sohbet endpointleri, intent şeması, gerçek Gemini kurulum/testi ve mevcut sınırlar: [Aşama 3 rehberi](docs/phase3.md).

`.env` ve veritabanı Git dışında tutulur. Yedek için sunucuyu durdurup SQLite dosyasını güvenli bir konuma kopyalayabilirsin; çalışan veritabanı için SQLite backup API kullanılmalı. Başka bir bilgisayarda tekrarlanabilir kurulum için `requirements-lock.txt` geliştirme/test ortamının kesin sürümlerini içerir: `python -m pip install -r requirements-lock.txt`.

Ayrıntılar: [Mimari ve geliştirme planı](docs/architecture.md).
