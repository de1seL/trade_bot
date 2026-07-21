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
import { AssetType, BuyCurrency, Holding } from '../types';
import { colors, spacing, radius, assetMeta } from '../theme';
import { COINS, CoinOption } from '../prices/coins';
import { CoinSearch } from '../components/CoinSearch';

const TYPES: AssetType[] = ['crypto', 'stock', 'gold', 'fx', 'fund', 'cash'];
const CURRENCIES: { value: BuyCurrency; label: string }[] = [
  { value: 'TRY', label: 'TL' },
  { value: 'USD', label: 'USD' },
  { value: 'USDT', label: 'USDT' },
  { value: 'USDC', label: 'USDC' },
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function parseNum(s: string): number {
  const n = parseFloat(s.replace(',', '.'));
  return isNaN(n) ? 0 : n;
}

function curSymbol(c: BuyCurrency): string {
  if (c === 'TRY') return '₺';
  if (c === 'USD') return '$';
  return c; // USDT / USDC
}

export function AddHoldingScreen({
  currentUsdTry,
  onAdd,
  onClose,
}: {
  currentUsdTry: number | null;
  onAdd: (h: Holding) => void;
  onClose: () => void;
}) {
  const [type, setType] = useState<AssetType>('crypto');
  const [selectedCoin, setSelectedCoin] = useState<CoinOption | null>(COINS[0]);
  const [symbol, setSymbol] = useState('');
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('');
  const [buyPrice, setBuyPrice] = useState('');
  const [buyCurrency, setBuyCurrency] = useState<BuyCurrency>('TRY');
  const [manualPrice, setManualPrice] = useState('');
  const [buyDate, setBuyDate] = useState(todayISO());
  const [error, setError] = useState('');

  const isCrypto = type === 'crypto';

  function submit() {
    const qty = parseNum(quantity);
    const bp = parseNum(buyPrice);

    let sym = symbol.trim().toUpperCase();
    let nm = name.trim();
    let cgId: string | undefined;

    if (isCrypto) {
      if (!selectedCoin) {
        setError('Coin seç');
        return;
      }
      sym = selectedCoin.symbol;
      nm = selectedCoin.name;
      cgId = selectedCoin.coingeckoId;
    } else if (!sym) {
      setError('Sembol gir (örn. THYAO, GRAM ALTIN)');
      return;
    }

    if (qty <= 0) {
      setError('Adet 0’dan büyük olmalı');
      return;
    }
    if (bp <= 0) {
      setError('Alış fiyatı 0’dan büyük olmalı');
      return;
    }

    const holding: Holding = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      type,
      symbol: sym,
      name: nm || sym,
      quantity: qty,
      buyPrice: bp,
      buyCurrency,
      // Alış anındaki USD/TRY kuru saklanır (TL↔USD çevirisi için).
      buyUsdTry: currentUsdTry ?? undefined,
      buyDate,
      manualPrice: isCrypto ? undefined : parseNum(manualPrice) || bp,
      coingeckoId: cgId,
    };
    onAdd(holding);
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={onClose} hitSlop={8}>
          <Text style={styles.cancel}>İptal</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Varlık Ekle</Text>
        <TouchableOpacity onPress={submit} hitSlop={8}>
          <Text style={styles.save}>Kaydet</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Text style={styles.fieldLabel}>Tür</Text>
        <View style={styles.chips}>
          {TYPES.map((t) => (
            <TouchableOpacity
              key={t}
              onPress={() => setType(t)}
              style={[styles.chip, type === t && styles.chipActive]}
            >
              <Text style={[styles.chipText, type === t && styles.chipTextActive]}>
                {assetMeta[t].label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {isCrypto ? (
          <>
            <Text style={styles.fieldLabel}>Coin</Text>
            <CoinSearch selected={selectedCoin} onSelect={setSelectedCoin} />
          </>
        ) : (
          <>
            <Text style={styles.fieldLabel}>Sembol</Text>
            <TextInput
              style={styles.input}
              placeholder="THYAO, GRAM ALTIN, EUR…"
              placeholderTextColor={colors.textDim}
              value={symbol}
              onChangeText={setSymbol}
              autoCapitalize="characters"
            />
            <Text style={styles.fieldLabel}>Ad (opsiyonel)</Text>
            <TextInput
              style={styles.input}
              placeholder="Türk Hava Yolları…"
              placeholderTextColor={colors.textDim}
              value={name}
              onChangeText={setName}
            />
          </>
        )}

        <Text style={styles.fieldLabel}>Hangi parayla aldın?</Text>
        <View style={styles.chips}>
          {CURRENCIES.map((c) => (
            <TouchableOpacity
              key={c.value}
              onPress={() => setBuyCurrency(c.value)}
              style={[styles.chip, buyCurrency === c.value && styles.chipActive]}
            >
              <Text
                style={[
                  styles.chipText,
                  buyCurrency === c.value && styles.chipTextActive,
                ]}
              >
                {c.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={styles.fieldLabel}>Adet / Miktar</Text>
        <TextInput
          style={styles.input}
          placeholder="0"
          placeholderTextColor={colors.textDim}
          value={quantity}
          onChangeText={setQuantity}
          keyboardType="decimal-pad"
        />

        <Text style={styles.fieldLabel}>
          Birim Alış Fiyatı ({curSymbol(buyCurrency)})
        </Text>
        <TextInput
          style={styles.input}
          placeholder="0"
          placeholderTextColor={colors.textDim}
          value={buyPrice}
          onChangeText={setBuyPrice}
          keyboardType="decimal-pad"
        />

        {!isCrypto && (
          <>
            <Text style={styles.fieldLabel}>
              Güncel Birim Fiyat ({curSymbol(buyCurrency)})
            </Text>
            <TextInput
              style={styles.input}
              placeholder="Boş bırakılırsa alış fiyatı kullanılır"
              placeholderTextColor={colors.textDim}
              value={manualPrice}
              onChangeText={setManualPrice}
              keyboardType="decimal-pad"
            />
            <Text style={styles.hint}>
              Kripto dışı varlıkların fiyatı şimdilik elle güncellenir.
            </Text>
          </>
        )}

        <Text style={styles.fieldLabel}>Alış Tarihi (YYYY-AA-GG)</Text>
        <TextInput
          style={styles.input}
          placeholder={todayISO()}
          placeholderTextColor={colors.textDim}
          value={buyDate}
          onChangeText={setBuyDate}
          autoCapitalize="none"
        />
        <Text style={styles.hint}>Reel getiri hesabı bu tarihi kullanır.</Text>

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
