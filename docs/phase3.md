# Aşama 3 — Gemini ve kalıcı sohbet

Aşama 2'nin beslenme API'si ve Decimal/zaman dilimi sözleşmeleri korunur. Bu aşama intent çıkarımı, sınırlı eylemler, temel koç cevabı ve kalıcı sohbet ekler. Tam kişisel bağlam motoru, uzun süreli hafıza, frontend, auth ve Vertex AI eklenmedi.

## Kurulum ve migration

Sunucuyu durdur; aynı proje klasöründe:

```sh
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m app.db.migrate
alembic current
alembic check
```

`alembic current` → `0003 (head)`. Önceki migration'lar değiştirilmedi. `0003_chat.py` yalnızca yeni tabloları ekler; users, user_profiles, meals, meal_items ve weight_logs satırlarına dokunmaz. Standart migration komutu mevcut SQLite dosyasını backup API ile önce yedekler.

| Tablo | Alanlar / kısıtlar |
|---|---|
| conversations | id, user_id, created_at, updated_at; `(user_id,id)` unique |
| messages | id, user_id, conversation_id, role, content, status, created_at; ayrıca client_request_id, in_reply_to, effects_committed, action_results, error_type |
| ai_requests | id, user_id, message_id, model, phase, status, input_tokens, output_tokens, total_tokens, latency_ms, error_type, created_at |

Mesajın `(user_id,conversation_id)` FK'si başka kullanıcının sohbetine yazmayı engeller. Cevabın `(user_id,conversation_id,in_reply_to)` FK'si aynı kullanıcı/sohbet içindeki mesaja bağlıdır. AI isteğinin `(user_id,message_id)` FK'si de kullanıcı izolasyonunu korur. Rol/durum ve negatif olmayan token/latency CHECK kısıtları vardır.

`(user_id,client_request_id)` unique ile kullanıcı mesajı tek sefer kaydedilir. Assistant mesajında client_request_id null, in_reply_to zorunludur; her kullanıcı mesajı için en fazla bir assistant cevabı bulunur. `action_results` kayıt kimliği ve sürüm gibi küçük işlem sonuçlarını tutar; ham model çıktısını veya prompt'u tutmaz. Beslenme tablosuna yazılan değişikliklerle effects_committed/action_results aynı transaction'da commit edilir.

`alembic downgrade 0002` yeni sohbet tablolarını ve içlerindeki verileri siler; normal güncelleme/geri alma yöntemi değildir. Geri dönüşte uygun yedek ve uyumlu kod sürümü birlikte kullanılmalıdır.

## Sağlayıcı soyutlaması

[gemini_service.py](../app/services/gemini_service.py) içinde:

```python
class GeminiProvider(Protocol):
    model: str
    def extract_intent(self, payload: dict) -> ProviderResult: ...
    def generate_reply(self, payload: dict) -> ProviderResult: ...
```

`ProviderResult`: text + Usage(input_tokens, output_tokens, total_tokens). Gerçek adaptör `GoogleGeminiProvider`, resmi `google-genai` SDK'sında `genai.Client` ve `models.generate_content` kullanır. Route içinde model kodu yoktur. Yapılandırılmış çağrı `response_mime_type="application/json"` ve `response_json_schema` ile yapılır; dönen JSON ayrıca Pydantic ile backend'de doğrulanır.

Testlerde `create_app(settings, provider=FakeGeminiProvider(...))` ile enjekte edilir. Fake uygulaması [tests/fakes.py](../tests/fakes.py) içindedir. SDK adaptörü ayrıca gerçek ağ açmadan sahte SDK Client/response ile test edilir. Bu testler gerçek modelin dilsel doğruluğunu ölçmez.

API anahtarı yalnızca backend Settings üzerinden okunur. Her model çağrısı kendi SDK istemcisini açıp kapatır; timeout varsayılan 30 saniye, otomatik SDK retry kapalıdır. Bir normal mesaj genellikle iki çağrı gerektirir. Clarification ve intent hatasında ikinci çağrı yapılmaz.

