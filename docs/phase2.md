# Aşama 2: beslenme veritabanı

## Migration ve mevcut kayıtları koruma

1. Çalışan uygulamayı durdur; migration sırasında başka süreç yazmasın.
2. Sanal ortamda `python -m pip install -r requirements-lock.txt` çalıştır.
3. Mevcut `.env` dosyasını koru. `NUTRICOACH_DATABASE_URL` eski SQLite dosyanı göstermeli; aynı proje klasöründen çalış.
4. `python -m app.db.migrate` çalıştır.
5. `alembic current` çıktısı `0002 (head)` olmalı. `alembic check` şema farkı olmadığını doğrular.
6. `uvicorn app.main:app --reload --host 127.0.0.1` ile başlat.

Komut mevcut SQLite dosyası için SQLite backup API ile `nutricoach.db.backup-<benzersiz-id>` yedeği üretir. Yedek izinleri yalnızca dosya sahibine açıktır; Git dışında tutulur. Kaynak dosya silinmez veya yeniden adlandırılmaz. Yedekler kişisel veri içerir; DB gibi korunmalıdır.

- **0001:** Boş DB'de dondurulmuş Aşama 1 şemasını oluşturur. Mevcut users/user_profiles tablolarında sütun, tip, nullability, foreign key, unique, primary key ve CHECK uyumunu kontrol eder; eşleşirse tablo ve satırları değiştirmeden revision kaydeder. Bilinmeyen/kısmi şemada durur.
- **0002:** meals, meal_items, weight_logs tablolarını, sahiplik kısıtlarını ve indeksleri ekler. Eski tablo/verilere dokunmaz.
- Komutu tekrar çalıştırmak veri çoğaltmaz. Her çalıştırmada mevcut dosya için yeni bir yedek alınır.
- Sunucu artık `create_all` çağırmaz. Eksik/eski revision ile açılmayı reddedip migration komutunu gösterir.

Doğrudan `alembic upgrade head` aynı revision'ları uygular ama otomatik yedek almaz; normal kullanımda sarmalayıcı komutu tercih et. `stamp head` geçiş yerine kullanılamaz. `alembic downgrade 0001`, Aşama 2 tablolarını **ve içlerindeki verileri siler**; normal geri alma yöntemi değildir. Geri dönüşte sunucuyu durdurup önce mevcut DB'yi ayrıca koru, uygun yedeği geri yükle ve o şemayla uyumlu kod sürümünü kullan. Başarısız/yarım migration için yedeği koruyarak hata nedenini incele; otomatik dosya silme veya sıfırlama yapılmaz.

## Endpointler

Aşağıdaki yolların başına `/api/v1/users/{user_id}` gelir. Kimlikler UUID'dir.

| Yöntem | Yol | İşlev |
|---|---|---|
| POST | `/meals` | Öğünü item'larla tek transaction içinde kaydet |
| GET | `/meals?day=2026-09-14&limit=100&offset=0` | İsteğe bağlı yerel gün filtresiyle listele |
| GET | `/meals/today` | Kullanıcının yerel bugünkü öğünleri |
| GET | `/meals/{meal_id}` | Item'lar ve hesaplanan toplamlarla getir |
| PUT | `/meals/{meal_id}` | Öğünü ve tüm item listesini değiştir |
| DELETE | `/meals/{meal_id}` | Öğünü ve bağlı item'ları sil; 204 |
| GET | `/nutrition/daily?day=2026-09-14` | Günlük toplamlar; gün yoksa yerel bugün |
| GET | `/nutrition/weekly?end_day=2026-09-14` | Bitiş günü dahil son 7 yerel gün |
| POST | `/weight-logs` | Kilo kaydet |
| GET | `/weight-logs?limit=100&offset=0` | Ölçüm zamanına göre azalan kilo geçmişi |
| GET | `/weight-logs/current` | Son ölçüm; hiç kayıt yoksa 200/null |
| GET | `/weight-logs/{weight_id}` | Kilo kaydını getir |
| PUT | `/weight-logs/{weight_id}` | Kilo ve ölçüm zamanını değiştir |
| DELETE | `/weight-logs/{weight_id}` | Kilo kaydını sil; 204 |

