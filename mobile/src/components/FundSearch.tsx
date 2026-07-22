import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { colors, spacing, radius } from '../theme';
import { fetchFundInfo, FundInfo } from '../prices/funds';
import { formatTRY } from '../utils/format';

export function FundSearch({
  selected,
  onSelect,
}: {
  selected: { code: string; name: string } | null;
  onSelect: (f: { code: string; name: string }) => void;
}) {
  const [code, setCode] = useState('');
  const [result, setResult] = useState<FundInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const c = code.trim().toUpperCase();
    if (c.length < 2) {
      setResult(null);
      setError('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const info = await fetchFundInfo(c);
        if (!cancelled) {
          setResult(info);
          setError('');
        }
      } catch (e: any) {
        if (!cancelled) {
          setResult(null);
          setError(e?.message ?? 'Bulunamadı');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 500);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [code]);

  return (
    <View>
      {selected && (
        <View style={styles.selected}>
          <Text style={styles.selectedText}>
            Seçili: {selected.code} · {selected.name}
          </Text>
        </View>
      )}

      <TextInput
        style={styles.input}
        placeholder="Fon kodu (örn. AAK, TTE, IPB)"
        placeholderTextColor={colors.textDim}
        value={code}
        onChangeText={setCode}
        autoCapitalize="characters"
        autoCorrect={false}
      />

      {loading && (
        <ActivityIndicator style={{ marginTop: spacing.md }} color={colors.textDim} />
      )}
      {!!error && !loading && <Text style={styles.hint}>{error}</Text>}

      {result && !loading && (
        <TouchableOpacity
          style={styles.resultRow}
          onPress={() => onSelect({ code: result.code, name: result.name })}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.resultSymbol}>{result.code}</Text>
            <Text style={styles.resultName} numberOfLines={2}>
              {result.name}
            </Text>
          </View>
          <Text style={styles.resultPrice}>{formatTRY(result.priceTry)}</Text>
        </TouchableOpacity>
      )}

      <Text style={styles.hint}>
        Fon kodunu yaz; adı ve güncel fiyatı TEFAS'tan gelir, üzerine dokunup seç.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  selected: {
    backgroundColor: colors.primary + '22',
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
  },
  selectedText: { color: colors.primary, fontSize: 13, fontWeight: '600' },
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
  resultRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.sm,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.primary,
    padding: spacing.md,
    gap: spacing.md,
  },
  resultSymbol: { color: colors.text, fontSize: 15, fontWeight: '700' },
  resultName: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  resultPrice: { color: colors.text, fontSize: 14, fontWeight: '600' },
  hint: { color: colors.textDim, fontSize: 11, marginTop: spacing.md, lineHeight: 16 },
});