## Intent sözleşmesi

Tam ve çalıştırılabilir Pydantic şema: [intents.py](../app/schemas/intents.py).

```json
{
  "actions": [{"type": "normal_chat"}],
  "needs_clarification": false,
  "clarification_question": null
}
```

`actions`, type alanıyla ayrılan en fazla 5 eylem içerir. Bilinmeyen type, fazladan alan, DB id'si, negatif/sonlu olmayan/iki ondalığı aşan besin değeri reddedilir. `needs_clarification=true` ise actions boş ve clarification_question dolu olmalıdır; bu durumda hiçbir beslenme değişikliği yapılmaz.

| type | Ek alanlar |
|---|---|
| normal_chat | Yok |
| nutrition_question | Yok |
| meal_create | meal: Aşama 2 MealWrite yapısı; occurred_at ayrıca null olabilir |
| meal_update | target: `{item_name, day?}`, quantity, unit |
| meal_delete | target: `{item_name, day?}`, scope: item veya meal |
| weight_log_create | weight: `{weight_kg, occurred_at?}` |
| profile_update | changes: yalnızca açıkça belirtilen ProfileWrite alanları |

Örnek extraction çıktısı (besin değerleri yalnızca örnek tahmindir):

```json
{
  "actions": [
    {
      "type": "meal_create",
      "meal": {
        "occurred_at": null,
        "meal_type": "other",
        "original_description": "200g tavuk ve 150g pilav yedim",
        "nutrition_source": "estimate",
        "confidence": "0.60",
        "items": [
          {"name":"Tavuk","quantity":"200.00","unit":"g","calories":"330.00","protein_g":"62.00","carbs_g":"0.00","fat_g":"7.20","source":"estimate","assumptions":"Pişmiş, derisiz tavuk göğsü varsayıldı."},
          {"name":"Pilav","quantity":"150.00","unit":"g","calories":"195.00","protein_g":"4.00","carbs_g":"42.00","fat_g":"0.50","source":"estimate","assumptions":"Pişmiş, ilave yağ içermeyen pirinç varsayıldı."}
        ]
      }
    },
    {"type":"nutrition_question"}
  ],
  "needs_clarification": false,
  "clarification_question": null
}
```

Backend original_description alanını gerçek kullanıcı mesajıyla doldurur. Modelden gelen yeni öğün/item değerleri estimate olarak işaretlenir; model kendiliğinden doğrulanmış etiket kaynağı ilan edemez. occurred_at null ise kullanıcı mesajının UTC kayıt zamanı kullanılır. Açık tarih için offset zorunludur; belirsiz tarihte modelden soru istenir. Tüm besin değerleri porsiyonun tamamı içindir.

Düzeltme örneği:

```json
{
  "actions": [{"type":"meal_update","target":{"item_name":"pilav","day":"2026-09-14"},"quantity":"100.00","unit":"g"}],
  "needs_clarification": false,
  "clarification_question": null
}
```

Backend yiyecek adını kullanıcıya ait item'larda arar. day yoksa mesajın yerel günü dahil son 7 gün taranır. Harf boyutu/Türkçe İ normalize edilir; yiyecek adı alt metin eşleşmesi kullanır, modelden SQL alınmaz. Sıfır veya birden fazla eşleşme varsa açıklama sorulur; keyfî “son kayıt” seçilmez. day belirtmek farklı günleri ayırabilir; aynı günde hâlâ belirsiz kayıtlar Aşama 2 öğün API'siyle düzenlenmelidir.

Miktar düzeltmesi aynı birimde yapılır; g/gram/gr gibi eş anlamlar desteklenir, kg→g veya kase→gram dönüşümü yapılmaz. Besin değerlerini backend eski miktara orantılı olarak Decimal ile hesaplar, iki ondalığa ROUND_HALF_UP uygular. Bu önceki tahmini ölçekler; yeni bir besin analizi değildir. source=user_corrected ve varsayım kaydı yazılır. Item silme diğer yiyecekleri korur; son item silinirse öğün de silinir. Aynı batch'te aynı öğüne birden fazla düzenleme şimdilik açıklama ister. Profil eylemi yalnızca belirtilen alanları değiştirir; diğer hedef/profil alanlarını korur.

