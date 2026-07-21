import { COINS } from './coins';
import { PricePair } from '../types';

// ─────────────────────────────────────────────────────────────
// Binance yedek fiyat kaynağı
//
// CoinGecko 429 (rate limit) verdiğinde devreye girer. Anahtar gerektirmez.
// USD fiyatı doğrudan coin'in USDT paritesinden; TL fiyatı ise
// USD × USDT/TRY kuru ile hesaplanır.
// ─────────────────────────────────────────────────────────────

const BASE = 'https://api.binance.com/api/v3/ticker/price';

function baseSymbolFor(coingeckoId: string): string | null {
  const coin = COINS.find((c) => c.coingeckoId === coingeckoId);
  return coin ? coin.symbol : null;
}

export interface BinanceResult {
  pairs: Record<string, PricePair>; // coingeckoId -> {try, usd}
  usdTry: number;
}

export async function fetchBinance(
  coingeckoIds: string[]
): Promise<BinanceResult> {
  const bases = coingeckoIds
    .map((id) => ({ id, base: baseSymbolFor(id) }))
    .filter((x): x is { id: string; base: string } => !!x.base);

  const symbols = new Set<string>(['USDTTRY']);
  for (const b of bases) {
    if (b.base === 'USDT') continue; // USDT'nin USD fiyatı 1, TL fiyatı USDTTRY
    symbols.add(`${b.base}USDT`);
  }

  const url = `${BASE}?symbols=${encodeURIComponent(
    JSON.stringify(Array.from(symbols))
  )}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Binance ${res.status}`);
  const data = (await res.json()) as { symbol: string; price: string }[];

  const priceBySymbol: Record<string, number> = {};
  for (const row of data) {
    const p = parseFloat(row.price);
    if (isFinite(p)) priceBySymbol[row.symbol] = p;
  }

  const usdTry = priceBySymbol['USDTTRY'];
  if (!usdTry) throw new Error('USDTTRY kuru alınamadı');

  const pairs: Record<string, PricePair> = {};
  for (const b of bases) {
    if (b.base === 'USDT') {
      pairs[b.id] = { usd: 1, try: usdTry };
    } else {
      const usd = priceBySymbol[`${b.base}USDT`];
      if (usd) pairs[b.id] = { usd, try: usd * usdTry };
    }
  }
  return { pairs, usdTry };
}
