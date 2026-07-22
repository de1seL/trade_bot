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
import { BIST } from '../prices/bist';
import { StockRef, searchStocks } from '../prices/stocks';

const POPULAR: StockRef[] = BIST.slice(0, 10).map((s) => ({
  symbol: s.symbol,
  fullSymbol: `${s.symbol}.IS`,
  name: s.name,
}));

export function StockSearch({
  selected,
  onSelect,
}: {
  selected: StockRef | null;
  onSelect: (s: StockRef) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockRef[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) {
      setResults([]);
      setError('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await searchStocks(q);
        if (!cancelled) {
          setResults(r);
          setError(r.length === 0 ? 'Sonuç yok' : '');
        }
      } catch {
        if (!cancelled) setError('Arama başarısız');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query]);

  return (
    <View>
      {selected && (
        <View style={styles.selected}>
          <Text style={styles.selectedText}>
            Seçili: {selected.symbol} · {selected.name}
          </Text>
        </View>
      )}

      <TextInput
        style={styles.input}
        placeholder="Hisse ara (THYAO, garanti…)"
        placeholderTextColor={colors.textDim}
        value={query}
        onChangeText={setQuery}
        autoCapitalize="characters"
        autoCorrect={false}
      />

      {loading && (
        <ActivityIndicator style={{ marginTop: spacing.md }} color={colors.textDim} />
      )}
      {!!error && !loading && <Text style={styles.hint}>{error}</Text>}

      {results.length > 0 && (
        <View style={styles.results}>
          {results.map((s) => (
            <TouchableOpacity
              key={s.fullSymbol}
              style={styles.resultRow}
              onPress={() => {
                onSelect(s);
                setQuery('');
                setResults([]);
              }}
            >
              <Text style={styles.resultSymbol}>{s.symbol}</Text>
              <Text style={styles.resultName} numberOfLines={1}>
                {s.name}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {query.trim().length < 1 && (
        <>
          <Text style={styles.hint}>Popüler:</Text>
          <View style={styles.chips}>
            {POPULAR.map((s) => (
              <TouchableOpacity
                key={s.fullSymbol}
                onPress={() => onSelect(s)}
                style={[
                  styles.chip,
                  selected?.symbol === s.symbol && styles.chipActive,
                ]}
              >
                <Text
                  style={[
                    styles.chipText,
                    selected?.symbol === s.symbol && styles.chipTextActive,
                  ]}
                >
                  {s.symbol}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </>
      )}
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
  results: {
    marginTop: spacing.sm,
    backgroundColor: colors.card,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  resultRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    gap: spacing.md,
  },
  resultSymbol: { color: colors.text, fontSize: 14, fontWeight: '700', minWidth: 60 },
  resultName: { color: colors.textDim, fontSize: 13, flex: 1 },
  hint: { color: colors.textDim, fontSize: 11, marginTop: spacing.md },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm },
  chip: {
    backgroundColor: colors.card,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipText: { color: colors.textDim, fontSize: 13, fontWeight: '600' },
  chipTextActive: { color: '#fff' },
});