## Mesaj işleme akışı

“200g tavuk ve 150g pilav yedim. Akşam pizza yiyebilir miyim?”

1. Kullanıcı kapsamı ve sohbet kontrol edilir. User message pending olarak kaydedilip commit edilir.
2. Oturum kapatılır. Gemini, mevcut mesaj + UTC şimdi + timezone + sınırlı son sohbet ile structured intent üretir.
3. Ham model JSON'u Pydantic doğrulamasından geçer; geçmezse hiçbir beslenme eylemi uygulanmaz.
4. Backend tüm düzeltme/silme hedeflerini sahiplik kontrolüyle çözer. Belirsizlik varsa tüm batch durur ve soru kaydedilir.
5. meal_create mevcut nutrition servisine gider. Servisler `commit=False` ile aynı transaction'a katılır; batch'in herhangi bir kısmı başarısızsa tüm beslenme değişiklikleri rollback olur. Aşama 2 route'larında varsayılan commit davranışı değişmez.
6. Öğün/item ve mesajın işlem sonucu birlikte commit edilir. Bu adımdan sonra koç hatası öğünü geri almaz.
7. Yeni oturumda bugünkü toplamlar tekrar hesaplanır; nutrition_question varsa mevcut weekly_summary de alınır. Örnekte koç, yeni tavuk/pilav öğününü içeren toplamı görür.
8. DB oturumu kapandıktan sonra ikinci Gemini çağrısı doğal cevap üretir. Modelin DB değiştirme yetkisi bu çağrıda yoktur.
9. Assistant mesajı, user message durumu ve sohbet updated_at kalıcı yazılır. Her çağrının token/latency/durum logu ayrı kaydedilir.

Bu, Aşama 4'ün tam context engine'i değildir: profil katmanları, ilgili uzun süreli hafıza, kilo trendi ve eski sohbet özetleme yoktur. Son sohbet varsayılan 10 mesaj/8000 karakterle sınırlıdır; yalnızca aynı kullanıcı/sohbette completed mesajlar seçilir. Mevcut mesaj geçmişe ikinci kez eklenmez. Uzun sohbetin tamamı gönderilmez.

## Endpointler ve durumlar

Ortak önek: `/api/v1/users/{user_id}`.

| Yöntem | Yol | Sonuç |
|---|---|---|
| POST | `/conversations` | 201; yeni sohbet, gövde gerekmiyor |
| GET | `/conversations?limit=100&offset=0` | Oluşturulma zamanına göre azalan liste |
| GET | `/conversations/{conversation_id}` | 200; başka kullanıcı veya yoksa 404 |
| POST | `/conversations/{conversation_id}/messages` | User + assistant sonucu |
| GET | `/conversations/{conversation_id}/messages?limit=100&offset=0` | Oluşturulma zamanına göre artan mesaj geçmişi |

Liste limitleri Aşama 2 ile aynı: varsayılan 100, en fazla 500. UUID alanları doğrulanır.

Mesaj POST gövdesi:

```json
{
  "client_request_id": "c3ef9d62-8c51-48b2-8d7e-e248bd009fd3",
  "content": "200g tavuk ve 150g pilav yedim. Akşam pizza yiyebilir miyim?"
}
```

Her yeni mesaj için yeni UUID üret. **Aynı mesajın retry'ında aynı UUID ve aynı içeriği kullan.** Unique kapsam kullanıcıdır, yalnızca sohbet değildir. Aynı ID farklı içerik/sohbet için kullanılırsa 409; mevcut pending mesaj için 202; tamamlanmış/başarısız mevcut mesajın aynı sonucu için 200 döner. Retry tekrar model çağırmaz ve işlem uygulamaz. Yeni mesaj 201 döner; AI işleminin başarısını ayrıca user_message.status üzerinden kontrol et.

