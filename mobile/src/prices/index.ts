import { Holding } from '../types';

// ─────────────────────────────────────────────────────────────
// Fiyat servisi
//
// Bugün: kripto fiyatları CoinGecko'dan canlı (TL cinsinden, ücretsiz,
// anahtar gerektirmez). Diğer varlıklar (hisse/altın/döviz/fon) kullanıcının
// girdiği manuel güncel fiyatla değerlenir.
//
// İleride: buraya bir "provider" daha eklenince (örn. altın/USDTRY için bir
// ücretsiz API) o türler de otomatik canlıya döner. Ekranların değişmesi
// gerekmez — sadece bu dosya priceMap'e o türleri doldurur.
// ─────────────────────────────────────────────────────────────

const COINGECKO_URL = 'https://api.coingecko.com/api/v3/simple/price';

export interface PriceResult {
  // holding.id -> güncel birim fiyat (TL)
  priceMap: Record<string, number>;
  // canlı fiyat çekilebildi mi (ağ sorunlarını kullanıcıya bildirmek için)
  ok: boolean;
  error?: string;
}

async function fetchCryptoPrices(
  ids: string[]
): Promise<Record<string, number>> {
  if (ids.length === 0) return {};
  const url = `${COINGECKO_URL}?ids=${encodeURIComponent(
    ids.join(',')
  )}&vs_currencies=try`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`CoinGecko ${res.status}`);
  const data = (await res.json()) as Record<string, { try?: number }>;
  const out: Record<string, number> = {};
  for (const id of ids) {
    const p = data[id]?.try;
    if (typeof p === 'number') out[id] = p;
  }
  return out;
}

export async function fetchPrices(holdings: Holding[]): Promise<PriceResult> {
  const priceMap: Record<string, number> = {};

  // Kripto pozisyonlarının benzersiz CoinGecko id'lerini topla.
  const cryptoHoldings = holdings.filter(
    (h) => h.type === 'crypto' && h.coingeckoId
  );
  const ids = Array.from(
    new Set(cryptoHoldings.map((h) => h.coingeckoId as string))
  );

  try {
    const cryptoPrices = await fetchCryptoPrices(ids);
    // id bazlı fiyatları holding.id bazına yay.
    for (const h of cryptoHoldings) {
      const p = cryptoPrices[h.coingeckoId as string];
      if (typeof p === 'number') priceMap[h.id] = p;
    }
    return { priceMap, ok: true };
  } catch (e: any) {
    // Ağ hatası: kripto fiyatları güncellenemedi. Diğer varlıklar zaten
    // manuel fiyatla çalışmaya devam eder.
    return { priceMap, ok: false, error: e?.message ?? 'Ağ hatası' };
  }
}
