# Portföyüm 📱

Yatırımlarını tek ekranda takip eden mobil uygulama (Expo / React Native).
Bu, yatırım uygulaması fikrinin **1. aşaması**: portföy takip & analiz aracı.
(2. aşama — eğitim/simülasyon modülü — sonra eklenecek.)

## Özellikler (MVP)

- **Varlık ekleme** — kripto, hisse, altın, döviz, fon, nakit
- **Canlı kripto fiyatları** — CoinGecko üzerinden, TL cinsinden, API anahtarı gerektirmez
- **Kripto dışı varlıklar** — güncel fiyatı elle girilerek takip edilir
- **Nominal kâr/zarar** — TL ve yüzde
- **Reel getiri** — enflasyona göre düzeltilmiş; "enflasyonu yendim mi?" sorusunun cevabı (yıllık enflasyon ayarlardan değiştirilebilir)
- **Dağılım görünümü** — portföyün türlere göre yüzdesel dağılımı
- **Yerel kayıt** — veriler telefonda saklanır, hesap/giriş gerektirmez

## Çalıştırma

```bash
cd mobile
npm install
npm start
```

Ardından telefonuna **Expo Go** uygulamasını kurup terminaldeki QR kodu okut.
Uygulama telefonunda canlı açılır (App Store'a gerek yok).

- Android: `npm run android`
- iOS (Mac gerekir): `npm run ios`
- Tarayıcı: `npm run web`

## Mimari

```
mobile/
  App.tsx                 durum yönetimi + navigasyon (modallar)
  src/
    types.ts              veri modelleri (Holding, Settings, ...)
    theme.ts              renkler, boşluklar
    storage.ts            AsyncStorage (yerel kayıt)
    prices/
      index.ts            fiyat servisi (CoinGecko + manuel)
      coins.ts            desteklenen coin listesi
    utils/
      format.ts           TL / yüzde biçimleme
      portfolio.ts        kâr-zarar ve reel getiri hesabı
    components/           SummaryCard, AllocationBar, HoldingCard
    screens/              PortfolioScreen, AddHoldingScreen, SettingsModal
```

## Sıradaki adımlar (yol haritası)

- [ ] Altın / USD-TRY / EUR-TRY için canlı fiyat sağlayıcısı
- [ ] BIST hisseleri için fiyat kaynağı
- [ ] Zaman içindeki portföy değeri grafiği
- [ ] Varlık düzenleme (şu an ekle/sil var)
- [ ] 2. aşama: eğitim & simülasyon modülü
