import React from 'react';
import { TextInput } from 'react-native';
import { colors } from '../theme';

// ─────────────────────────────────────────────────────────────
// Sayı girişi. Kullanıcının yazdığını aynen gösterir (rakam, "," ve ".").
// Değerin sayıya çevrilmesi parseTRNumber ile yapılır (akıllı: "1,885" → 1885).
// ─────────────────────────────────────────────────────────────
export function NumberInput({
  value,
  onChangeText,
  ...rest
}: {
  value: string;
  onChangeText: (text: string) => void;
} & Omit<
  React.ComponentProps<typeof TextInput>,
  'value' | 'onChangeText' | 'keyboardType'
>) {
  function handle(text: string) {
    // Sadece rakam, virgül ve nokta kalsın.
    onChangeText(text.replace(/[^0-9.,]/g, ''));
  }

  return (
    <TextInput
      {...rest}
      value={value}
      onChangeText={handle}
      keyboardType="decimal-pad"
      placeholderTextColor={colors.textDim}
    />
  );
}
