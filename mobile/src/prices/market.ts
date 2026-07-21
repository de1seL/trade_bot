import { COINS } from './coins';

// ─────────────────────────────────────────────────────────────
// Piyasa verisi (canlı fiyat listeleri)
//
// Binance 24s ticker'ından fiyat + 24 saatlik değişim yüzdesi alır.
// TL fiyatı USD × USDT/TRY ile hesaplanır. Anahtar gerektirmez.
// ─────────────────────────────────────────────────────────────

const T24 = 'https://api.binance.com/api/v3/ticker/24hr';
const GRAMS_PER_OUNCE = 31.1035;

export interface MarketQuote {
  key: string;
  symbol: string;
  name: string;
  priceTry: number;
  priceUsd: number;
  changePct: number; // 24 saatlik değişim %
}

async function binance24hr(
  symbols: string[]
): Promise<Record<string, { last: number; change: number }>> {
  const url = `${T24}?symbols=${encodeURIComponent(JSON.stringify(symbols))}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Binance ${res.status}`);
  const data = (await res.json()) as {
    symbol: string;
    lastPrice: string;
    priceChangePercent: string;
  }[];
  const map: Record<string, { last: number; change: number }> = {};
  for (const row of data) {
    map[row.symbol] = {
      last: parseFloat(row.lastPrice),
      change: parseFloat(row.priceChangePercent),
    };
  }
  return map;
}

export async function fetchCryptoMarket(): Promise<MarketQuote[]> {
  const coins = COINS.filter((c) => c.symbol !== 'USDT');
  const symbols = ['USDTTRY', ...coins.map((c) => `${c.symbol}USDT`)];
  const map = await binance24hr(symbols);

  const usdttry = map['USDTTRY']?.last;
  if (!usdttry) throw new Error('USDTTRY kuru alınamadı');

  const out: MarketQuote[] = [];
  for (const c of coins) {
    const q = map[`${c.symbol}USDT`];
    if (!q || !isFinite(q.last)) continue;
    out.push({
      key: c.coingeckoId,
      symbol: c.symbol,
      name: c.name,
      priceUsd: q.last,
      priceTry: q.last * usdttry,
      changePct: q.change,
    });
  }
  return out;
}

export async function fetchGoldMarket(): Promise<MarketQuote[]> {
  // PAXG ≈ 1 ons (troy ounce) altın. Gram = ons / 31.1035.
  const map = await binance24hr(['USDTTRY', 'PAXGUSDT']);
  const usdttry = map['USDTTRY']?.last;
  const paxg = map['PAXGUSDT'];
  if (!usdttry || !paxg) throw new Error('Altın verisi alınamadı');

  const onsUsd = paxg.last;
  const onsTry = onsUsd * usdttry;
  const gramUsd = onsUsd / GRAMS_PER_OUNCE;
  const gramTry = onsTry / GRAMS_PER_OUNCE;

  return [
    {
      key: 'gram-altin',
      symbol: 'GRAM',
      name: 'Gram Altın',
      priceUsd: gramUsd,
      priceTry: gramTry,
      changePct: paxg.change,
    },
    {
      key: 'ons-altin',
      symbol: 'ONS',
      name: 'Ons Altın',
      priceUsd: onsUsd,
      priceTry: onsTry,
      changePct: paxg.change,
    },
  ];
}
