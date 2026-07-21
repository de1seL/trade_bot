// ─────────────────────────────────────────────────────────────
// Sayı / para / yüzde biçimlendirme (TL, tr-TR)
// ─────────────────────────────────────────────────────────────

export function formatTRY(value: number): string {
  if (!isFinite(value)) return '₺0';
  return (
    '₺' +
    value.toLocaleString('tr-TR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

// Büyük değerleri kısalt (₺1,25 Mn gibi) — özet kartı için.
export function formatTRYShort(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return '₺' + (value / 1_000_000).toFixed(2) + ' Mn';
  if (abs >= 1_000) return '₺' + (value / 1_000).toFixed(1) + ' B';
  return formatTRY(value);
}

export function formatPct(value: number): string {
  if (!isFinite(value)) return '%0,00';
  const sign = value > 0 ? '+' : '';
  return sign + '%' + value.toLocaleString('tr-TR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function formatQty(value: number): string {
  return value.toLocaleString('tr-TR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 8,
  });
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleDateString('tr-TR');
}
