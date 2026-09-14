# Aşama 4 — Context Engine (Bağlam Motoru)

Aşama 1, 2 ve 3'ün temel beslenme, veritabanı ve Gemini structured intent mimarisi korunarak; modelin salt mevcut mesaj ve kısa geçmişe dayanması yerine, kullanıcının kalıcı verilerinden deterministik olarak türetilen yapılandırılmış bir **Context Engine** uygulanmıştır.

Bu aşamada:
- **Veritabanı / Python**: Tek doğruluk kaynağı ve hesaplama motorudur (toplamlar, ortalamalar, saat dilimi sınırları, trendler ve hedef farkları burada hesaplanır).
- **Gemini**: Yorumlama ve doğal dil koçluğu üretir; modelden deterministik olarak hesaplanabilecek veri uydurması veya toplam hesabı yapması istenmez.

---

## 1. Mimari ve Veri Akışı

```
[Kullanıcı Mesajı]
       ↓
[1. Aşama: Intent Extraction (Gemini)] → Sade girdi (yalnızca son mesajlar + saat dilimi)
       ↓
[Pydantic Doğrulama & Eylem Çözümleme]
       ↓
[DB Transaction: Beslenme / Kilo / Profil Değişiklikleri Commit]
       ↓
[2. Aşama: build_coach_context(...)] → Eylemler uygulandıktan sonraki güncel durum okunur
       ↓
[Relevance Selection] → Soru tipi ve intent'e göre gerekli bölümler filtrelenir
       ↓
[Deterministik Hesaplamalar] → Bugün, dün, 7 ve 14 günlük agregasyon, kilo trendi
       ↓
[3. Aşama: Coach Çağrısı (Gemini)] → Yapılandırılmış CoachContext ile doğal cevap
       ↓
[Assistant Mesajı Kaydı]
```

### Temel Soyutlama
`build_coach_context(session, user_id, conversation_id, message_id, current_message, now, plan, action_results, settings) -> CoachContext`
- HTTP route'larına bağımlı değildir; saf veritabanı oturumu ve zaman parametresiyle bağımsız test edilebilir.
- Ham veritabanı ID'lerini (UUID vb.) Gemini'ye aktarmaz; yalnızca koçluk için anlamlı verileri sunar.

---

## 2. Bağlam Bileşenleri (Context Sections)

| Bölüm | Şema / İçerik | Detay / Semantik |
|---|---|---|
| `profile` | `ProfileContext` | Yaş (kullanıcı yerel gününden hesaplanır), cinsiyet, boy, kilo hedefi, haftalık değişim hedefi, aktivite seviyesi, kalori ve makro hedefleri. Eksikler `null`. |
| `today` | `TodayContext` | Kullanıcının saat dilimine göre yerel gün, kayıt var mı (`has_records`), öğün sayısı, makro/kalori toplamları, hedeften kalanlar, öğün ve yiyecek detayları. `detail_truncated` bayrağı. |
| `yesterday` | `YesterdayContext` | Bir önceki yerel günün kompakt özeti: tarih, kayıt varlığı, öğün sayısı ve toplamlar. |
| `recent_7_days` | `PeriodSummaryContext` | Son 7 günün istatistikleri: kayıtlı gün sayısı, eksik gün sayısı, kayıtlı günlerin ortalama kalori ve makroları, min/max kalori, kalori hedefi varsa hedef üstü/altı gün sayıları. |
| `recent_14_days` | `PeriodSummaryContext` | Son 14 günün orta vadeli istatistikleri (7 gün ile aynı kompakt agregasyon). |
| `weight` | `WeightContext` | Güncel kilo ve tarihi, ölçüm sayısı, deterministik kilo trendi (`insufficient_data`, `stable`, `increasing`, `decreasing`), toplam delta (kg), haftalık değişim hızı (kg/hafta), ölçüm geçmişi. |
| `recent_messages` | `list[RecentChatMessageContext]` | Aynı kullanıcı ve sohbete ait, tamamlanmış son mesajlar (mevcut mesaj hariç). |

