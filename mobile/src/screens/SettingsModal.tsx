import React, { useState } from 'react';
import { View, Text, StyleSheet, TextInput, TouchableOpacity } from 'react-native';
import { Settings } from '../types';
import { colors, spacing, radius } from '../theme';

export function SettingsModal({
  settings,
  onSave,
  onClose,
}: {
  settings: Settings;
  onSave: (s: Settings) => void;
  onClose: () => void;
}) {
  const [inflation, setInflation] = useState(String(settings.annualInflation));

  function save() {
    const n = parseFloat(inflation.replace(',', '.'));
    onSave({
      ...settings,
      annualInflation: isNaN(n) ? settings.annualInflation : n,
    });
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={onClose} hitSlop={8}>
          <Text style={styles.cancel}>Kapat</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Ayarlar</Text>
        <TouchableOpacity onPress={save} hitSlop={8}>
          <Text style={styles.save}>Kaydet</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.body}>
        <Text style={styles.fieldLabel}>Yıllık Enflasyon (%)</Text>
        <TextInput
          style={styles.input}
          value={inflation}
          onChangeText={setInflation}
          keyboardType="decimal-pad"
          placeholderTextColor={colors.textDim}
        />
        <Text style={styles.hint}>
          Reel (enflasyona göre düzeltilmiş) getiri bu oranı kullanır. TÜİK
          verisini ya da kendi beklentini girebilirsin.
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  title: { color: colors.text, fontSize: 17, fontWeight: '600' },
  cancel: { color: colors.textDim, fontSize: 15 },
  save: { color: colors.primary, fontSize: 15, fontWeight: '700' },
  body: { padding: spacing.lg },
  fieldLabel: {
    color: colors.textDim,
    fontSize: 12,
    marginBottom: spacing.sm,
  },
  input: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    fontSize: 16,
  },
  hint: { color: colors.textDim, fontSize: 12, marginTop: spacing.md, lineHeight: 18 },
});
