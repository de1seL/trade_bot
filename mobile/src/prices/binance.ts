import { PricePair } from '../types';

// ─────────────────────────────────────────────────────────────
// Binance yedek fiyat kaynağı
//
// CoinGecko 429 (rate limit) verdiğinde devreye girer. Anahtar gerektirmez.
// USD fiyatı coin'in USDT paritesinden; TL fiyatı USD × USDT/TRY ile hesaplanır.
// Coin'ler sembolleriyle (BTC, ETH, PEPE...) verilir, sabit listeye bağlı değil.
// ─────────────────────────────────────────────────────────────

const BASE = 'https://api.binance.com/api/v3/ticker/price';

export interface CoinRef {
  coingeckoId: string;
  symbol: string; // Binance temel sembolü (örn. BTC)
}

export interface BinanceResult {
  pairs: Record<string, PricePair>; // coingeckoId -> {try, usd}
  usdTry: number;
}

export async function fetchBinance(coins: CoinRef[]): Promise<BinanceResult> {
  const symbols = new Set<string>(['USDTTRY']);
  for (const c of coins) {
    const base = c.symbol.toUpperCase();
    if (base === 'USDT') continue; // USDT: usd=1, try=USDTTRY
    symbols.add(`${base}USDT`);
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
  for (const c of coins) {
    const base = c.symbol.toUpperCase();
    if (base === 'USDT') {
      pairs[c.coingeckoId] = { usd: 1, try: usdTry };
    } else {
      const usd = priceBySymbol[`${base}USDT`];
      if (usd) pairs[c.coingeckoId] = { usd, try: usd * usdTry };
    }
  }
  return { pairs, usdTry };
}
