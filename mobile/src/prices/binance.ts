import { COINS } from './coins';

// ─────────────────────────────────────────────────────────────
// Binance yedek fiyat kaynağı
//
// CoinGecko 429 (rate limit) verdiğinde devreye girer. Binance'in halka açık
// fiyat API'si anahtar gerektirmez ve limiti çok yüksektir. TL fiyatı,
// coin'in USDT paritesi × USDT/TRY kuru ile hesaplanır.
// ─────────────────────────────────────────────────────────────

const BASE = 'https://api.binance.com/api/v3/ticker/price';

// coingeckoId -> Binance temel sembolü (örn. "bitcoin" -> "BTC")
function baseSymbolFor(coingeckoId: string): string | null {
  const coin = COINS.find((c) => c.coingeckoId === coingeckoId);
  return coin ? coin.symbol : null;
}

// İstenen coingeckoId'ler için TL fiyat haritası döndürür.
export async function fetchBinanceTRYPrices(
  coingeckoIds: string[]
): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  if (coingeckoIds.length === 0) return out;

  const bases = coingeckoIds
    .map((id) => ({ id, base: baseSymbolFor(id) }))
    .filter((x): x is { id: string; base: string } => !!x.base);

  // Çekilecek Binance sembolleri: her coin'in USDT paritesi + USDT/TRY kuru.
  const symbols = new Set<string>(['USDTTRY']);
  for (const b of bases) {
    if (b.base === 'USDT') continue; // USDT'nin TL fiyatı doğrudan USDTTRY
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

  const usdttry = priceBySymbol['USDTTRY'];
  if (!usdttry) throw new Error('USDTTRY kuru alınamadı');

  for (const b of bases) {
    if (b.base === 'USDT') {
      out[b.id] = usdttry;
    } else {
      const usd = priceBySymbol[`${b.base}USDT`];
      if (usd) out[b.id] = usd * usdttry; // USDT fiyatını TL'ye çevir
    }
  }
  return out;
}
