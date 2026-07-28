import { binance24hr, fetchGoldMarket } from './market';
import { fetchFxRates } from './fx';
import { yahooQuote } from './stocks';
import { parseTRNumber } from '../utils/format';

// ─────────────────────────────────────────────────────────────
// Ana sayfa göstergeleri: Dolar, Euro, Gram Altın, Gram Gümüş, BIST 100, BTC.
// Altın/gümüş için önce Türk finans verisi (Kapalıçarşı gram fiyatları),
// olmazsa uluslararası spot'tan hesaplanır. Diğerleri Binance/Yahoo.
// ─────────────────────────────────────────────────────────────

export interface Indicator {
  key: string;
  label: string;
  value: number;
  unit: 'TRY' | 'USD' | 'POINT';
  changePct?: number;
}

const CG_BTC =
  'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true';
const TRUNCGIL = 'https://finans.truncgil.com/today.json';
const GOLDAPI_XAG = 'https://api.gold-api.com/price/XAG';
const GRAMS_PER_OUNCE = 31.1035;

function pickField(v: any, keys: string[]): number | undefined {
  for (const k of keys) {
    if (v[k] !== undefined && v[k] !== null && v[k] !== '') {
      const n = parseTRNumber(String(v[k]));
      if (isFinite(n) && n !== 0) return n;
    }
  }
  return undefined;
}

// Kapalıçarşı gram altın/gümüş (truncgil). Bulunamazsa boş döner.
async function fromTruncgil(): Promise<{
  gold?: { value: number; change?: number };
  silver?: { value: number; change?: number };
}> {
  const res = await fetch(TRUNCGIL, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`truncgil ${res.status}`);
  const data = (await res.json()) as Record<string, any>;

  let gold: { value: number; change?: number } | undefined;
  let silver: { value: number; change?: number } | undefined;

  for (const [k, v] of Object.entries(data)) {
    if (typeof v !== 'object' || v === null) continue;
    const key = k.toLocaleLowerCase('tr-TR');
    const name = String(v.Name ?? v.name ?? '').toLocaleLowerCase('tr-TR');
    const price = pickField(v, ['Satış', 'Selling', 'Alış', 'Buying']);
    if (price === undefined) continue;
    const change = pickField(v, ['Değişim', 'Change']);

    const isGram = key.includes('gram') || name.includes('gram');
    if (!gold && isGram && (key.includes('alt') || name.includes('altın'))) {
      gold = { value: price, change };
    }
    if (
      !silver &&
      (key.includes('gumus') || key.includes('gümüş') || name.includes('gümüş'))
    ) {
      silver = { value: price, change };
    }
  }
  return { gold, silver };
}

export async function fetchHomeIndicators(): Promise<Indicator[]> {
  const out: Indicator[] = [];
  let usdTry = 0;

  // Dolar / Euro / Bitcoin.
  try {
    const m = await binance24hr(['USDTTRY', 'EURUSDT', 'BTCUSDT']);
    usdTry = m['USDTTRY']?.last ?? 0;
    if (usdTry) {
      out.push({ key: 'usd', label: 'Dolar', value: usdTry, unit: 'TRY', changePct: m['USDTTRY']?.change });
      const eurUsd = m['EURUSDT']?.last;
      if (eurUsd) out.push({ key: 'eur', label: 'Euro', value: eurUsd * usdTry, unit: 'TRY' });
    }
    const btc = m['BTCUSDT'];
    if (btc?.last) out.push({ key: 'btc', label: 'Bitcoin', value: btc.last, unit: 'USD', changePct: btc.change });
  } catch {
    try {
      const fx = await fetchFxRates();
      usdTry = fx.USD ?? 0;
      if (fx.USD) out.push({ key: 'usd', label: 'Dolar', value: fx.USD, unit: 'TRY' });
      if (fx.EUR) out.push({ key: 'eur', label: 'Euro', value: fx.EUR, unit: 'TRY' });
    } catch {
      // yoksay
    }
    try {
      const r = await fetch(CG_BTC, { headers: { Accept: 'application/json' } });
      if (r.ok) {
        const d = (await r.json()) as { bitcoin?: { usd?: number; usd_24h_change?: number } };
        if (d.bitcoin?.usd)
          out.push({ key: 'btc', label: 'Bitcoin', value: d.bitcoin.usd, unit: 'USD', changePct: d.bitcoin.usd_24h_change });
      }
    } catch {
      // yoksay
    }
  }

  // Gram Altın / Gram Gümüş — önce Kapalıçarşı (truncgil), sonra spot.
  let gold: { value: number; change?: number } | undefined;
  let silver: { value: number; change?: number } | undefined;
  try {
    const t = await fromTruncgil();
    gold = t.gold;
    silver = t.silver;
  } catch {
    // yoksay
  }
  if (!gold) {
    try {
      const g = await fetchGoldMarket(); // [GRAM, ONS] TL
      const gram = g.find((x) => x.symbol === 'GRAM');
      if (gram) gold = { value: gram.priceTry, change: gram.changePct };
    } catch {
      // yoksay
    }
  }
  if (!silver && usdTry) {
    try {
      const r = await fetch(GOLDAPI_XAG, { headers: { Accept: 'application/json' } });
      if (r.ok) {
        const d = (await r.json()) as { price?: number };
        if (d.price) silver = { value: (d.price / GRAMS_PER_OUNCE) * usdTry };
      }
    } catch {
      // yoksay
    }
  }
  if (gold) out.push({ key: 'gold', label: 'Gram Altın', value: gold.value, unit: 'TRY', changePct: gold.change });
  if (silver) out.push({ key: 'silver', label: 'Gram Gümüş', value: silver.value, unit: 'TRY', changePct: silver.change });

  // BIST 100.
  try {
    const q = await yahooQuote('XU100.IS');
    out.push({ key: 'bist', label: 'BIST 100', value: q.price, unit: 'POINT', changePct: q.change });
  } catch {
    // yoksay
  }

  const order = ['usd', 'eur', 'gold', 'silver', 'bist', 'btc'];
  out.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  return out;
}
