# NutriCoach

Kalıcı beslenme kayıtları ve Gemini destekli koçluk için adım adım geliştirilen uygulama. **Aşama 4 tamamlandı:** Veritabanı ve Python hesaplamalarına dayalı deterministik Context Engine eklendi (profil, bugün, dün, 7 ve 14 günlük agregasyonlar, kilo trendi, uygunluk seçimi ve token limitleri). Ayrıntılar [Aşama 4 rehberinde](docs/phase4.md). Hafıza (Aşama 5), auth ve web arayüzü henüz yok.

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

API dokümantasyonu: http://127.0.0.1:8000/docs

Sağlık kontrolü: http://127.0.0.1:8000/health

İlk migration çalıştırıldığında çalışma klasöründe `nutricoach.db` oluşturulur. Sunucu açılışta şema sürümünü kontrol eder; migration otomatik çalışmaz. Aynı klasörden yeniden başlatıldığında kayıtlar korunur. Farklı klasörlerden çalıştıracaksan `.env` içindeki URL'yi mutlak dosya yolu ile ayarla. Beslenme API’si için API anahtarı gerekmez. Gerçek AI sohbeti için backend `.env` dosyasında `GEMINI_API_KEY` ve `GEMINI_MODEL` ayarlanmalıdır; ayrıntılar [Aşama 3 rehberinde](docs/phase3.md).

## Kullanım

Swagger `/docs` ekranından `POST /api/v1/users` çağır:

```json
{"name": "Demo", "timezone": "Europe/Istanbul"}
```

Dönen `id` ile `GET /api/v1/users/{user_id}/profile` veya `PUT /api/v1/users/{user_id}/profile` kullan. Hedefler varsayılan olarak boştur. Örnek hedefler kişisel öneri değildir:

```json
{"calorie_target": 2200, "protein_target_g": 150}
```

`PUT` profilin tamamını değiştirir; gönderilmeyen alanlar `null` olur. İleride kısmi düzenleme için `PATCH` eklenecek. Kilo kayıtları `/api/v1/users/{user_id}/weight-logs` üzerinden yönetilir; güncel kilo `/weight-logs/current` ile geçmişten okunur.

## Testler

```sh
python -m pytest -q
```

Testler geçici SQLite dosyaları kullanır. Migration sırasında dosya ve eski verilerin korunması, öğün/item değişiklikleri, silme, Decimal hassasiyeti, İstanbul gece yarısı ve DST sınırları, eksik günler, kullanıcı kapsamı ve kilo CRUD kontrol edilir. Sohbet testleri fake sağlayıcı kullanır; gerçek API çağrısı yapmaz. Intent doğrulama, düzeltme, clarification, eşzamanlı retry, token/hata kayıtları ve koç hatasında kayıtların korunması da test edilir.

## Geliştirme sınırları

Kimlik doğrulama henüz yoktur: kullanıcı kimliği erişim yetkisi sağlamaz; API'ye ulaşan biri başka bir kullanıcı kimliğini de kullanabilir. Bu aşama yalnızca yerel geliştirme içindir. İnternete veya yerel ağa açmadan önce kimlik doğrulama ve yetkilendirme eklenecek. Sunucu loopback üzerinde çalıştırılır; izin verilen Host adları da yerel adreslerle sınırlıdır.

Migration akışı: sunucuyu durdur, `python -m app.db.migrate` çalıştır, sonra sunucuyu başlat. Komut mevcut SQLite dosyasını backup API ile yedekler. `0001` eski kullanıcı/profil şemasını doğrulayıp verileri değiştirmeden benimser; `0002` beslenme tablolarını, `0003` sohbet/mesaj/AI istek tablolarını ekler. Mevcut DB'ye körlemesine `alembic stamp head` çalıştırma. `alembic current` sürümü, `alembic check` model/şema farklarını gösterir.

Beslenme endpointleri ve veri sözleşmesi: [Aşama 2 rehberi](docs/phase2.md). Yeni sohbet endpointleri, intent şeması, gerçek Gemini kurulum/testi ve mevcut sınırlar: [Aşama 3 rehberi](docs/phase3.md).

`.env` ve veritabanı Git dışında tutulur. Yedek için sunucuyu durdurup SQLite dosyasını güvenli bir konuma kopyalayabilirsin; çalışan veritabanı için SQLite backup API kullanılmalı. Başka bir bilgisayarda tekrarlanabilir kurulum için `requirements-lock.txt` geliştirme/test ortamının kesin sürümlerini içerir: `python -m pip install -r requirements-lock.txt`.

Ayrıntılar: [Mimari ve geliştirme planı](docs/architecture.md).
