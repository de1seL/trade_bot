# CRM Taslak — Müşteri Yönetimi

Ortak veritabanlı, giriş ekranlı CRM taslağı. Tüm çalışanlar aynı müşteri
listesini görür; ekleme, düzenleme ve notlar herkese anında yansır.

## Kurulum ve çalıştırma

```bash
pip install fastapi uvicorn
python server.py
```

Ardından tarayıcıda **http://localhost:8000** adresini açın.
Aynı ofis ağındaki arkadaşlarınız **http://<sizin-ip-adresiniz>:8000**
adresiyle bağlanabilir (IP adresinizi Windows'ta `ipconfig`,
Mac/Linux'ta `ip addr` ile öğrenebilirsiniz).

**Demo kullanıcılar:** `deniz`, `selin`, `emre` — şifre hepsi için `1234`.
Yeni kullanıcı eklemek için `server.py` içindeki `SEED_USERS` listesine
ekleyip `crm.db` dosyasını silerek sunucuyu yeniden başlatın.

Veriler bu klasördeki `crm.db` (SQLite) dosyasında saklanır — yedeklemek
için bu tek dosyayı kopyalamanız yeterlidir.

## Özellikler

- **Giriş ekranı**: Her çalışan kendi hesabıyla girer; açılışta liste otomatik
  olarak kendi müşterilerine filtrelenir (filtreyi silip herkesi görebilir).
- **Ortak veri**: Müşteriler SQLite veritabanında tutulur; bir kişinin
  eklediği/düzenlediği kayıt herkeste görünür.
- **Müşteri düzenleme**: "Düzenle" ile tüm bilgiler (durum dahil) güncellenir.
- **Görüşme notları**: Her müşterinin altında tarihli, yazarı belli not
  geçmişi ("Deniz — 2026-07-20 10:02 · Telefonla görüşüldü...").
- **Sonraki temas tarihi**: Tarihi geçen temaslar listede kırmızı ⚠ ile
  görünür — kimin aranması gerektiği bir bakışta belli olur.
- **Sorumlu çalışan filtresi**: "Sorumlu Çalışan" kutusuna isim yazınca
  (örn. `deniz`) o kişinin müşterileri listelenir.
- **Durum filtresi**: "Durum" menüsünden ya da üstteki **Aktif** /
  **Potansiyel** kartlarına tıklayarak (ikinci tıklama filtreyi kaldırır).
  Çalışan + durum birlikte çalışır: "deniz" + Aktif → Deniz'in aktif müşterileri.
- **Sıralama**: "Müşteri Adı" veya "Kayıt Tarihi" başlığına tıklayarak
  artan/azalan (Türkçe alfabeye uygun).
- **Tarih aralığı filtresi** ve **isim/şirket arama**.
- **Excel'e aktarma (.xlsx)**: Tabloda o an görünen (tüm filtrelere uyan)
  kayıtları indirir; dosya adı seçilen tarih aralığını içerir. Çıktıda mavi
  dolgulu kalın başlıklar, içeriğe göre sütun genişlikleri, Sorumlu ve
  Sonraki Temas sütunları ile duruma göre önerilen **Aksiyonlar** sütunu
  bulunur. Harici kütüphane kullanılmaz; dosya tarayıcıda üretilir.

## Teknik not

- Sunucu: FastAPI + SQLite (`server.py`, tek dosya). Arayüz: `index.html`
  (tek dosya, kütüphanesiz).
- Bu bir taslaktır: şifreler basit SHA-256 ile saklanır, oturumlar sunucu
  yeniden başlayınca düşer (tekrar giriş yeterli). Gerçek kullanımda HTTPS,
  güçlü parola politikası ve düzenli yedekleme eklenmelidir.
