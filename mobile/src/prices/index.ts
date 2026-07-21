import { Holding } from '../types';
import { fetchBinanceTRYPrices } from './binance';

// ─────────────────────────────────────────────────────────────
// Fiyat servisi
//
// Kripto fiyatları iki kaynaktan, sırayla denenerek çekilir:
//   1) CoinGecko — doğrudan TL (try) verir, tüm coin'leri kapsar.
//   2) Binance — CoinGecko rate-limit (429) verirse yedek. USDT paritesi ×
//      USDT/TRY ile TL fiyat hesaplar. Anahtar gerektirmez, limiti yüksektir.
//
// Diğer varlıklar (hisse/altın/döviz/fon) kullanıcının girdiği manuel güncel
// fiyatla değerlenir. İleride buraya bir sağlayıcı daha eklenince o türler de
// otomatik canlıya döner; ekranların değişmesi gerekmez.
// ─────────────────────────────────────────────────────────────

const COINGECKO_URL = 'https://api.coingecko.com/api/v3/simple/price';

export interface PriceResult {
  // holding.id -> güncel birim fiyat (TL)
  priceMap: Record<string, number>;
  // canlı fiyat çekilebildi mi (ağ sorunlarını kullanıcıya bildirmek için)
  ok: boolean;
  // hangi kaynaktan geldi (bilgi amaçlı)
  source?: 'coingecko' | 'binance';
  error?: string;
}

async function fetchCoinGeckoTRY(
  ids: string[]
): Promise<Record<string, number>> {
  if (ids.length === 0) return {};
  const url = `${COINGECKO_URL}?ids=${encodeURIComponent(
    ids.join(',')
  )}&vs_currencies=try`;
  const res = await fetch(url, {
    headers: { Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  const data = (await res.json()) as Record<string, { try?: number }>;
  const out: Record<string, number> = {};
  for (const id of ids) {
    const p = data[id]?.try;
    if (typeof p === 'number') out[id] = p;
  }
  return out;
}

// id bazlı fiyatları holding.id bazına yay.
function applyToHoldings(
  cryptoHoldings: Holding[],
  idPrices: Record<string, number>,
  priceMap: Record<string, number>
): number {
  let applied = 0;
  for (const h of cryptoHoldings) {
    const p = idPrices[h.coingeckoId as string];
    if (typeof p === 'number') {
      priceMap[h.id] = p;
      applied++;
    }
  }
  return applied;
}

export async function fetchPrices(holdings: Holding[]): Promise<PriceResult> {
  const priceMap: Record<string, number> = {};

  const cryptoHoldings = holdings.filter(
    (h) => h.type === 'crypto' && h.coingeckoId
  );
  const ids = Array.from(
    new Set(cryptoHoldings.map((h) => h.coingeckoId as string))
  );

  if (ids.length === 0) return { priceMap, ok: true };

  // 1) Önce CoinGecko (doğrudan TL).
  try {
    const cg = await fetchCoinGeckoTRY(ids);
    if (applyToHoldings(cryptoHoldings, cg, priceMap) > 0) {
      return { priceMap, ok: true, source: 'coingecko' };
    }
  } catch {
    // 429 veya ağ hatası — Binance'e düş.
  }

  // 2) Yedek: Binance (USDT × USDT/TRY).
  try {
    const bn = await fetchBinanceTRYPrices(ids);
    if (applyToHoldings(cryptoHoldings, bn, priceMap) > 0) {
      return { priceMap, ok: true, source: 'binance' };
    }
  } catch (e: any) {
    return { priceMap, ok: false, error: e?.message ?? 'Ağ hatası' };
  }

  return { priceMap, ok: false, error: 'Fiyat alınamadı' };
}
