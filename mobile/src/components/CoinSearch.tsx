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
import { COINS, CoinOption } from '../prices/coins';
import { searchCoins } from '../prices/search';

export function CoinSearch({
  selected,
  onSelect,
}: {
  selected: CoinOption | null;
  onSelect: (c: CoinOption) => void;
}) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<CoinOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Yazarken (400ms gecikmeyle) CoinGecko'da ara.
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      setError('');
      return;
    }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await searchCoins(q);
        if (!cancelled) {
          setResults(r);
          setError(r.length === 0 ? 'Sonuç yok' : '');
        }
      } catch {
        if (!cancelled) setError('Arama başarısız (tekrar dene)');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 400);
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
        placeholder="Coin ara (btc, pepe, render…)"
        placeholderTextColor={colors.textDim}
        value={query}
        onChangeText={setQuery}
        autoCapitalize="none"
        autoCorrect={false}
      />

      {loading && (
        <ActivityIndicator style={{ marginTop: spacing.md }} color={colors.textDim} />
      )}
      {!!error && !loading && <Text style={styles.hint}>{error}</Text>}

      {/* Arama sonuçları */}
      {results.length > 0 && (
        <View style={styles.results}>
          {results.map((c) => (
            <TouchableOpacity
              key={c.coingeckoId}
              style={styles.resultRow}
              onPress={() => {
                onSelect(c);
                setQuery('');
                setResults([]);
              }}
            >
              <Text style={styles.resultSymbol}>{c.symbol}</Text>
              <Text style={styles.resultName} numberOfLines={1}>
                {c.name}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* Arama boşken popüler coin'ler hızlı seçim olarak */}
      {query.trim().length < 2 && (
        <>
          <Text style={styles.hint}>Popüler:</Text>
          <View style={styles.chips}>
            {COINS.map((c) => (
              <TouchableOpacity
                key={c.coingeckoId}
                onPress={() => onSelect(c)}
                style={[
                  styles.chip,
                  selected?.coingeckoId === c.coingeckoId && styles.chipActive,
                ]}
              >
                <Text
                  style={[
                    styles.chipText,
                    selected?.coingeckoId === c.coingeckoId &&
                      styles.chipTextActive,
                  ]}
                >
                  {c.symbol}
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
  resultSymbol: {
    color: colors.text,
    fontSize: 14,
    fontWeight: '700',
    minWidth: 60,
  },
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
