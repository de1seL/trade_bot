import { PricePair } from '../types';
import { CoinRef, fetchBinance } from './binance';

// ─────────────────────────────────────────────────────────────
// Fiyat servisi (coin bazlı)
//
// Verilen coin'ler (coingeckoId + symbol) için hem TL hem USD fiyat ve güncel
// USD/TRY kuru döndürür. İki kaynak sırayla denenir:
//   1) CoinGecko — try + usd birlikte, id ile.
//   2) Binance — 429 durumunda yedek, sembol ile (USDT paritesi).
//
// Sonuç coingeckoId bazında döner; hem spot portföy hem futures aynı sonucu
// kullanır (tek ağ çağrısı).
// ─────────────────────────────────────────────────────────────

export type { CoinRef };

const COINGECKO_URL = 'https://api.coingecko.com/api/v3/simple/price';

export interface MarketResult {
  pairs: Record<string, PricePair>; // coingeckoId -> {try, usd}
  usdTry: number | null;
  ok: boolean;
  source?: 'coingecko' | 'binance';
  error?: string;
}

async function fetchCoinGecko(
  ids: string[]
): Promise<{ pairs: Record<string, PricePair>; usdTry: number | null }> {
  const reqIds = Array.from(new Set([...ids, 'tether'])); // tether → USD/TRY
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
  const usdTry = tether && typeof tether.try === 'number' ? tether.try : null;
  return { pairs, usdTry };
}

export async function fetchMarket(coins: CoinRef[]): Promise<MarketResult> {
  const ids = Array.from(new Set(coins.map((c) => c.coingeckoId)));

  // 1) CoinGecko
  try {
    const cg = await fetchCoinGecko(ids);
    if (cg.usdTry !== null || Object.keys(cg.pairs).length > 0) {
      return {
        pairs: cg.pairs,
        usdTry: cg.usdTry,
        ok: true,
        source: 'coingecko',
      };
    }
  } catch {
    // 429 / ağ → Binance
  }

  // 2) Binance yedek
  try {
    const bn = await fetchBinance(coins);
    return { pairs: bn.pairs, usdTry: bn.usdTry, ok: true, source: 'binance' };
  } catch (e: any) {
    return {
      pairs: {},
      usdTry: null,
      ok: false,
      error: e?.message ?? 'Ağ hatası',
    };
  }
}
