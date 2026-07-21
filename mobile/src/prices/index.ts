import { Holding, PricePair } from '../types';
import { fetchBinance } from './binance';

// ─────────────────────────────────────────────────────────────
// Fiyat servisi
//
// Kripto fiyatları hem TL hem USD olarak, iki kaynaktan sırayla denenir:
//   1) CoinGecko — try + usd birlikte.
//   2) Binance — CoinGecko 429 verirse yedek (USDT paritesi + USDT/TRY).
// Ayrıca güncel USD/TRY kuru döndürülür (TL/USD çevirileri için).
// ─────────────────────────────────────────────────────────────

const COINGECKO_URL = 'https://api.coingecko.com/api/v3/simple/price';

export interface PriceResult {
  priceMap: Record<string, PricePair>; // holding.id -> {try, usd}
  usdTry: number | null; // güncel USD/TRY kuru
  ok: boolean;
  source?: 'coingecko' | 'binance';
  error?: string;
}

interface CoinGeckoData {
  pairs: Record<string, PricePair>; // coingeckoId -> {try, usd}
  usdTry: number | null;
}

async function fetchCoinGecko(ids: string[]): Promise<CoinGeckoData> {
  // 'tether' her zaman eklenir → USD/TRY kurunu ondan okuruz.
  const reqIds = Array.from(new Set([...ids, 'tether']));
  const url = `${COINGECKO_URL}?ids=${encodeURIComponent(
    reqIds.join(',')
  )}&vs_currencies=try,usd`;
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  const data = (await res.json()) as Record<
    string,
    { try?: number; usd?: number }
  >;

  const pairs: Record<string, PricePair> = {};
  for (const id of ids) {
    const t = data[id]?.try;
    const u = data[id]?.usd;
    if (typeof t === 'number' && typeof u === 'number') {
      pairs[id] = { try: t, usd: u };
    }
  }
  const tether = data['tether'];
  const usdTry =
    tether && typeof tether.try === 'number' ? tether.try : null;
  return { pairs, usdTry };
}

// coingeckoId bazlı çiftleri holding.id bazına yay.
function applyToHoldings(
  cryptoHoldings: Holding[],
  idPairs: Record<string, PricePair>,
  priceMap: Record<string, PricePair>
): number {
  let applied = 0;
  for (const h of cryptoHoldings) {
    const pair = idPairs[h.coingeckoId as string];
    if (pair) {
      priceMap[h.id] = pair;
      applied++;
    }
  }
  return applied;
}

export async function fetchPrices(holdings: Holding[]): Promise<PriceResult> {
  const priceMap: Record<string, PricePair> = {};

  const cryptoHoldings = holdings.filter(
    (h) => h.type === 'crypto' && h.coingeckoId
  );
  const ids = Array.from(
    new Set(cryptoHoldings.map((h) => h.coingeckoId as string))
  );

  // 1) Önce CoinGecko.
  try {
    const cg = await fetchCoinGecko(ids);
    applyToHoldings(cryptoHoldings, cg.pairs, priceMap);
    // Kur alındıysa (kriptosuz portföyde bile) başarı say.
    if (cg.usdTry !== null) {
      return { priceMap, usdTry: cg.usdTry, ok: true, source: 'coingecko' };
    }
  } catch {
    // 429 / ağ — Binance'e düş.
  }

  // 2) Yedek: Binance.
  try {
    const bn = await fetchBinance(ids);
    applyToHoldings(cryptoHoldings, bn.pairs, priceMap);
    return { priceMap, usdTry: bn.usdTry, ok: true, source: 'binance' };
  } catch (e: any) {
    return {
      priceMap,
      usdTry: null,
      ok: false,
      error: e?.message ?? 'Ağ hatası',
    };
  }
}
