// ─────────────────────────────────────────────────────────────
// Temel veri modelleri
// ─────────────────────────────────────────────────────────────

// Desteklenen varlık türleri. Kripto fiyatları canlı (CoinGecko),
// diğerleri şimdilik manuel güncel fiyatla çalışır.
export type AssetType = 'crypto' | 'stock' | 'gold' | 'fx' | 'fund' | 'cash';

// Kullanıcının portföyündeki tek bir pozisyon.
export interface Holding {
  id: string;
  type: AssetType;
  symbol: string; // örn. BTC, THYAO, GRAM ALTIN, USD
  name: string; // görünen ad
  quantity: number; // adet / lot / gram
  buyPrice: number; // TL cinsinden birim alış fiyatı
  buyDate: string; // ISO tarih (reel getiri için)
  // Kripto dışı varlıklarda kullanıcının girdiği güncel birim fiyat (TL).
  // Kriptoda bu alan yok sayılır; fiyat CoinGecko'dan gelir.
  manualPrice?: number;
  // Kripto ise CoinGecko id'si (örn. "bitcoin").
  coingeckoId?: string;
}

// Uygulama ayarları.
export interface Settings {
  // Reel (enflasyona göre düzeltilmiş) getiri hesabı için yıllık enflasyon (%).
  // Kullanıcı güncelleyebilir; TÜİK/beklenti neyse onu girer.
  annualInflation: number;
}

// Bir pozisyonun canlı fiyatla hesaplanmış hali.
export interface HoldingValue {
  holding: Holding;
  currentPrice: number; // TL birim güncel fiyat
  cost: number; // toplam maliyet (quantity * buyPrice)
  value: number; // toplam güncel değer (quantity * currentPrice)
  pnl: number; // nominal kâr/zarar (value - cost)
  pnlPct: number; // nominal kâr/zarar %
  realPnl: number; // enflasyona göre düzeltilmiş kâr/zarar (TL, bugünkü lira)
  realPnlPct: number; // reel kâr/zarar %
  priceIsLive: boolean; // fiyat canlı mı yoksa manuel mi
}

export interface PortfolioSummary {
  totalValue: number;
  totalCost: number;
  totalPnl: number;
  totalPnlPct: number;
  totalRealPnl: number;
  totalRealPnlPct: number;
  items: HoldingValue[];
}
