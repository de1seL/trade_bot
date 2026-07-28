import React from 'react';
import { TextInput } from 'react-native';
import { colors } from '../theme';

// Binlik ayraç ekle: "1234567" -> "1.234.567"
function group(intDigits: string): string {
  return intDigits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

// ─────────────────────────────────────────────────────────────
// Türkçe sayı girişi.
//
// Yazarken otomatik biçimlenir: binlikler "." ile gruplanır, ondalık ",".
// Kullanıcı sadece rakam yazar → "1959" kutuda "1.959" görünür (= bin 959).
// Virgül yalnızca ondalık (kuruş) içindir → "1959,5" -> "1.959,5".
//
// Dışarıya "normalize" değer verilir/alınır: nokta ondalıklı ("1959.5"),
// böylece parseFloat doğrudan okuyabilir.
// ─────────────────────────────────────────────────────────────
export function NumberInput({
  value,
  onChangeText,
  ...rest
}: {
  value: string; // normalize: "1959.5" / "1959" / ""
  onChangeText: (normalized: string) => void;
} & Omit<
  React.ComponentProps<typeof TextInput>,
  'value' | 'onChangeText' | 'keyboardType'
>) {
  // Görünen (Türkçe) metin.
  let display = '';
  if (value.length > 0) {
    const hasDot = value.includes('.');
    const [intRaw, fracRaw = ''] = value.split('.');
    const intp = intRaw === '' ? '0' : intRaw;
    display = group(intp) + (hasDot ? ',' + fracRaw : '');
  }

  function handle(text: string) {
    // Binlik noktalarını at, sadece rakam ve virgül bırak.
    const cleaned = text.replace(/\./g, '').replace(/[^0-9,]/g, '');
    const firstComma = cleaned.indexOf(',');
    let normalized: string;
    if (firstComma === -1) {
      normalized = cleaned;
    } else {
      const intp = cleaned.slice(0, firstComma).replace(/,/g, '');
      const frac = cleaned.slice(firstComma + 1).replace(/,/g, '').slice(0, 8);
      normalized = `${intp}.${frac}`;
    }
    onChangeText(normalized);
  }

  return (
    <TextInput
      {...rest}
      value={display}
      onChangeText={handle}
      keyboardType="decimal-pad"
      placeholderTextColor={colors.textDim}
    />
  );
}