---

## 3. Uygunluk ve Bölüm Seçimi (Relevance Selection)

Her istekte tüm veri tabanını modele yığmak yerine, deterministik ve test edilebilir kural setiyle ilgili bölümler seçilir:

1. **Normal Sohbet (`normal_conversation`)**:
   - Örn: *"Merhaba"*, *"Günaydın"*, kısa selamlaşmalar.
   - Eklenen bölümler: `profile`, `recent_messages`.
   - Gereksiz 14 günlük liste veya kilo geçmişi eklenmez.
2. **Bugünün Beslenmesi (`today_nutrition`)**:
   - Örn: *"Bugün ne kadar protein aldım?"*, *"Akşam pizza yedim"*, `meal_create` eylemleri.
   - Eklenen bölümler: `profile`, `today`, `recent_messages`. (Dün anıldıysa `yesterday` eklenir).
3. **Yakın Geçmiş ve İlerleme (`recent_nutrition`)**:
   - Örn: *"Son iki haftadır nasıl gidiyorum?"*, *"Haftalık ortalamam kaç?"*.
   - Eklenen bölümler: `profile`, `today`, `yesterday`, `recent_7_days`, `recent_14_days`, `recent_messages`.
4. **Kilo ve Gidişat (`weight_progress`)**:
   - Örn: *"Kilom nasıl gidiyor?"*, *"Tartıldım 74.5 kg"*, `weight_log_create` eylemleri.
   - Eklenen bölümler: `profile`, `weight`, `recent_7_days`, `recent_messages`.
5. **Hedef / Profil Soruları (`profile_goals`)**:
   - Örn: *"Kalori hedefim neydi?"*, `profile_update` eylemleri.
   - Eklenen bölümler: `profile`, `today`, `recent_messages`.

---

## 4. Eksik Veri ve Deterministik Hesaplama Kuralları

- **Eksik Gün != Sıfır Kalorili Gün**:
  Kullanıcının veri girmediği günler "0 kalori tüketti" olarak varsayılmaz. 7 günlük periyotta 2 gün kayıt varsa, ortalama kalori `toplam_kalori / 2` olarak hesaplanır; `toplam_kalori / 7` yapılmaz. `recorded_days` ve `missing_days` sayıları model koçuna açıkça iletilir.
- **Saat Dilimi Sınırları**:
  Kullanıcının IANA saat dilimine (`user.timezone`) göre yerel gece yarıları (`day_bounds`) UTC'ye çevrilerek sorgulanır. Gece 23:30 ve ertesi gün 00:30 kayıtları doğru yerel günlere ayrıştırılır.
- **Decimal Hassasiyeti**:
  Tüm besin ve kilo ortalamalarında float kayması engellenir; `ROUND_HALF_UP` ile 2 ondalık basamağa yuvarlanır.

---

## 5. Deterministik Kilo Trendi Algoritması

Kilo trendi Gemini tarafından tahmin edilmez; Python katmanında aşağıdaki muhafazakar kurallarla hesaplanır:

1. Ölçüm sayısı $< 2$ ise $\rightarrow$ `trend = 'insufficient_data'`.
2. Ölçümler aynı takvim gününe aitse (gün farkı $= 0$) $\rightarrow$ `trend = 'insufficient_data'`.
3. Gün farkı $\ge 1$ ise:
   - $\Delta kg = \text{son\_kilo} - \text{ilk\_kilo}$
   - $\text{hız} = (\Delta kg \times 7) / \text{gün\_farkı}$ (kg/hafta)
   - Eğer $\Delta kg > 0.50$ kg ve $\text{hız} > 0.15$ kg/hafta $\rightarrow$ `'increasing'`.
   - Eğer $\Delta kg < -0.50$ kg ve $\text{hız} < -0.15$ kg/hafta $\rightarrow$ `'decreasing'`.
   - Aksi durumda $\rightarrow$ `'stable'`.

