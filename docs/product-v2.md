# NutriCoach Product V2

## Sprint 2 — Food Data Engine ve Aktivite Temeli

Sprint 2, öğün tahminlerinin yanına kaynağı izlenebilir canonical `Food` kataloğunu ekler. `FoodAlias` Türkçe arama adlarını, `FoodPortion` yalnızca açık gram/ml/servis karşılıklarını, `FavoriteFood` kullanıcı tercihlerini tutar. `MealItem` katalog kimliğine bağlanabilir; bunun yanında kaynak kimliği, porsiyon etiketi ve hesaplanmış toplam makroları snapshot olarak saklanır. Katalog daha sonra güncellense bile geçmiş öğün değişmez.

Besin temeli `per_100g`, `per_100ml` veya `per_serving` olarak zorunludur. Gram ve ml arasında yoğunluk kaydı olmadan dönüşüm yapılmaz. Kalori, protein, karbonhidrat ve yağ yapılandırılmış kayıt için zorunludur. Lif, şeker ve sodyum nullable kalır; bulunmayan değer sıfıra çevrilmez. Tüm nicelikler mevcut `Amount` tipiyle SQLite'ta tam sayı yüzde birlik, PostgreSQL'de `NUMERIC(12,2)` olarak tutulur.

USDA FoodData Central genel yiyeceklerin birincil kaynağıdır. `scripts/import_usda_foods.py` sorgu, FDC id ve Türkçe common-food modlarını destekler; `(source, source_food_id)` ile tekrar çalıştırılabilir upsert yapar. Çalıştırma için `USDA_FDC_API_KEY` gerekir. Küçük yerel smoke denemesinde `--demo-key` kullanılabilir fakat ortak kota düşüktür. USDA verileri kamu malıdır/CC0 koşullarıyla sunulur; [resmî API rehberi](https://fdc.nal.usda.gov/api-guide/) ve [indirme sayfası](https://fdc.nal.usda.gov/download-datasets/) kaynak alınır. Open Food Facts yalnızca kullanıcı paketli ürün aramasını açtığında sorgulanır; arama sonucu seçilirse v3 ürün detayı tekrar doğrulanır ve cache edilir. İstemci kimliği için `OPEN_FOOD_FACTS_USER_AGENT` değerine iletişim adresi yazılmalıdır. OFF veritabanı ODbL, tekil içerikler Database Contents License kapsamındadır; [resmî lisans açıklaması](https://openfoodfacts.github.io/openfoodfacts-server/api/tutorials/license-be-on-the-legal-side/) izlenir. Görseller ve veri dump'ları alınmaz.

```sh
# .env içine USDA_FDC_API_KEY ve iletişim içeren OPEN_FOOD_FACTS_USER_AGENT yazdıktan sonra:
PYTHONPATH=. python scripts/import_usda_foods.py --common
PYTHONPATH=. python scripts/import_usda_foods.py --query "lentils cooked" --alias mercimek
PYTHONPATH=. python scripts/import_usda_foods.py --fdc-id 171477 --alias "tavuk göğsü"
```

Sprint 2 doğrulamasında USDA'nın resmî Nisan 2026 Foundation Foods JSON paketi ile resmî SR Legacy JSON paketi kullanılarak **9 gerçek kayıt** tutuldu: **4 Foundation** ve **5 SR Legacy**. Bunlar yumurta, muz, süt, sade yoğurt, çiğ badem, çiğ patates, pişmiş beyaz pirinç, zeytinyağı ve pişmiş tavuk göğsüdür. Toplam 18 Türkçe alias eklendi. Ortak `DEMO_KEY` ile API smoke çağrısı gerçek sonuç verdi ancak paylaşılan kota `429` ürettiği için doğrulama resmî küçük indirilebilir paketlerle tamamlandı; ürün API'sinin normal kullanımı için kişisel USDA anahtarı gerekir.

Arama görünürlüğü global katalog ile oturum sahibinin private custom yiyecekleriyle sınırlıdır. Son kullanılanlar `MealItem` kayıtlarından türetilir; ayrı bir mutable recent tablosu yoktur. Favoriler kullanıcı ve yiyecek ilişkisi olarak tutulur. AI öğün eylemi önce tam canonical ad/Türkçe alias eşleşmesini dener ve uyumlu açık birim veya food-specific porsiyon varsa deterministik değeri kullanır; güvenli eşleşme yoksa mevcut `estimate` akışına döner.

`DailySteps` kullanıcı+tarih+kaynak bazında tekildir. `Workout` manuel CRUD sağlar. Bilinen aktivite türlerinde güncel WeightLog varsa enerji `MET × 3.5 × kg / 200 × dakika` ile hesaplanır ve `met_estimate` olarak etiketlenir; kilo veya MET yoksa değer null kalır. Bu enerji beslenme hedefine geri eklenmez. `CoachContext` yalnızca aktiviteyle ilgili istekte bugünün toplam adım, süre ve kompakt egzersiz listesini alır; geçmiş seri prompt'a taşınmaz.

### Sprint 2 API

| Yöntem | Uç | Amaç |
|---|---|---|
| `GET` | `/api/v1/me/foods/search` | Yerel katalog/alias ara; isteğe bağlı OFF sonuçları |
| `POST` | `/api/v1/me/foods/external-cache` | Seçilen OFF ürününü yeniden doğrula ve cache et |
| `POST` | `/api/v1/me/foods` | Private custom yiyecek oluştur |
| `GET` | `/api/v1/me/foods/recent` | Öğünlerden türetilen son yiyecekler |
| `GET` | `/api/v1/me/foods/favorites` | Favori yiyecekler |
| `PUT/DELETE` | `/api/v1/me/foods/{id}/favorite` | Favori ekle/kaldır |
| `POST` | `/api/v1/me/foods/log-preview` | Deterministik porsiyon önizlemesi |
| `POST` | `/api/v1/me/foods/log` | Snapshot MealItem ve öğün oluştur |
| `PUT/GET/DELETE` | `/api/v1/me/daily-steps` | Kaynağa göre adım upsert/liste/sil |
| `POST/GET` | `/api/v1/me/workouts` | Egzersiz oluştur/listele |
| `PUT/DELETE` | `/api/v1/me/workouts/{id}` | Egzersiz güncelle/sil |
| `GET` | `/api/v1/me/activity/today` | Kullanıcı saat diliminde bugünkü aktivite |

`0007_food_data_and_activity.py` yeni tabloları oluşturur ve mevcut `meal_items` tablosuna yalnızca nullable katalog/snapshot referansları ekler. `python -m app.db.migrate` mevcut SQLite dosyasını yerinde yükseltmeden önce SQLite backup API ile `0600` izinli ayrı kopya üretir.

Manuel doğrulama: migration sonrası `/meals` sayfasında `yumurta` veya `yoğurt` ara, sonucu seçip miktarı değiştirerek preview değerinin orantılı değiştiğini kontrol et. `Ekstra` kategorisiyle kaydet ve günlük toplamı kontrol et. Private yiyecek oluşturup başka hesapta görünmediğini doğrula. Paketli ürün aramasında dış aramayı açıp bir ürünü seç; yalnızca makroları eksiksiz ürün cache edilmelidir. `/progress` sayfasında adım ve egzersiz gir; süre ve MET tahminini gör, beslenme hedefinin değişmediğini kontrol et.

Saved Meal ve Copy Meal bu sprintte uygulanmadı. Temel Food Engine ve snapshot bütünlüğünü büyütmemek için sonraki ürün kararına bırakıldı.

Hedefli otomatik doğrulama komutu: `pytest -q tests/test_product_v2_sprint2.py tests/test_migrations.py`. Sprint 2 brief'i gereği tüm pytest ve tarayıcı/viewport/axe paketleri çalıştırılmaz.

## Sprint 1 — Kişiselleştirme ve Beslenme Hedefi

## Kapsam

Bu sprint kişiselleştirme, ilk kurulum ve deterministik beslenme hedefi üretimini ekler. Kayıt formu kısa kalır; yeni kullanıcı giriş yaptıktan sonra hedef, vücut, günlük hareket, antrenman ve hız adımlarından geçer. Hesap/güvenlik ayarları `/account`, beslenme planı `/profile` sayfasındadır.

Gemini hedef hesabı yapmaz. Python servisinin ürettiği `profile`, `plan` ve `today` alanlarını yorumlar. Öğün tahmini gibi mevcut AI görevleri korunmuştur. Tarif, aktivite takibi, adaptif hedef, oyunlaştırma ve yeni bir frontend framework'ü bu sprintin dışında tutulmuştur.

## Veri sahipliği ve migration

`0006_product_v2_sprint1.py`, `user_profiles` tablosuna nullable plan girdileri ve hesaplama snapshot alanları ekler. Eski kullanıcılar ve profiller değiştirilmez; `onboarding_completed_at` boş olduğu için kurulumları eksik kabul edilir. Migration mevcut SQLite dosyasını silmez veya yerine başka dosya koymaz. `app.db.migrate`, önce SQLite backup API ile izinleri `0600` olan bir yedek oluşturur, sonra aynı dosya üzerinde Alembic'i `0006` başına taşır.

`current_weight_kg` profil tablosunda tutulmaz. Kaynak her zaman `weight_logs` içinde `occurred_at`, `created_at`, `id` sırasıyla en yeni kayıttır. Yeni bir güncel kilo eklenince snapshot yeniden hesaplanır. Hedef geçilmişse kayıt reddedilmez; plan `goal_reached` durumunda bakım enerjisine geçer. Geçmiş tarihli bir kilo kaydı güncel planı değiştirmez.

Snapshot alanları `bmr_kcal`, `estimated_expenditure_kcal`, `expenditure_source`, kalori/makro hedefleri, planlanan hız, ETA aralığı, durum, kısıt nedeni, `calculation_version` ve `targets_recalculated_at` değerleridir. İlk sürüm `msj-v1` olarak işaretlenir.

## Deterministik hesaplama

Yetişkinler için Mifflin–St Jeor dinlenme enerji tahmini kullanılır:

```text
erkek:  10 × kilo(kg) + 6.25 × boy(cm) − 5 × yaş + 5
kadın:  10 × kilo(kg) + 6.25 × boy(cm) − 5 × yaş − 161
```

Kaynak çalışma 498 sağlıklı, 19–78 yaş arası katılımcıdan türetilmiştir: [Mifflin ve arkadaşları, PubMed](https://pubmed.ncbi.nlm.nih.gov/2305711/).

Başlangıç günlük harcama tahmini BMR × hareket katsayısıdır ve `initial_estimate` olarak etiketlenir. Katsayılar sırasıyla 1.20, 1.375, 1.55, 1.725 ve geriye uyumlu yoğun tempo için 1.90'dır. Bu değer gözleme dayalı adaptif bir tahmin değildir.

Haftalık hız vücut ağırlığının `%0,20–%0,75` aralığıyla doğrulanır; arayüz `%0,25`, `%0,50`, `%0,75` seçeneklerini sunar. Enerji karşılığı ürün politikası olarak `7.700 kcal/kg` ile hesaplanır. Alt sınır kadın için 1.200, erkek için 1.500 kcal ve her iki durumda BMR'nin `%80` değerinden yüksek olanıdır. Üst sınır tahmini harcama + 750 kcal'dir. Sınır uygulanırsa durum `constrained` olur ve neden kullanıcıya gösterilir.

Protein kilo verme/alma için `1,6 g/kg`, koruma için `1,4 g/kg` ile başlar ve enerjinin `%35` değerini aşmaz. Yağ en az `0,8 g/kg` veya enerjinin `%20` değerinden yüksek olanıyla başlar, `%35` ile sınırlandırılır. Karbonhidrat kalan enerjiden hesaplanır. Bu sınırlar NutriCoach ürün politikasıdır; yetişkin makroları için daha geniş referans aralıkları [National Academies AMDR tablosunda](https://www.nationalacademies.org/read/10872/chapter/13) yayımlanmıştır.

ETA kesin tarih değildir. Mevcut kilo farkı ve planlanan hızdan çıkan sürenin `%85–%125` aralığı gösterilir ve `planned_range` olarak etiketlenir.

## Güvenlik sınırları

13 yaş altı veya 120 yaş üstü girişler reddedilir. 13–17 yaş profili kaydedilir fakat `unsupported_minor` durumunda otomatik kalori/makro hedefi verilmez. Hamilelik veya emzirme seçildiğinde `unsupported_pregnancy_breastfeeding` durumu kullanılır ve otomatik reçete üretilmez. Bu yaklaşım, NIDDK Body Weight Planner'ın yetişkinler için olduğunu ve hamile/emziren kişiler için kullanılmaması gerektiğini belirten [resmî kapsamıyla](https://www.niddk.nih.gov/health-information/weight-management/body-weight-planner) uyumludur.

Boy 100–250 cm, kilo/hedef kilo 25–400 kg aralığında olmalıdır. Kilo verme hedefi güncel kilodan düşük, kilo alma hedefi yüksek olmalıdır. Koruma hedefi güncel kilonun 1 kg çevresinde ve hız `%0` olmalıdır. Doğum tarihi gelecekte olamaz. Bütün kurallar backend'de doğrulanır.

## API

| Yöntem | Uç | Amaç |
|---|---|---|
| `GET` | `/api/v1/me/onboarding` | Kurulum durumu, eksik alanlar ve plan |
| `PUT` | `/api/v1/me/onboarding` | Beş adımın verilerini atomik kaydet, ilk WeightLog'u ve snapshot'ı oluştur |
| `GET` | `/api/v1/me/nutrition-plan` | Güncel kilo ve sürümlü plan snapshot'ını getir |
| `PUT` | `/api/v1/me/nutrition-profile` | Plan girdilerini güncelle ve yeniden hesapla |
| `PATCH` | `/api/v1/me/account` | Ad, e-posta ve saat dilimini güncelle |

Mevcut `/api/v1/me/profile` ve geliştirme amaçlı `/api/v1/users/{id}/profile` sözleşmeleri geriye uyumluluk için korunur. Üretim arayüzü türetilmiş kalori/makroları bu eski uçlardan yazmaz. Chat `profile_update` eylemi de yalnızca plan girdilerini kabul eder; türetilmiş hedefler şemada yoktur.

`CoachContext` içinde `profile` kullanıcı girdilerini, `plan` backend snapshot'ını taşır. `today` alanı `remaining_calories`, `remaining_protein_g`, `remaining_carbohydrate_g` ve `remaining_fat_g` değerlerini doğrudan içerir. Kayıt olmayan günde `totals` ve kalan değerler `null` kalır; sıfır tüketim varsayılmaz.

## Manuel test

```sh
source .venv/bin/activate
python -m app.db.migrate
uvicorn app.main:app --reload --host 127.0.0.1
```

1. `/register` üzerinden kısa form ile yeni hesap oluştur. `/onboarding` sayfasına yönlenmelisin.
2. Beş adımı tamamla. Kilo verme için hedef kiloyu güncel kilodan düşük seç. Son adım sonrası `/today` açılmalı.
3. `/profile` sayfasında kalori, makro, harcama, hız ve ETA aralığını kontrol et. Kalori/makro alanları düzenlenebilir olmamalı.
4. Hız veya hareket seviyesini değiştirip kaydet. Plan snapshot'ı ve `targets_recalculated_at` yenilenmeli.
5. `/progress` üzerinden yeni bir güncel kilo ekle. `/profile` sayfasında güncel kilo, BMR, harcama, hedefler ve ETA yeniden hesaplanmalı.
6. `/account` sayfasında hesap bilgileri, tema ve şifrenin beslenme formundan ayrı olduğunu kontrol et.
7. Yeni bir hesapta 18 yaş altı tarih veya hamilelik/emzirme seç. Profil kaydolmalı, açıklayıcı kısıt görünmeli ve kalori/makro hedefleri boş kalmalı.

Otomatik test:

```sh
.venv/bin/pytest -q
```

İzole gerçek tarayıcı paketi `scripts/ui_v2_preview.py` ve `scripts/ui_v2_smoke.cjs` ile çalışır. Chromium ve WebKit akışı kayıt, onboarding, deterministik plan güncellemesi, öğün CRUD, kilo, chat, tema, yedi responsive genişlik ve axe WCAG A/AA kontrollerini kapsar.

## Sprint 1 doğrulama sonucu

- Pytest: **182 geçti**, hata yok.
- Chromium: **109 kontrol**, JavaScript/konsol hatası yok, axe ihlali yok.
- WebKit: **109 kontrol**, JavaScript/konsol hatası yok, axe ihlali yok.
- Kontrol edilen genişlikler: 360, 390, 430, 768, 1024, 1280, 1440 px.
- Gerçek SQLite migration: kaynak dosya korunarak `0006` uygulandı; öncesinde ayrı backup oluşturuldu; 4 kullanıcı, 4 profil ve 3 kilo kaydı migration sonrasında korundu.
