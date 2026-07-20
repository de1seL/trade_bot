# CRM Taslak — Müşteri Yönetimi

Tek dosyalık, kurulum gerektirmeyen bir CRM taslağı. `index.html` dosyasını
herhangi bir tarayıcıda açmanız yeterlidir (sunucu gerekmez).

## Özellikler

- **Müşteri listesi**: ad, şirket, e-posta, telefon, durum (Aktif / Potansiyel / Pasif) ve kayıt tarihi.
- **Sıralama**: "Müşteri Adı" veya "Kayıt Tarihi" sütun başlığına tıklayarak artan/azalan sıralama (Türkçe alfabeye uygun).
- **Tarih aralığı filtresi**: Başlangıç ve bitiş tarihi seçerek listeyi daraltma.
- **İsim/şirket arama**.
- **Excel'e aktarma (.xlsx)**: "Excel'e Aktar" düğmesi, tabloda o an görünen
  (yani seçilen tarih aralığı + arama filtresine uyan) kayıtları gerçek bir
  `.xlsx` dosyası olarak indirir. Dosya adı seçilen aralığı içerir,
  örn. `musteriler_2026-03-01_2026-05-31.xlsx`.
- **Müşteri ekleme/silme**: Veriler tarayıcının `localStorage`'ında saklanır;
  sayfa yenilense de kaybolmaz.

## Kullanım: belirli tarih aralığını Excel'e aktarma

1. Üstteki **Başlangıç Tarihi** ve **Bitiş Tarihi** alanlarından aralığı seçin.
2. Tabloda yalnızca o aralıktaki müşteriler görünür.
3. **⬇ Excel'e Aktar (.xlsx)** düğmesine tıklayın — dosya indirilir ve Excel'de doğrudan açılır.

## Teknik not

Harici hiçbir kütüphane/CDN kullanılmaz; `.xlsx` dosyası tarayıcıda
JavaScript ile (sıkıştırmasız ZIP + SpreadsheetML) üretilir. Bu bir taslaktır:
gerçek kullanımda veriler bir veritabanına taşınmalı ve kullanıcı girişi eklenmelidir.
