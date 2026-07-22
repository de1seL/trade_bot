import {
  Currency,
  Holding,
  HoldingValue,
  PortfolioSummary,
  PricePair,
  Settings,
  isUsdLike,
} from '../types';

// Alış tarihinden bugüne geçen yıl sayısı.
function yearsSince(iso: string): number {
  const then = new Date(iso).getTime();
  const now = Date.now();
  if (isNaN(then) || now <= then) return 0;
  return (now - then) / (365.25 * 24 * 60 * 60 * 1000);
}

// Bir pozisyonun TOPLAM alış maliyetini hedef para biriminde döndürür.
// Çapraz çeviri, alış anındaki kur (buyUsdTry) ile yapılır; yoksa güncel kura
// düşer. Alış kuru saklandığı için TL ve USD bazında farklı yüzdeler çıkar.
function costInCurrency(
  h: Holding,
  target: Currency,
  currentUsdTry: number | null
): number {
  const rate = h.buyUsdTry ?? currentUsdTry ?? 0;
  const buyIsUsd = isUsdLike(h.buyCurrency);

  let unitTRY: number;
  let unitUSD: number;
  if (buyIsUsd) {
    unitUSD = h.buyPrice;
    unitTRY = rate > 0 ? h.buyPrice * rate : h.buyPrice;
  } else {
    unitTRY = h.buyPrice;
    unitUSD = rate > 0 ? h.buyPrice / rate : h.buyPrice;
  }
  const unit = target === 'TRY' ? unitTRY : unitUSD;
  return unit * h.quantity;
}

// Bir pozisyonun güncel BİRİM fiyatını hedef para biriminde döndürür.
function currentUnitPrice(
  h: Holding,
  priceMap: Record<string, PricePair>,
  currentUsdTry: number | null,
  target: Currency
): { price: number; isLive: boolean } {
  // Canlı fiyatı olan her varlık (kripto veya hisse) onu kullanır.
  const pair = priceMap[h.id];
  if (pair) {
    return { price: target === 'TRY' ? pair.try : pair.usd, isLive: true };
  }

  // Canlı fiyatı yoksa: manuel fiyat (buyCurrency cinsinden), güncel kurla çevrilir.
  const manual =
    h.manualPrice && h.manualPrice > 0 ? h.manualPrice : h.buyPrice;
  const manualIsUsd = isUsdLike(h.buyCurrency);
  const rate = currentUsdTry ?? h.buyUsdTry ?? 0;

  let priceTRY: number;
  let priceUSD: number;
  if (manualIsUsd) {
    priceUSD = manual;
    priceTRY = rate > 0 ? manual * rate : manual;
  } else {
    priceTRY = manual;
    priceUSD = rate > 0 ? manual / rate : manual;
  }
  return {
    price: target === 'TRY' ? priceTRY : priceUSD,
    isLive: false,
  };
}

// Tek pozisyonu seçilen para biriminde değerle.
export function valueHolding(
  h: Holding,
  priceMap: Record<string, PricePair>,
  currentUsdTry: number | null,
  display: Currency
): HoldingValue {
  const cost = costInCurrency(h, display, currentUsdTry);
  const { price, isLive } = currentUnitPrice(
    h,
    priceMap,
    currentUsdTry,
    display
  );
  const value = price * h.quantity;
  const pnl = value - cost;
  const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;

  return {
    holding: h,
    currency: display,
    currentPrice: price,
    cost,
    value,
    pnl,
    pnlPct,
    priceIsLive: isLive,
  };
}

export function buildSummary(
  holdings: Holding[],
  priceMap: Record<string, PricePair>,
  currentUsdTry: number | null,
  settings: Settings,
  display: Currency
): PortfolioSummary {
  const items = holdings.map((h) =>
    valueHolding(h, priceMap, currentUsdTry, display)
  );

  const totalValue = items.reduce((s, i) => s + i.value, 0);
  const totalCost = items.reduce((s, i) => s + i.cost, 0);
  const totalPnl = totalValue - totalCost;
  const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;

  // Reel K/Z her zaman TL bazında: TL maliyeti enflasyonla bugüne taşı,
  // TL değerle karşılaştır.
  let realValueTRY = 0;
  let adjustedCostTRY = 0;
  for (const h of holdings) {
    const costTRY = costInCurrency(h, 'TRY', currentUsdTry);
    const { price } = currentUnitPrice(h, priceMap, currentUsdTry, 'TRY');
    const valueTRY = price * h.quantity;
    const years = yearsSince(h.buyDate);
    const inflFactor = Math.pow(1 + settings.annualInflation / 100, years);
    realValueTRY += valueTRY;
    adjustedCostTRY += costTRY * inflFactor;
  }
  const totalRealPnlTRY = realValueTRY - adjustedCostTRY;
  const totalRealPnlPctTRY =
    adjustedCostTRY > 0 ? (totalRealPnlTRY / adjustedCostTRY) * 100 : 0;

  return {
    currency: display,
    totalValue,
    totalCost,
    totalPnl,
    totalPnlPct,
    totalRealPnlTRY,
    totalRealPnlPctTRY,
    items,
  };
}

// Varlık türüne göre dağılım (yüzde). Oranlar para biriminden bağımsızdır.
export function allocationByType(
  items: HoldingValue[]
): { type: string; value: number; pct: number }[] {
  const total = items.reduce((s, i) => s + i.value, 0);
  const map: Record<string, number> = {};
  for (const i of items) {
    map[i.holding.type] = (map[i.holding.type] || 0) + i.value;
  }
  return Object.entries(map)
    .map(([type, value]) => ({
      type,
      value,
      pct: total > 0 ? (value / total) * 100 : 0,
    }))
    .sort((a, b) => b.value - a.value);
}
