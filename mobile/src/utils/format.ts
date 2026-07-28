// ─────────────────────────────────────────────────────────────
// Sayı / para / yüzde biçimlendirme — Türkçe (binlik ".", ondalık ",")
//
// Not: toLocaleString('tr-TR') React Native (Hermes) üzerinde çoğu zaman
// yerel desteği olmadığından İngilizce formata düşer (1.959 → "1.959").
// Bu yüzden biçimleme elle yapılır; her cihazda tutarlı Türkçe görünür.
// ─────────────────────────────────────────────────────────────

// Binlik ayraç ekle: "1234567" -> "1.234.567"
function groupThousands(intPart: string): string {
  return intPart.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

// value'yu Türkçe biçimle. minFrac..maxFrac ondalık; fazla sıfırlar atılır.
function formatNumberTR(value: number, minFrac: number, maxFrac: number): string {
  if (!isFinite(value)) return '0';
  const neg = value < 0;
  const fixed = Math.abs(value).toFixed(maxFrac); // "1234.5678"
  const dot = fixed.indexOf('.');
  let intp = dot === -1 ? fixed : fixed.slice(0, dot);
  let frac = dot === -1 ? '' : fixed.slice(dot + 1);

  // maxFrac'e kadar yuvarlandı; şimdi minFrac'in üstündeki sıfırları kırp.
  if (frac.length > minFrac) frac = frac.replace(/0+$/, '');
  while (frac.length < minFrac) frac += '0';

  const grouped = groupThousands(intp);
  const body = frac.length > 0 ? `${grouped},${frac}` : grouped;
  return (neg ? '-' : '') + body;
}

export function formatTRY(value: number): string {
  if (!isFinite(value)) return '₺0';
  return '₺' + formatNumberTR(value, 2, 2);
}

export function formatUSD(value: number): string {
  if (!isFinite(value)) return '$0';
  return '$' + formatNumberTR(value, 2, 2);
}

// Seçilen para birimine göre biçimle.
export function formatMoney(value: number, currency: 'TRY' | 'USD'): string {
  return currency === 'USD' ? formatUSD(value) : formatTRY(value);
}

// Büyük değerleri kısalt (₺1,25 Mn gibi) — özet kartı için.
export function formatTRYShort(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return '₺' + formatNumberTR(value / 1_000_000, 2, 2) + ' Mn';
  if (abs >= 1_000) return '₺' + formatNumberTR(value / 1_000, 1, 1) + ' B';
  return formatTRY(value);
}

export function formatPct(value: number): string {
  if (!isFinite(value)) return '%0,00';
  const sign = value > 0 ? '+' : '';
  return sign + '%' + formatNumberTR(value, 2, 2);
}

export function formatQty(value: number): string {
  return formatNumberTR(value, 0, 8);
}

// Kullanıcının yazdığı sayıyı akıllıca çöz (TR/EN karışık girişe dayanıklı):
//  - "1.234,56" veya "1,234.56" → 1234.56  (son ayraç ondalık)
//  - "1,885" veya "1.885"       → 1885      (tek ayraç + 3 hane = binlik)
//  - "0,5" / "1,88" / "12,5"    → ondalık
//  - "1885"                     → 1885
export function parseTRNumber(s: string): number {
  const str = (s ?? '').trim();
  if (!str) return 0;
  const hasComma = str.includes(',');
  const hasDot = str.includes('.');

  let dec: ',' | '.' | null = null;
  if (hasComma && hasDot) {
    dec = str.lastIndexOf(',') > str.lastIndexOf('.') ? ',' : '.';
  } else if (hasComma || hasDot) {
    const sep = hasComma ? ',' : '.';
    const occ = str.split(sep).length - 1;
    const after = str.slice(str.lastIndexOf(sep) + 1);
    // Tek ayraç + arkasından tam 3 hane → binlik (ondalık değil).
    dec = occ === 1 && after.length !== 3 ? sep : null;
  }

  let normalized: string;
  if (!dec) {
    normalized = str.replace(/[.,]/g, '');
  } else {
    const idx = str.lastIndexOf(dec);
    const intp = str.slice(0, idx).replace(/[.,]/g, '');
    const frac = str.slice(idx + 1).replace(/[.,]/g, '');
    normalized = `${intp}.${frac}`;
  }
  const n = parseFloat(normalized);
  return isNaN(n) ? 0 : n;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '-';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
}
