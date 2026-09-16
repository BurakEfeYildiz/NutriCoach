# Product V2 · Sprint 3 adaptif koçluk

## Hesaplama sözleşmesi

Yiyecek, kilo ve aktivite kayıtları Python/SQL içinde işlenir. Gemini yalnızca `CoachContext` içindeki kısa, yapılandırılmış olguları açıklar. Boş kayıt günü `0 kcal` sayılmaz; `average_over_usable_days` yalnızca `likely_complete` günlerle hesaplanır. Bugünkü toplam ise kısmi kayıt olsa bile kaydedilmiş öğünlerin gerçek toplamını gösterir.

Gün kalitesi gözlenebilir bir sezgiye dayanır: üç farklı ana öğün veya en az dört saate yayılmış iki farklı ana öğün `likely_complete`; diğer kayıtlı günler `partial`; kayıtsız günler `none`. Bunlar kullanıcının bütün yiyecekleri kaydettiğinin kesin kanıtı değildir. Gün ve pencere sınırları profil timezone'una göre oluşturulur.

Kalori hedef aralığı hedefin %90–110'u; protein başarı eşiği en az %90; karbonhidrat ve yağ aralığı %80–120'dir. Çok düşük kalori tüketimi başarı/rozet üretmez. Aktivitede kayıtsız adım günü sıfır sayılmaz. Egzersiz kalorisi öğün için doğrudan kredi değildir.

## Kilo eğilimi ve güven

Ham `weight_logs` aynen saklanır. Yerel gün başına en son ölçümle EWMA eğilimi hesaplanır. Yarı ömür 7 gündür; iki ölçüm arasındaki gün farkı ağırlığı değiştirir: `alpha = 1 - 0.5^(gün_aralığı/7)`. Ölçüm olmayan gün sahte ölçüm üretmez. Eğilim iki ondalığa yuvarlanır. 7 ve 14 gün öncesi referansı, kesim gününden en fazla 7 gün önce gerçek ölçüm varsa verilir. Haftalık değişim ölçümler arası süreye normalize edilir; yüzde, referans eğilim kilosuna bölünür.

Güven için en az üç ayrı ölçüm günü, 14 gün kapsama, son 7 günde ölçüm ve haftalık değişim gerekir. Beş ölçüm `medium`, sekiz ölçüm ve 28 gün `high`; daha az ama yeterli veri `low`; diğerleri `insufficient`. Planlanan hızın `% vücut ağırlığı/hafta` sözleşmesi ile karşılaştırılır. Trend ETA yalnızca yeterli, hedef yönünde ve makul hızda oluşur; tek tarih yerine aralık verilir.

## Adaptif harcama

İlk planın `estimated_expenditure_kcal` değeri varsayılan kaynaktır. Adaptif kaynak için en az 28 gün, aralıkta en az 6 ölçüm, en az 21 örtüşen `likely_complete` gün ve günlük kapsama en az %75 gerekir. Ortalama güvenilir alım 1000–4500 kcal/gün ve gözlenen hız en çok %1.25/hafta olmalıdır. Ağırlık değişimi için 7000 kcal/kg yalnızca yaklaşık enerji katsayısıdır, fizyolojik eşitlik değildir. Ham sonuç 1200–4500 kcal/gün ve ilk tahmine ±300 ile sınırlanır; ilk tahminle %50 karıştırılır. Böylece bir hesapta oynama ±150 kcal/gün olur. Plan kalori hedefi değiştirilmez.

Haftalık hedef değerlendirmesi yeterli veri varsa en fazla ±100 kcal/gün *öneri* üretir. Öneri otomatik uygulanmaz; onay/uygulama endpoint'i bu sprintte yoktur. Desteklenmeyen küçük yaş/gebelik-emzirme ve hedefe ulaşma durumlarında öneri üretilmez.

## Arayüz ve API

`/today`: en çok üç günlük içgörü, bugünkü kayıt durumu ve 14 günlük tutarlılık. `/progress`: ham kilo/eğilim, tahmin kaynağı ve güven, haftalık kullanılabilir gün sayısı, egzersiz ve hedef önerisi. Koç bağlantısı haftalık değerlendirme sorusunu taslak olarak doldurur; kullanıcı göndermeden Gemini çağrılmaz. `/recipes`: öneriler, porsiyon başına makrolar, malzemeler, hazırlama adımları ve beslenme dışı tutulan yiyecekler.

Yetkili API:

- `GET /api/v1/me/adaptive-dashboard`
- `GET /api/v1/me/weight-trend`
- `GET /api/v1/me/expenditure-estimate`
- `GET /api/v1/me/daily-insights`
- `GET /api/v1/me/weekly-review`
- `GET /api/v1/me/consistency`
- `GET /api/v1/me/recipes/recommended?meal_type=...`
- `GET /api/v1/me/recipes/{recipe_id}`
- `POST /api/v1/me/recipes`
- `GET /api/v1/me/dietary-exclusions`
- `PUT /api/v1/me/dietary-exclusions`

Yazma çağrıları mevcut CSRF korumasını kullanır. Kullanıcıya özel tarifler ve yiyecekler sahiplik sorgularıyla sınırlandırılır.

Tariflerin toplamı Food Engine ingredient preview değerlerinden porsiyon sayısına bölünür. Çözümlenmeyen malzemede `nutrition_status=partial`, `per_serving=null`; modelin yazdığı besin değeri doğrulanmış gibi gösterilmez. Mevcut USDA kayıtlarından iki örnek tarif `scripts/seed_recipes.py` ile idempotent eklenir. Kullanıcının açık `dietary_exclusions` alanı ve mevcut `food_dislike` bellekleri filtreye girer. Mevcut kısa başarılar kayıt tutarlılığını, düzenli ölçümü, protein tutarlılığını ve aktiviteyi temsil eder; XP ve kısıtlama yarışları yoktur.

## Migration ve geliştirme

`0008_adaptive_recipes` migration'ı `user_profiles.dietary_exclusions` sütununu ve tarif/ingredient tablolarını ekler. Eski kayıtlar doldurulmaz; türetilmiş analitik tabloları yoktur. `python -m app.db.migrate` mevcut SQLite dosyasına Alembic upgrade uygular ve dosyayı silmez. `alembic check` metadata uyumunu doğrular. Yeni veritabanında `python scripts/seed_recipes.py` ancak gerekli yapılandırılmış Food kayıtları varsa tarif ekler.

Manuel deneme: sunucuyu başlat, `/today` ve `/progress` ekranlarını aç, aynı gün iki ana öğün ve birkaç kilo ölçümü kaydet, kullanılabilir gün/güven etiketlerinin değiştiğini gözle. `/recipes` ekranında `süt` tercihini kaydet ve yoğurtlu önerilerin kaybolduğunu kontrol et. Koçta “Bu haftam nasıldı?” diye sor; sayısal ifadeler deterministik haftalık bağlamdan gelmelidir. Gerçek adaptif harcama için 28 günlük kapsama gerektiğinden günlük yeni kullanımda ilk plan tahmini gösterilir.

Sprint 4 için not: görsel yeniden tasarım, bildirim, tarif görselleri ve öneri onay akışı bu sprint kapsamında değildir. `partial` ve güven etiketleri yeni tasarımda görünür kalmalıdır.
