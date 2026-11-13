// Petits composants communs.

import { useMemo } from "react";
import { Pressable, StyleSheet, Text, type TextStyle, View, type ViewStyle } from "react-native";

import { buildMathHtml, hasMath } from "../lib/logic";
import { colors, serif, space } from "../lib/theme";
import { HtmlView } from "./HtmlView";

/** Texte qui peut contenir du LaTeX. Sans « $ », un simple Text ; sinon rendu par KaTeX. */
export function MathText({ text, size = 17, style }: { text: string; size?: number; style?: TextStyle }) {
  const html = useMemo(
    () => (hasMath(text) ? buildMathHtml(text, { text: colors.text, background: colors.background, muted: colors.muted }, size) : ""),
    [text, size],
  );
  if (!html) return <Text style={[styles.body, { fontSize: size, lineHeight: size * 1.6 }, style]}>{text}</Text>;
  return <HtmlView html={html} />;
}

export function Button({
  label,
  onPress,
  kind = "primary",
  disabled,
  style,
}: {
  label: string;
  onPress: () => void;
  kind?: "primary" | "quiet";
  disabled?: boolean;
  style?: ViewStyle;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        kind === "primary" ? styles.primary : styles.quiet,
        (pressed || disabled) && { opacity: 0.6 },
        style,
      ]}
    >
      <Text style={[styles.buttonLabel, kind === "primary" && { color: colors.background }]}>{label}</Text>
    </Pressable>
  );
}

/** Bouton à bascule discret, pour le feedback. */
export function Toggle({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={[styles.toggle, active && styles.toggleActive]}
    >
      <Text style={[styles.toggleLabel, active && { color: colors.background }]}>{label}</Text>
    </Pressable>
  );
}

export function Label({ children }: { children: string }) {
  return <Text style={styles.label}>{children}</Text>;
}

export function Tags({ items }: { items: string[] }) {
  return (
    <View style={styles.tags}>
      {items.map((t) => (
        <Text key={t} style={styles.tag}>
          {t}
        </Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  body: { ...serif, color: colors.text },
  button: { paddingVertical: 14, paddingHorizontal: space.lg, borderRadius: 4, alignItems: "center" },
  primary: { backgroundColor: colors.text },
  quiet: { borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  buttonLabel: { color: colors.text, fontSize: 16, letterSpacing: 0.3 },
  toggle: {
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 4,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  toggleActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  toggleLabel: { color: colors.muted, fontSize: 13 },
  label: { color: colors.muted, fontSize: 12, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: space.xs },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  tag: {
    color: colors.muted,
    fontSize: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 3,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
});
