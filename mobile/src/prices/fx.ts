// ─────────────────────────────────────────────────────────────
// Döviz kurları — ücretsiz, anahtarsız (open.er-api.com).
// Her para biriminin 1 biriminin TL karşılığı döndürülür.
// ─────────────────────────────────────────────────────────────

export interface FxCurrency {
  code: string;
  name: string;
}

export const FX_CURRENCIES: FxCurrency[] = [
  { code: 'USD', name: 'Amerikan Doları' },
  { code: 'EUR', name: 'Euro' },
  { code: 'GBP', name: 'İngiliz Sterlini' },
  { code: 'CHF', name: 'İsviçre Frangı' },
  { code: 'JPY', name: 'Japon Yeni' },
  { code: 'CAD', name: 'Kanada Doları' },
  { code: 'AUD', name: 'Avustralya Doları' },
  { code: 'SAR', name: 'Suudi Riyali' },
  { code: 'AED', name: 'BAE Dirhemi' },
  { code: 'RUB', name: 'Rus Rublesi' },
  { code: 'CNY', name: 'Çin Yuanı' },
];

const ER = 'https://open.er-api.com/v6/latest/USD';

// code -> 1 birimin TL karşılığı (örn. USD -> 44.87)
export async function fetchFxRates(): Promise<Record<string, number>> {
  const res = await fetch(ER, { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`FX ${res.status}`);
  const json = (await res.json()) as { rates?: Record<string, number> };
  const rates = json.rates ?? {};
  const tryPerUsd = rates['TRY'];
  if (!tryPerUsd) throw new Error('TRY kuru yok');

  const out: Record<string, number> = { USD: tryPerUsd };
  for (const c of FX_CURRENCIES) {
    const perUsd = rates[c.code]; // 1 USD kaç "code"
    if (perUsd && perUsd > 0) out[c.code] = tryPerUsd / perUsd; // 1 code kaç TL
  }
  return out;
}
