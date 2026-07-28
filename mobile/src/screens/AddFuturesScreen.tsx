import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { FuturesPosition, FuturesSide } from '../types';
import { colors, spacing, radius } from '../theme';
import { CoinOption } from '../prices/coins';
import { CoinSearch } from '../components/CoinSearch';
import { NumberInput } from '../components/NumberInput';
import { parseTRNumber } from '../utils/format';

const LEVERAGES = [1, 2, 3, 5, 10, 20, 25, 50, 75, 100];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

const parseNum = parseTRNumber;

export function AddFuturesScreen({
  onAdd,
  onClose,
}: {
  onAdd: (p: FuturesPosition) => void;
  onClose: () => void;
}) {
  const [coin, setCoin] = useState<CoinOption | null>(null);
  const [side, setSide] = useState<FuturesSide>('long');
  const [entryPrice, setEntryPrice] = useState('');
  const [leverage, setLeverage] = useState(10);
  const [margin, setMargin] = useState('');
  const [openDate, setOpenDate] = useState(todayISO());
  const [error, setError] = useState('');

  function submit() {
    if (!coin) {
      setError('Coin seç');
      return;
    }
    const entry = parseNum(entryPrice);
    const mrg = parseNum(margin);
    if (entry <= 0) {
      setError('Giriş fiyatı 0’dan büyük olmalı');
      return;
    }
    if (mrg <= 0) {
      setError('Teminat 0’dan büyük olmalı');
      return;
    }
    if (leverage <= 0) {
      setError('Kaldıraç seç');
      return;
    }

    const pos: FuturesPosition = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      symbol: coin.symbol,
      name: coin.name,
      coingeckoId: coin.coingeckoId,
      side,
      entryPrice: entry,
      leverage,
      margin: mrg,
      openDate,
    };
    onAdd(pos);
  }

  const notional = parseNum(margin) * leverage;

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={onClose} hitSlop={8}>
          <Text style={styles.cancel}>İptal</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Futures Pozisyonu</Text>
        <TouchableOpacity onPress={submit} hitSlop={8}>
          <Text style={styles.save}>Kaydet</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Text style={styles.fieldLabel}>Coin (USDT.P)</Text>
        <CoinSearch selected={coin} onSelect={setCoin} />

        <Text style={styles.fieldLabel}>Yön</Text>
        <View style={styles.sideRow}>
          <TouchableOpacity
            onPress={() => setSide('long')}
            style={[
              styles.sideBtn,
              side === 'long' && { backgroundColor: colors.green, borderColor: colors.green },
            ]}
          >
            <Text style={[styles.sideText, side === 'long' && styles.sideTextActive]}>
              LONG
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setSide('short')}
            style={[
              styles.sideBtn,
              side === 'short' && { backgroundColor: colors.red, borderColor: colors.red },
            ]}
          >
            <Text style={[styles.sideText, side === 'short' && styles.sideTextActive]}>
              SHORT
            </Text>
          </TouchableOpacity>
        </View>

        <Text style={styles.fieldLabel}>Giriş Fiyatı (USDT)</Text>
        <NumberInput
          style={styles.input}
          placeholder="0"
          value={entryPrice}
          onChangeText={setEntryPrice}
        />

        <Text style={styles.fieldLabel}>Kaldıraç</Text>
        <View style={styles.chips}>
          {LEVERAGES.map((l) => (
            <TouchableOpacity
              key={l}
              onPress={() => setLeverage(l)}
              style={[styles.chip, leverage === l && styles.chipActive]}
            >
              <Text style={[styles.chipText, leverage === l && styles.chipTextActive]}>
                {l}x
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.fieldLabel}>Teminat (USDT)</Text>
        <NumberInput
          style={styles.input}
          placeholder="0"
          value={margin}
          onChangeText={setMargin}
        />
        {notional > 0 && (
          <Text style={styles.hint}>
            Pozisyon büyüklüğü: {notional.toLocaleString('en-US')} USDT
            ({leverage}x)
          </Text>
        )}

        <Text style={styles.fieldLabel}>Açılış Tarihi (YYYY-AA-GG)</Text>
        <TextInput
          style={styles.input}
          placeholder={todayISO()}
          placeholderTextColor={colors.textDim}
          value={openDate}
          onChangeText={setOpenDate}
          autoCapitalize="none"
        />

        {!!error && <Text style={styles.error}>{error}</Text>}
      </ScrollView>
    </KeyboardAvoidingView>
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
  body: { padding: spacing.lg, paddingBottom: spacing.xl * 2 },
  fieldLabel: {
    color: colors.textDim,
    fontSize: 12,
    marginTop: spacing.lg,
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
  sideRow: { flexDirection: 'row', gap: spacing.md },
  sideBtn: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  sideText: { color: colors.textDim, fontSize: 14, fontWeight: '800' },
  sideTextActive: { color: '#fff' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
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
  hint: { color: colors.textDim, fontSize: 11, marginTop: spacing.xs },
  error: {
    color: colors.red,
    fontSize: 13,
    marginTop: spacing.lg,
    textAlign: 'center',
  },
});
