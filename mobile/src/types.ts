// ─────────────────────────────────────────────────────────────
// Temel veri modelleri
// ─────────────────────────────────────────────────────────────

// Desteklenen varlık türleri. Kripto fiyatları canlı (CoinGecko/Binance),
// diğerleri şimdilik manuel güncel fiyatla çalışır.
export type AssetType = 'crypto' | 'stock' | 'gold' | 'fx' | 'fund' | 'cash';

// Portföyün gösterileceği para birimi (üstteki TL/USD geçişi).
export type Currency = 'TRY' | 'USD';

// Kullanıcının yatırım yaparken kullandığı para birimi.
// Stablecoin'ler (USDT/USDC) dolar kabul edilir.
export type BuyCurrency = 'TRY' | 'USD' | 'USDT' | 'USDC';

// Bir BuyCurrency dolar cinsinden mi? (TRY hariç hepsi dolar)
export function isUsdLike(c: BuyCurrency): boolean {
  return c !== 'TRY';
}

// Kullanıcının portföyündeki tek bir pozisyon.
export interface Holding {
  id: string;
  type: AssetType;
  symbol: string; // örn. BTC, THYAO, GRAM ALTIN
  name: string; // görünen ad
  quantity: number; // adet / lot / gram
  buyPrice: number; // buyCurrency cinsinden birim alış fiyatı
  buyCurrency: BuyCurrency; // hangi parayla alındı
  // Alış anındaki USD/TRY kuru. TL↔USD çapraz çevirisi için saklanır;
  // böylece "TL bazında %X, USD bazında %Y" farkı doğru çıkar.
  buyUsdTry?: number;
  buyDate: string; // ISO tarih (reel getiri için)
  // Kripto dışı varlıklarda kullanıcının girdiği güncel birim fiyat
  // (buyCurrency cinsinden). Kriptoda yok sayılır; fiyat canlı gelir.
  manualPrice?: number;
  // Kripto ise CoinGecko id'si (örn. "bitcoin").
  coingeckoId?: string;
}

// Uygulama ayarları.
export interface Settings {
  // Reel (enflasyona göre düzeltilmiş) getiri için yıllık enflasyon (%).
  annualInflation: number;
  // Varsayılan görüntü para birimi.
  displayCurrency: Currency;
}

// Bir kriptonun hem TL hem USD güncel fiyatı.
export interface PricePair {
  try: number;
  usd: number;
}

// Bir pozisyonun seçilen para biriminde hesaplanmış hali.
export interface HoldingValue {
  holding: Holding;
  currency: Currency; // bu değerler hangi para biriminde
  currentPrice: number; // seçilen para biriminde birim güncel fiyat
  cost: number; // toplam maliyet
  value: number; // toplam güncel değer
  pnl: number; // nominal kâr/zarar
  pnlPct: number; // nominal kâr/zarar %
  priceIsLive: boolean; // fiyat canlı mı yoksa manuel mi
}

export interface PortfolioSummary {
  currency: Currency;
  totalValue: number;
  totalCost: number;
  totalPnl: number;
  totalPnlPct: number;
  // Reel K/Z her zaman TL bazında (enflasyon TL kavramı) hesaplanır.
  totalRealPnlTRY: number;
  totalRealPnlPctTRY: number;
  items: HoldingValue[];
}

// ─────────────────────────────────────────────────────────────
// Futures (USDT-M vadeli / perpetual) pozisyonları
// ─────────────────────────────────────────────────────────────

export type FuturesSide = 'long' | 'short';

export interface FuturesPosition {
  id: string;
  symbol: string; // BTC (fiyat için USDT paritesi kullanılır → BTCUSDT.P)
  name: string;
  coingeckoId: string; // canlı fiyat için
  side: FuturesSide;
  entryPrice: number; // USDT — giriş fiyatı
  leverage: number; // kaldıraç (x)
  margin: number; // USDT — ayrılan teminat
  openDate: string;
}

export interface FuturesValue {
  position: FuturesPosition;
  markPrice: number; // USDT güncel fiyat
  notional: number; // pozisyon büyüklüğü (margin × kaldıraç)
  quantity: number; // coin adedi (notional / giriş)
  pnl: number; // USDT kâr/zarar
  roiPct: number; // teminata göre getiri % (kaldıraçlı)
  liqPrice: number; // tahmini likidasyon fiyatı
  priceIsLive: boolean;
}

export interface FuturesSummary {
  totalMargin: number; // toplam teminat (USDT)
  totalPnl: number; // toplam K/Z (USDT)
  totalRoiPct: number; // teminata göre toplam %
  items: FuturesValue[];
}
