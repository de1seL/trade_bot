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
import { AssetType, Holding } from '../types';
import { colors, spacing, radius, assetMeta } from '../theme';
import { COINS } from '../prices/coins';

const TYPES: AssetType[] = ['crypto', 'stock', 'gold', 'fx', 'fund', 'cash'];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// Basit sayı ayrıştırma: hem "1,5" hem "1.5" kabul et.
function parseNum(s: string): number {
  const n = parseFloat(s.replace(',', '.'));
  return isNaN(n) ? 0 : n;
}

export function AddHoldingScreen({
  onAdd,
  onClose,
}: {
  onAdd: (h: Holding) => void;
  onClose: () => void;
}) {
  const [type, setType] = useState<AssetType>('crypto');
  const [coingeckoId, setCoingeckoId] = useState(COINS[0].coingeckoId);
  const [symbol, setSymbol] = useState('');
  const [name, setName] = useState('');
  const [quantity, setQuantity] = useState('');
  const [buyPrice, setBuyPrice] = useState('');
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
      const coin = COINS.find((c) => c.coingeckoId === coingeckoId);
      if (!coin) {
        setError('Coin seç');
        return;
      }
      sym = coin.symbol;
      nm = coin.name;
      cgId = coin.coingeckoId;
    } else if (!sym) {
      setError('Sembol gir (örn. THYAO, GRAM ALTIN, USD)');
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
            <View style={styles.chips}>
              {COINS.map((c) => (
                <TouchableOpacity
                  key={c.coingeckoId}
                  onPress={() => setCoingeckoId(c.coingeckoId)}
                  style={[
                    styles.chip,
                    coingeckoId === c.coingeckoId && styles.chipActive,
                  ]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      coingeckoId === c.coingeckoId && styles.chipTextActive,
                    ]}
                  >
                    {c.symbol}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </>
        ) : (
          <>
            <Text style={styles.fieldLabel}>Sembol</Text>
            <TextInput
              style={styles.input}
              placeholder="THYAO, GRAM ALTIN, USD…"
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

        <Text style={styles.fieldLabel}>Adet / Miktar</Text>
        <TextInput
          style={styles.input}
          placeholder="0"
          placeholderTextColor={colors.textDim}
          value={quantity}
          onChangeText={setQuantity}
          keyboardType="decimal-pad"
        />

        <Text style={styles.fieldLabel}>Birim Alış Fiyatı (₺)</Text>
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
            <Text style={styles.fieldLabel}>Güncel Birim Fiyat (₺)</Text>
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