Listeler varsayılan 100, en fazla 500 kayıt döndürür; `offset` ile devam edilir. Günlük/haftalık hesaplar sayfalama sınırından etkilenmez. Item düzenleme, öğünün PUT uç noktasına güncellenmiş tam item listesi gönderilerek yapılır; bağımsız item uçları yoktur. PUT sonrası item kimlikleri yenilenir. Gönderilmeyen isteğe bağlı alanlar varsayılanlarına döner. `expected_version` son okunan öğün sürümüdür; eskiyse 409. Sahibi yanlış veya kayıt yoksa 404; doğrulama hatasında 422.

## Veri sözleşmesi

**Ondalıklar:** Besin değerleri, quantity ve kilo en fazla iki ondalık kabul eder; fazlası sessizce yuvarlanmaz, 422 döner. JSON'da bu değerleri string (`"97.80"`) göndermek istemci kayan nokta dönüşümünü önler; yanıtta Decimal alanları string'dir. SQLite'ta `100.10 kcal` ham olarak `10010` tamsayısıdır, ORM geri okurken Decimal'e çevirir. PostgreSQL için aynı tip `NUMERIC(12,2)` olur. SQLite'ta ham SQL yazarken bu ölçeği dikkate almak gerekir; uygulama işlemleri ORM üzerinden yapılmalıdır. Negatif besin/kilo ve SQLite'ta kesirli ham depolama DB CHECK ile de engellenir.

Öğün toplamı DB'de ikinci kez tutulmaz: item değerleri Python Decimal ile toplanır. Haftalık ortalama gösteriminde iki ondalığa ROUND_HALF_UP uygulanır. Item kalorisi ve makroları **girilen porsiyonun tamamına aittir**; quantity ile tekrar çarpılmaz ve 100 gram başına değer değildir. Kalori, makrolardan yeniden türetilmez. Eski Aşama 1 profil sütunları veri korumak için değiştirilmedi; hedef hesabında gerektiğinde `Decimal(str(target))` kullanılır.

**Zamanlar:** `occurred_at` offset içermelidir (`Z` veya `+03:00` gibi). Offset'siz giriş reddedilir. UTC saklanır ve UTC döner; günler kullanıcının IANA timezone'una göre `[yerel 00:00, sonraki gün 00:00)` aralığıyla seçilir. Örneğin İstanbul 14 Eylül 2026, UTC'de 13 Eylül 21:00 dahil — 14 Eylül 21:00 hariç aralığıdır. Gün sınırları DST olan bölgelerde de ayrı hesaplanır.

**Eksik kayıtlar:** Kayıt yoksa `has_records=false`, `totals=null`; açıkça 0 kcal içeren öğün varsa kayıtlı 0'dır. Haftalık sonuç `recorded_days`, `missing_days` ve yalnızca kayıtlı günler üzerinden `average_over_recorded_days` döndürür. Kayıtlı gün de tüm tüketimin kaydedildiği anlamına gelmez; sonuçlar kaydedilmiş tüketimi özetler. Haftalık pencere bugün dahil 7 takvim günüdür; bugün tamamlanmamış olabilir. Hedef üstü/altı günler yalnızca kayıtlı günlerde **mevcut** kalori hedefine göre sayılır; hedef geçmişi henüz yoktur. Hedef eksikse ilgili kalan değer null'dır; aşım varsa negatif kalır. Kayıtsız günde kalan hedef de null'dır.

**Kilo:** Güncel kilo insertion sırasına değil, en son `occurred_at` değerine göre belirlenir. Aynı ölçüm zamanında created_at, sonra id azalan sıralaması belirleyicidir. Geriye dönük kayıt en güncel ölçümü geçersiz kılmaz. Düzenleme/silme sonrası güncel kilo tekrar hesaplanır; profile kopyalanmaz. Gelecek tarihli kayıt girilirse ölçüm sırasının en yenisi olarak değerlendirilir.

**Kullanıcı kapsamı:** Her veri sorgusunda user_id bulunur. Item→Meal bileşik foreign key `(user_id, meal_id) → (user_id, id)`, başka kullanıcının öğününe item bağlanmasını DB düzeyinde engeller. user_id istek gövdesinden kabul edilmez. Bununla birlikte henüz login/auth yok: URL'deki kullanıcı kimliğini değiştirebilen yerel API kullanıcısının gerçek kimliği doğrulanmaz. Bu aşamanın testleri kullanıcı kapsamını doğrular; gerçek erişim yetkilendirmesi Aşama 7'de eklenecek. Uygulamayı yerel geliştirme sınırında çalıştır.

