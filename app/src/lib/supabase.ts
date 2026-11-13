import "react-native-url-polyfill/auto";

import AsyncStorage from "@react-native-async-storage/async-storage";
import { createClient } from "@supabase/supabase-js";

// Clé PUBLIQUE uniquement : tout accès est filtré en base par les règles RLS (compte propriétaire).
const url = process.env.EXPO_PUBLIC_SUPABASE_URL ?? "";
const key = process.env.EXPO_PUBLIC_SUPABASE_KEY ?? "";

export const configured = Boolean(url && key);

export const supabase = createClient(url || "https://missing.invalid", key || "missing", {
  auth: {
    storage: AsyncStorage,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});
