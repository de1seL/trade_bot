// ─────────────────────────────────────────────────────────────
// Basit tema — koyu arka plan, tek yerden renk yönetimi
// ─────────────────────────────────────────────────────────────

export const colors = {
  bg: '#0B0E14',
  card: '#151A23',
  cardAlt: '#1C2230',
  border: '#232B3A',
  text: '#E6EAF2',
  textDim: '#8A93A6',
  primary: '#4C8DFF',
  green: '#26C281',
  red: '#FF5C5C',
  gold: '#E0B341',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
};

// Varlık türü → görünen etiket + renk ipucu (dağılım çubuğu ve rozetler için)
export const assetMeta: Record<string, { label: string; color: string }> = {
  crypto: { label: 'Kripto', color: '#F7931A' },
  stock: { label: 'Hisse', color: '#4C8DFF' },
  gold: { label: 'Altın', color: '#E0B341' },
  fx: { label: 'Döviz', color: '#26C281' },
  fund: { label: 'Fon', color: '#A46BFF' },
  cash: { label: 'Nakit', color: '#8A93A6' },
};
