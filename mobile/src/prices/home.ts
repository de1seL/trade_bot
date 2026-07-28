import { binance24hr } from './market';
import { fetchFxRates } from './fx';
import { yahooQuote } from './stocks';

// ─────────────────────────────────────────────────────────────
// Ana sayfa göstergeleri: Dolar, Euro, BIST 100, Bitcoin.
// Binance (kur/kripto) + Yahoo (BIST 100). Dayanıklı: biri düşerse diğerleri
// yine gelir.
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

export async function fetchHomeIndicators(): Promise<Indicator[]> {
  const out: Indicator[] = [];

  // Dolar / Euro / Bitcoin — önce Binance, olmazsa yedek.
  try {
    const m = await binance24hr(['USDTTRY', 'EURUSDT', 'BTCUSDT']);
    const usdTry = m['USDTTRY']?.last ?? 0;
    if (usdTry) {
      out.push({
        key: 'usd',
        label: 'Dolar',
        value: usdTry,
        unit: 'TRY',
        changePct: m['USDTTRY']?.change,
      });
      const eurUsd = m['EURUSDT']?.last;
      if (eurUsd) {
        out.push({ key: 'eur', label: 'Euro', value: eurUsd * usdTry, unit: 'TRY' });
      }
    }
    const btc = m['BTCUSDT'];
    if (btc?.last) {
      out.push({
        key: 'btc',
        label: 'Bitcoin',
        value: btc.last,
        unit: 'USD',
        changePct: btc.change,
      });
    }
  } catch {
    // Yedek: FX servisi (kur) + CoinGecko (BTC).
    try {
      const fx = await fetchFxRates();
      if (fx.USD) out.push({ key: 'usd', label: 'Dolar', value: fx.USD, unit: 'TRY' });
      if (fx.EUR) out.push({ key: 'eur', label: 'Euro', value: fx.EUR, unit: 'TRY' });
    } catch {
      // yoksay
    }
    try {
      const r = await fetch(CG_BTC, { headers: { Accept: 'application/json' } });
      if (r.ok) {
        const d = (await r.json()) as {
          bitcoin?: { usd?: number; usd_24h_change?: number };
        };
        const b = d.bitcoin;
        if (b?.usd) {
          out.push({
            key: 'btc',
            label: 'Bitcoin',
            value: b.usd,
            unit: 'USD',
            changePct: b.usd_24h_change,
          });
        }
      }
    } catch {
      // yoksay
    }
  }

  // BIST 100 endeksi (Yahoo).
  try {
    const q = await yahooQuote('XU100.IS');
    out.push({
      key: 'bist',
      label: 'BIST 100',
      value: q.price,
      unit: 'POINT',
      changePct: q.change,
    });
  } catch {
    // yoksay
  }

  // Sabit sıra: Dolar, Euro, BIST 100, Bitcoin.
  const order = ['usd', 'eur', 'bist', 'btc'];
  out.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  return out;
}