---

## 6. Token ve Detay Sınırları (Context Bounds)

Veritabanı büyüdükçe prompt'un sınırsız büyümesini engellemek için yapılandırılabilir sınırlar mevcuttur:

- `NUTRICOACH_CONTEXT_MAX_TODAY_MEALS` (varsayılan: 15): Bugün listelenen maksimum öğün detay sayısı.
- `NUTRICOACH_CONTEXT_MAX_WEIGHT_LOGS` (varsayılan: 10): Listelenen maksimum kilo ölçüm geçmişi.
- `NUTRICOACH_CONTEXT_MAX_CHARS` (varsayılan: 16000): Bağlam karakter bütçesi.

**Kritik Kural**: Detay sınırları yalnızca listelenen öğeleri kırpar; `totals` (toplam kalori, protein vb.) ve agregasyonlar **her zaman tüm veritabanı kayıtları üzerinden** eksiksiz hesaplanır. Kırpılma olduğunda `detail_truncated = true` bayrağı modele bildirilir.

---

## 7. Örnek JSON Çıktısı (`coach_context`)

```json
{
  "generated_at": "2026-09-14T12:00:00Z",
  "timezone": "Europe/Istanbul",
  "local_date": "2026-09-14",
  "categories": ["today_nutrition"],
  "included_sections": ["profile", "today", "recent_messages"],
  "profile": {
    "birth_date": "1995-05-15",
    "age": 31,
    "biological_sex": "male",
    "height_cm": 180.0,
    "goal_weight_kg": 75.0,
    "preferred_weekly_weight_change_kg": -0.5,
    "activity_level": "moderate",
    "calorie_target": 2200,
    "protein_target_g": 150.0,
    "carb_target_g": 200.0,
    "fat_target_g": 70.0,
    "timezone": "Europe/Istanbul"
  },
  "today": {
    "date": "2026-09-14",
    "has_records": true,
    "meal_count": 1,
    "totals": {
      "calories": "330.00",
      "protein_g": "62.00",
      "carbs_g": "0.00",
      "fat_g": "7.00"
    },
    "remaining_by_target": {
      "calories": "1870.00",
      "protein_g": "88.00",
      "carb_target_g": null,
      "fat_target_g": null
    },
    "meals": [
      {
        "meal_type": "lunch",
        "occurred_at": "2026-09-14T12:30:00+03:00",
        "original_description": "200 gram tavuk göğsü yedim.",
        "nutrition_source": "estimate",
        "confidence": null,
        "totals": {
          "calories": "330.00",
          "protein_g": "62.00",
          "carbs_g": "0.00",
          "fat_g": "7.00"
        },
        "items": [
          {
            "name": "Tavuk göğsü",
            "quantity": "200.00",
            "unit": "gram",
            "calories": "330.00",
            "protein_g": "62.00",
            "carbs_g": "0.00",
            "fat_g": "7.00",
            "source": "estimate",
            "assumptions": null
          }
        ]
      }
    ],
    "detail_truncated": false
  },
  "yesterday": null,
  "recent_7_days": null,
  "recent_14_days": null,
  "weight": null,
  "recent_messages": [
    {
      "role": "user",
      "content": "Merhaba koç"
    },
    {
      "role": "assistant",
      "content": "Merhaba! Nasıl yardımcı olabilirim?"
    }
  ]
}
```

---

## 8. Aşama 5 ve Sonrasına Ertelenen Konular

Aşama 4 sınırları gereği aşağıdaki konular bilinçli olarak ertelenmiştir:
- Uzun dönemli anlamsal hafıza ve kalıcı tercihler (Aşama 5'te ele alınacaktır).
- Vektör veritabanı, embedding ve RAG.
- Sohbet özetlerinin veritabanında kalıcılaştırılması.
- Web UI, mobil uygulama ve kullanıcı kimlik doğrulama/oturum yönetimi (Auth).
- Bulut dağıtımı (Cloud Run / PostgreSQL).
