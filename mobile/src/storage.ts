import AsyncStorage from '@react-native-async-storage/async-storage';
import { Holding, Settings } from './types';

const HOLDINGS_KEY = '@portfolio/holdings';
const SETTINGS_KEY = '@portfolio/settings';

export const DEFAULT_SETTINGS: Settings = {
  // Türkiye için başlangıç değeri — kullanıcı Ayarlar'dan günceller.
  annualInflation: 45,
  // Varsayılan görüntü para birimi.
  displayCurrency: 'TRY',
};

export async function loadHoldings(): Promise<Holding[]> {
  try {
    const raw = await AsyncStorage.getItem(HOLDINGS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Geriye dönük uyum: eski kayıtlarda buyCurrency yoksa TL varsay.
    return parsed.map((h: Holding) => ({
      ...h,
      buyCurrency: h.buyCurrency ?? 'TRY',
    }));
  } catch {
    return [];
  }
}

export async function saveHoldings(holdings: Holding[]): Promise<void> {
  try {
    await AsyncStorage.setItem(HOLDINGS_KEY, JSON.stringify(holdings));
  } catch {
    // sessizce geç — MVP
  }
}

export async function loadSettings(): Promise<Settings> {
  try {
    const raw = await AsyncStorage.getItem(SETTINGS_KEY);
    if (!raw) return DEFAULT_SETTINGS;
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export async function saveSettings(settings: Settings): Promise<void> {
  try {
    await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // sessizce geç
  }
}
