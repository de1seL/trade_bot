import { Holding, HoldingValue, PortfolioSummary, Settings } from '../types';

// Bir pozisyonun alış tarihinden bugüne geçen yıl sayısı.
function yearsSince(iso: string): number {
  const then = new Date(iso).getTime();
  const now = Date.now();
  if (isNaN(then) || now <= then) return 0;
  return (now - then) / (365.25 * 24 * 60 * 60 * 1000);
}

// Tek bir pozisyonu güncel fiyatla değerle.
// priceMap: holding.id -> güncel birim fiyat (TL). Yoksa manuel/alış fiyatına düşer.
export function valueHolding(
  holding: Holding,
  priceMap: Record<string, number>,
  settings: Settings
): HoldingValue {
  const live = priceMap[holding.id];
  const priceIsLive = typeof live === 'number' && isFinite(live) && live > 0;
  const currentPrice = priceIsLive
    ? live
    : holding.manualPrice && holding.manualPrice > 0
    ? holding.manualPrice
    : holding.buyPrice;

  const cost = holding.quantity * holding.buyPrice;
  const value = holding.quantity * currentPrice;
  const pnl = value - cost;
  const pnlPct = cost > 0 ? (pnl / cost) * 100 : 0;

  // Reel getiri: maliyeti enflasyonla bugüne taşı, güncel değerle karşılaştır.
  // "Paran sadece enflasyon kadar artsaydı ne olurdu?" sorusunun cevabı.
  const years = yearsSince(holding.buyDate);
  const inflFactor = Math.pow(1 + settings.annualInflation / 100, years);
  const inflationAdjustedCost = cost * inflFactor;
  const realPnl = value - inflationAdjustedCost;
  const realPnlPct =
    inflationAdjustedCost > 0 ? (realPnl / inflationAdjustedCost) * 100 : 0;

  return {
    holding,
    currentPrice,
    cost,
    value,
    pnl,
    pnlPct,
    realPnl,
    realPnlPct,
    priceIsLive,
  };
}

// Tüm portföyü özetle.
export function buildSummary(
  holdings: Holding[],
  priceMap: Record<string, number>,
  settings: Settings
): PortfolioSummary {
  const items = holdings.map((h) => valueHolding(h, priceMap, settings));

  const totalValue = items.reduce((s, i) => s + i.value, 0);
  const totalCost = items.reduce((s, i) => s + i.cost, 0);
  const totalPnl = totalValue - totalCost;
  const totalPnlPct = totalCost > 0 ? (totalPnl / totalCost) * 100 : 0;

  // Reel toplam: her pozisyonun enflasyona göre düzeltilmiş maliyeti = value - realPnl.
  // Bunları toplayıp güncel değerle karşılaştırınca enflasyon-üstü getiri çıkar.
  const totalAdjustedCost = items.reduce((s, i) => s + (i.value - i.realPnl), 0);
  const totalRealPnl = totalValue - totalAdjustedCost;
  const totalRealPnlPct =
    totalAdjustedCost > 0 ? (totalRealPnl / totalAdjustedCost) * 100 : 0;

  return {
    totalValue,
    totalCost,
    totalPnl,
    totalPnlPct,
    totalRealPnl,
    totalRealPnlPct,
    items,
  };
}

// Varlık türüne göre dağılım (yüzde) — dağılım çubuğu için.
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
