// ─────────────────────────────────────────────────────────────
// TEFAS fon fiyatları (resmi olmayan uç nokta).
// Fon kodu (örn. AAK) ile son fiyat + fon adı çekilir. TL bazında.
// Not: TEFAS Türkiye'den erişilebilir; bazı ağlarda kısıtlı olabilir.
// ─────────────────────────────────────────────────────────────

const TEFAS = 'https://www.tefas.gov.tr/api/DB/BindHistoryInfo';

export interface FundInfo {
  code: string;
  name: string;
  priceTry: number;
}

function fmtDate(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
}

export async function fetchFundInfo(code: string): Promise<FundInfo> {
  const c = code.trim().toUpperCase();
  if (c.length < 2) throw new Error('Fon kodu kısa');

  const end = new Date();
  const start = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000);
  const body =
    `fontip=YAT&sfontur=&fonkod=${encodeURIComponent(c)}&fongrup=` +
    `&bastarih=${fmtDate(start)}&bittarih=${fmtDate(end)}` +
    `&fonturkod=&fonunvantip=`;

  const res = await fetch(TEFAS, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      Accept: 'application/json',
    },
    body,
  });
  if (!res.ok) throw new Error(`TEFAS ${res.status}`);
  const json = (await res.json()) as {
    data?: { TARIH: string; FONKODU: string; FONUNVAN: string; FIYAT: number | string }[];
  };
  const rows = json.data ?? [];
  if (rows.length === 0) throw new Error('Fon bulunamadı');

  // En yeni tarihli kaydı al.
  rows.sort((a, b) => Number(b.TARIH) - Number(a.TARIH));
  const latest = rows[0];
  const price = parseFloat(String(latest.FIYAT));
  if (!isFinite(price)) throw new Error('Fon fiyatı yok');

  return { code: c, name: latest.FONUNVAN || c, priceTry: price };
}

// Birden çok fon için son fiyatlar (kod -> TL).
export async function fetchFundPrices(
  codes: string[]
): Promise<Record<string, number>> {
  const out: Record<string, number> = {};
  const settled = await Promise.allSettled(codes.map((c) => fetchFundInfo(c)));
  settled.forEach((s) => {
    if (s.status === 'fulfilled') out[s.value.code] = s.value.priceTry;
  });
  return out;
}