## Manuel test

Sunucu çalışırken [Swagger](http://127.0.0.1:8000/docs) aç.

1. `POST /api/v1/users` ile `{"name":"Aşama 2 Demo","timezone":"Europe/Istanbul"}` gönder. Dönen `id` değerini tüm işlemlerde user_id olarak kullan. İstersen mevcut kullanıcının kimliğini kullan; aşağıdakiler yeni test kayıtları oluşturur.
2. `POST .../meals` ile şu JSON'u gönder:

```json
{
  "occurred_at": "2026-09-14T00:05:00+03:00",
  "meal_type": "lunch",
  "original_description": "Tavuk ve pilav",
  "items": [
    {"name":"Tavuk","quantity":"200.00","unit":"g","calories":"330.00","protein_g":"62.00","carbs_g":"0.00","fat_g":"7.20"},
    {"name":"Pilav","quantity":"150.00","unit":"g","calories":"195.00","protein_g":"4.00","carbs_g":"42.00","fat_g":"0.50"}
  ]
}
```

Bu değerler API test verisidir. Yanıtta totals.calories `"525.00"`, protein `"66.00"`, carbs `"42.00"`, fat `"7.70"` olmalı.

3. `GET .../nutrition/daily?day=2026-09-14` ile toplamı kontrol et. `GET .../meals?day=2026-09-14` öğünü içermeli; 13 Eylül listesi içermemeli.
4. `PUT .../meals/{meal_id}` için aynı JSON'a `"expected_version":1` ekle, pilavın quantity'sini `"100.00"`, kalorisini `"130.00"`, proteinini `"2.70"`, karbonhidratını `"28.00"`, yağını `"0.30"` yap. Öğün ve günlük kalori `"460.00"` olmalı; version 2 olmalı. Aynı eski version ile tekrar deneme 409 döndürmeli.
5. `GET .../nutrition/weekly?end_day=2026-09-14` ile yeni demo kullanıcıda recorded_days 1, missing_days 6, ortalama kalori `"460.00"` olduğunu gör.
6. `POST .../weight-logs` ile `{"occurred_at":"2026-09-14T08:00:00+03:00","weight_kg":"97.80"}` gönder. `/weight-logs/current` aynı kaydı döndürmeli. Sonra daha eski tarihli bir kayıt ekle; güncel kilo değişmemeli.
7. Kilo kaydını PUT ile değiştir ve DELETE ile sil. Güncel kayıt silindiğinde eski ölçüm dönmeli; tümü silinince null dönmeli.
8. İkinci demo kullanıcı oluştur. İlk kullanıcının meal_id/weight_id değerleriyle ikinci kullanıcının yollarından GET/PUT/DELETE dene: 404 olmalı.
9. Öğünü DELETE ile sil. Başka öğün yoksa günlük totals null, haftalık recorded_days 0 olmalı. Sunucuyu yeniden başlat; kalan kayıtlar korunmalı.

## Otomatik doğrulama

```sh
python -m pytest -q
python -m pip check
alembic check
```

Migration testleri eski şemayı ve örnek kullanıcı/profili oluşturur, kaynak dosyanın inode'unun değişmediğini, tüm eski satırların ve yedeğin korunduğunu doğrular. Şema bilinmiyorsa veri silmeden durma, temiz kurulum ve yeniden migration da test edilir. Beslenme testleri item güncelleme, silme/cascade, sürüm çatışması, gün değiştirme, hassas Decimal toplamları, İstanbul gece yarısı, DST, eksik günler, kullanıcı kapsamı, DB kısıtları ve kilo CRUD'yi kapsar.

Resmi teknik dayanaklar: [Alembic migration komutları](https://alembic.sqlalchemy.org/en/latest/api/commands.html), [SQLAlchemy Numeric](https://docs.sqlalchemy.org/en/20/core/type_basics.html), [özel veri tipleri](https://docs.sqlalchemy.org/en/20/core/custom_types.html).