Yanıt `user_message` ve `assistant_message` içerir. Her mesaj id, rol, içerik, zaman, durum, error_type, effects_committed ve action_results taşır. Beslenme işlem sonucu esas olarak user_message üzerindedir; assistant mesajı user message'a in_reply_to ile bağlıdır. pending durumda assistant_message null olabilir.

- completed: cevap veya açıklama sorusu kalıcı kaydedildi.
- failed + effects_committed=false: beslenme değişikliği uygulanmadı.
- failed + effects_committed=true: değişiklikler kalıcı, AI cevabı alınamadı; kullanıcıya bu durum açıkça söylenir.
- pending: bir işlem çalışıyor veya süreç kesildi; retry eylemi yeniden başlatmaz.

Timeout, invalid_output, rate_limit, authentication, network, model_unavailable, configuration, provider_error ayrı hata türleridir. DB/action hataları action_error olur. Ham SDK exception/prompt/anahtar kullanıcıya veya ai_requests tablosuna yazılmaz. Bilinen yapılandırılmış anahtarın mesaj/cevap içinde geçmesi de redakte edilir. Normal mesaj içeriği kullanıcı isteği gereği messages tablosunda kalıcıdır; bu tablo bir hata logu değildir.

Token alanları metadata yoksa null, gerçek sıfır varsa 0 olur. output_tokens SDK candidates_token_count değeridir; total_tokens düşünme gibi ek tokenları içerebileceğinden input+output toplamına zorla eşitlenmez. Fiyat veya maliyet tahmini saklanmaz. ai_requests içinde yalnızca model, çağrı aşaması, durum, sayılar, hata sınıfı ve ilişkisel kimlikler bulunur.

## Gerçek Gemini ile manuel test

Bu teslimattaki otomatik testler gerçek Gemini çağırmaz. Gerçek model/schema uyumluluğu ve dilsel davranış aşağıdaki adımlarla doğrulanmalıdır.

