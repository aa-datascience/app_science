import { useState } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from "react-native";

import { Button } from "../components/ui";
import { configured, supabase } from "../lib/supabase";
import { colors, serif, space } from "../lib/theme";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function signIn() {
    setBusy(true);
    setError("");
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (error) setError(error.message);
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.wrap}>
      <View style={styles.box}>
        <Text style={styles.title}>arXiv Digest</Text>
        <Text style={styles.sub}>One edition a day. Then it ends.</Text>
        {!configured && <Text style={styles.error}>Missing Supabase settings: see app/.env.example.</Text>}
        <TextInput
          style={styles.input}
          placeholder="Email"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />
        <TextInput
          style={styles.input}
          placeholder="Password"
          placeholderTextColor={colors.muted}
          secureTextEntry
          autoComplete="current-password"
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={signIn}
        />
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <Button label={busy ? "Signing in…" : "Sign in"} onPress={signIn} disabled={busy || !email || !password} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background, justifyContent: "center", padding: space.xl },
  box: { gap: space.md, maxWidth: 420, width: "100%", alignSelf: "center" },
  title: { ...serif, color: colors.text, fontSize: 34 },
  sub: { color: colors.muted, fontSize: 15, marginBottom: space.lg },
  input: {
    color: colors.text,
    fontSize: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 4,
    paddingHorizontal: space.md,
    paddingVertical: 12,
  },
  error: { color: colors.accent, fontSize: 14 },
});
