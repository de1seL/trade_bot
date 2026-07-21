import { COINS, CoinOption } from './coins';

// ─────────────────────────────────────────────────────────────
// Piyasa verisi (canlı fiyat listeleri)
//
// İki kaynak sırayla denenir (biri engelliyse/limitliyse diğeri):
//   1) Binance 24s ticker — fiyat + 24s değişim, USD paritesi + USDT/TRY.
//   2) CoinGecko simple/price — try+usd + 24s değişim.
// Anahtar gerektirmez.
// ─────────────────────────────────────────────────────────────

const T24 = 'https://api.binance.com/api/v3/ticker/24hr';
const CG = 'https://api.coingecko.com/api/v3';
const GRAMS_PER_OUNCE = 31.1035;

export interface MarketQuote {
  key: string;
  symbol: string;
  name: string;
  priceTry: number;
  priceUsd: number;
  changePct: number; // 24 saatlik değişim %
}

// ── Binance ──────────────────────────────────────────────────
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

async function cryptoFromBinance(): Promise<MarketQuote[]> {
  const coins = COINS.filter((c) => c.symbol !== 'USDT');
  const symbols = ['USDTTRY', ...coins.map((c) => `${c.symbol}USDT`)];
  const map = await binance24hr(symbols);
  const usdttry = map['USDTTRY']?.last;
  if (!usdttry) throw new Error('Binance USDTTRY yok');

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
  if (out.length === 0) throw new Error('Binance veri yok');
  return out;
}

async function goldFromBinance(): Promise<MarketQuote[]> {
  const map = await binance24hr(['USDTTRY', 'PAXGUSDT']);
  const usdttry = map['USDTTRY']?.last;
  const paxg = map['PAXGUSDT'];
  if (!usdttry || !paxg) throw new Error('Binance altın verisi yok');
  return goldQuotes(paxg.last, usdttry, paxg.change);
}

// ── CoinGecko ────────────────────────────────────────────────
async function cgSimple(
  ids: string[]
): Promise<Record<string, { try?: number; usd?: number; usd_24h_change?: number }>> {
  const url = `${CG}/simple/price?ids=${encodeURIComponent(
    ids.join(',')
  )}&vs_currencies=try,usd&include_24hr_change=true`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  return (await res.json()) as Record<
    string,
    { try?: number; usd?: number; usd_24h_change?: number }
  >;
}

async function cryptoFromCoinGecko(): Promise<MarketQuote[]> {
  const coins = COINS.filter((c) => c.symbol !== 'USDT');
  const data = await cgSimple(coins.map((c) => c.coingeckoId));
  const out: MarketQuote[] = [];
  for (const c of coins) {
    const d = data[c.coingeckoId];
    if (!d || typeof d.usd !== 'number' || typeof d.try !== 'number') continue;
    out.push({
      key: c.coingeckoId,
      symbol: c.symbol,
      name: c.name,
      priceUsd: d.usd,
      priceTry: d.try,
      changePct: d.usd_24h_change ?? 0,
    });
  }
  if (out.length === 0) throw new Error('CoinGecko veri yok');
  return out;
}

async function goldFromCoinGecko(): Promise<MarketQuote[]> {
  const data = await cgSimple(['pax-gold']);
  const d = data['pax-gold'];
  if (!d || typeof d.usd !== 'number' || typeof d.try !== 'number') {
    throw new Error('CoinGecko altın verisi yok');
  }
  return goldQuotes(d.usd, d.try / d.usd, d.usd_24h_change ?? 0);
}

// PAXG (1 ons altın) → gram + ons kayıtları.
function goldQuotes(
  onsUsd: number,
  usdTry: number,
  change: number
): MarketQuote[] {
  const onsTry = onsUsd * usdTry;
  return [
    {
      key: 'gram-altin',
      symbol: 'GRAM',
      name: 'Gram Altın',
      priceUsd: onsUsd / GRAMS_PER_OUNCE,
      priceTry: onsTry / GRAMS_PER_OUNCE,
      changePct: change,
    },
    {
      key: 'ons-altin',
      symbol: 'ONS',
      name: 'Ons Altın',
      priceUsd: onsUsd,
      priceTry: onsTry,
      changePct: change,
    },
  ];
}

// ── Dışa açılan: sırayla dener, ikisi de olmazsa iki hatayı da bildirir ──
export async function fetchCryptoMarket(): Promise<MarketQuote[]> {
  try {
    return await cryptoFromBinance();
  } catch (eB: any) {
    try {
      return await cryptoFromCoinGecko();
    } catch (eC: any) {
      throw new Error(`${eB?.message ?? 'Binance?'} · ${eC?.message ?? 'CoinGecko?'}`);
    }
  }
}

export async function fetchGoldMarket(): Promise<MarketQuote[]> {
  try {
    return await goldFromBinance();
  } catch (eB: any) {
    try {
      return await goldFromCoinGecko();
    } catch (eC: any) {
      throw new Error(`${eB?.message ?? 'Binance?'} · ${eC?.message ?? 'CoinGecko?'}`);
    }
  }
}

// Aranan coin'ler için canlı fiyat listesi (CoinGecko). Piyasa aramasında
// kullanılır: kullanıcı arar → eşleşen coin'ler → fiyatları.
export async function fetchQuotesForCoins(
  coins: CoinOption[]
): Promise<MarketQuote[]> {
  if (coins.length === 0) return [];
  const data = await cgSimple(coins.map((c) => c.coingeckoId));
  const out: MarketQuote[] = [];
  for (const c of coins) {
    const d = data[c.coingeckoId];
    if (!d || typeof d.usd !== 'number' || typeof d.try !== 'number') continue;
    out.push({
      key: c.coingeckoId,
      symbol: c.symbol,
      name: c.name,
      priceUsd: d.usd,
      priceTry: d.try,
      changePct: d.usd_24h_change ?? 0,
    });
  }
  return out;
}