1. [Google AI Studio](https://aistudio.google.com/) hesabından Gemini Developer API anahtarı ve structured-output destekli kullanılabilir model kimliği edin. Google Cloud kredilerinin bu API'nin faturalandırmasını karşıladığını ayrıca doğrula; bu entegrasyon Vertex AI değildir.
2. Mevcut `.env` dosyasına backend ayarlarını ekle; anahtarı terminal çıktısına, koda veya istemciye yazma:

```dotenv
GEMINI_API_KEY=buraya_kendi_anahtarin
GEMINI_MODEL=hesabinda_kullanilabilir_model_kimligi
NUTRICOACH_GEMINI_TIMEOUT_SECONDS=30
NUTRICOACH_CHAT_RECENT_MESSAGES=10
NUTRICOACH_CHAT_HISTORY_CHARS=8000
```

Eski `NUTRICOACH_GEMINI_API_KEY` ve `NUTRICOACH_GEMINI_MODEL` adları da desteklenir; iki ad birden varsa GEMINI_* önceliklidir. Model varsayılan olarak boş bırakıldı; sürümü değişebilen bir model kod içine gömülmedi. Ayarlar eksikse sohbet configuration hatası kaydeder; Aşama 2 API'leri çalışır.

3. Migration'dan sonra `uvicorn app.main:app --reload --host 127.0.0.1` ile başlat. Ayar değişikliğinde yeniden başlat.
4. [Swagger](http://127.0.0.1:8000/docs) üzerinden kullanıcı oluştur veya mevcut user_id'yi kullan. İstersen kullanıcı profilindeki hedefleri ayarla.
5. `POST .../conversations` çağır. Dönen conversation_id ile mesaj POST örneğini gönder. Model porsiyon varsayımlarını yetersiz bulursa soru sorabilir; bu durumda yeni UUID ile açıklama mesajını gönder.
6. `user_message.status`, `effects_committed` ve `action_results` alanlarını incele. Kaydedilen meal_id ile Aşama 2 `GET .../meals/{meal_id}` ve `/nutrition/daily` sonuçlarını kontrol et.
7. Aynı request'i aynı UUID ile tekrar gönder: aynı mesaj kimlikleri ve sonuç dönmeli; öğün sayısı artmamalı.
8. Yeni UUID ile “Pilav 150 değil 100 gramdı” gönder. Tek eşleşme varsa mevcut öğün değişmeli; çoklu eşleşmede soru gelmeli. “Az önceki sütü sil” benzeri mesajı yalnızca test kaydın üzerinde dene.
9. `GET .../conversations/{id}/messages` ile geçmişi oku, sunucuyu yeniden başlat ve aynı geçmişin korunduğunu doğrula.
10. Geçersiz anahtar/model deneyerek hata state'lerini görebilirsin. Bunun için yeni mesaj UUID'si kullan; önceden effects_committed=true olan isteği farklı UUID ile otomatik yeniden gönderme.

Koç timeout sonrası kaydı koruma, rate limit ve ağ hataları gerçek servisi zorlamadan fake testlerle doğrulanır. Token kayıtları yerel ai_requests tablosundadır; bu aşamada ayrıca kullanım paneli/endpoint'i yoktur.

## Testler ve kalan sınırlar

`python -m pytest -q` ile Aşama 1–3 paketinin tamamını çalıştır. Model sırasında hiçbir DB bağlantısının checkout edilmediği de fake sağlayıcı callback'iyle doğrulanır. Migration testi Aşama 2'nin beş tablosuna veri koyar, 0003'e geçer, dosya inode'u ve eski satırları/yedeği karşılaştırır.

Teslimat doğrulaması: **79 test geçti**, `alembic check` şema farkı bulmadı, `pip check` bağımlılık hatası bulmadı. TestClient bağımlılıklarından iki deprecation uyarısı mevcut. Yerel gerçek DB de migration öncesi yedekle karşılaştırıldı; Aşama 2 satırları birebir korundu ve SQLite integrity/foreign-key kontrolleri geçti.

Aşama 4 öncesi bilinen sınırlar:

- Gerçek Gemini ile uçtan uca çağrı bu teslimatta yapılmadı; seçilecek modelin JSON schema desteği ve extraction doğruluğu elle denenmeli.
- Yapısal doğrulama semantik doğruluğu garanti etmez. Tahminler ve modelin seçtiği eylemler kullanıcı tarafından kayıt API'sinden incelenip düzeltilebilir.
- Süreç model çağrısı ortasında ölürse pending mesaj otomatik kurtarılmaz. Aynı ID güvenle pending döner; yönetimli kurtarma/lease/queue sonraki iş olmalıdır. Rastgele yeni ID ile tekrar kaydetmek yerine önce kalıcı işlem sonucu incelenmelidir.
- Aynı konuşmada farklı request ID'leriyle paralel mesajlar sıraya alınmaz. Şimdilik istemci mesajları sırayla göndermeli. Bir request içindeki beslenme değişiklikleri atomiktir.
- Düzeltme yalnızca tek eşleşme ve aynı birimde miktar değişikliğini destekler. Aynı gün aynı isimli birden fazla item seçimini doğal dilde çözen ek seçim akışı henüz yoktur.
- Auth yoktur. Kullanıcı kapsamı ve DB FK'ları korunur; URL'deki kimlik gerçek oturumdan doğrulanmaz. Sunucu yerel kullanımda kalır.
- Tam build_coach_context, profil/tercih katmanları, kilo trendleri ve hafıza Aşama 4 ve sonrasına bırakıldı.

Resmi dayanaklar: [Google GenAI Python SDK](https://github.com/googleapis/python-genai), [Gemini structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en). Kurulu SDK'nın desteklediği GenerateContentConfig/HttpOptions alanları yerel olarak da doğrulandı.
