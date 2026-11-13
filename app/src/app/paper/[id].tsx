// Vue profondeur : explication (bascule Curious / Physicist), contexte, affirmations sourcées,
// article original. À la première ouverture, le détail est généré : état de chargement.

import { useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, Label, MathText, Toggle } from "../../components/ui";
import { type DetailResult, loadDetail } from "../../lib/data";
import { useApp } from "../../lib/session";
import { colors, serif, space } from "../../lib/theme";

export default function Paper() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { cards, opened } = useApp();
  const card = cards.find((c) => c.arxiv_id === id);
  const [result, setResult] = useState<DetailResult | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [level, setLevel] = useState<"lay" | "expert">("lay");

  useEffect(() => {
    let alive = true;
    setResult(null);
    loadDetail(id).then((r) => {
      if (!alive) return;
      setResult(r);
      if (r.ok) opened(id); // « lu » = la vue profondeur a réellement été affichée
    });
    return () => {
      alive = false;
    };
  }, [id, attempt, opened]);

  const openOriginal = () => WebBrowser.openBrowserAsync(`https://arxiv.org/abs/${id}`);

  return (
    <ScrollView style={styles.wrap} contentContainerStyle={styles.content}>
      {card ? <MathText text={card.card.plain_title} size={24} style={{ lineHeight: 32 }} /> : null}
      {card ? <Text style={styles.original}>{card.title}</Text> : null}

      {result === null && (
        <View style={styles.state}>
          <ActivityIndicator color={colors.muted} />
          <Text style={styles.stateTitle}>Preparing this paper…</Text>
          <Text style={styles.muted}>
            The explanation is written from the full text the first time you open a paper. This takes up to a minute, once.
          </Text>
        </View>
      )}

      {result && !result.ok && (
        <View style={styles.state}>
          <Text style={styles.stateTitle}>
            {result.reason === "budget"
              ? "This month's budget is used up."
              : result.reason === "offline"
                ? "You seem to be offline."
                : "The explanation could not be prepared."}
          </Text>
          <Text style={styles.muted}>
            {result.reason === "budget"
              ? "No new explanation will be generated until next month. Papers you already opened stay available."
              : "You can try again, or read the original paper."}
            {result.message ? ` (${result.message})` : ""}
          </Text>
          {result.reason !== "budget" && <Button label="Try again" kind="quiet" onPress={() => setAttempt((n) => n + 1)} />}
        </View>
      )}

      {result?.ok && (
        <>
          <Text style={styles.badge}>
            {result.detail.verification_status === "verified" ? "Quotes found in the paper" : "Not verified"}
            {result.detail.based_on_abstract ? " · based on the abstract only" : ""}
          </Text>

          <View style={styles.section}>
            <View style={styles.switch}>
              <Toggle label="Curious" active={level === "lay"} onPress={() => setLevel("lay")} />
              <Toggle label="Physicist" active={level === "expert"} onPress={() => setLevel("expert")} />
            </View>
            <MathText
              text={level === "lay" ? result.detail.detail.explanation_lay : result.detail.detail.explanation_expert}
            />
          </View>

          <View style={styles.section}>
            <Label>Before this paper</Label>
            <MathText text={result.detail.detail.context.before} size={16} />
            <Label>What it changes</Label>
            <MathText text={result.detail.detail.context.change} size={16} />
            <Label>Limitations</Label>
            <MathText text={result.detail.detail.context.limitations} size={16} />
          </View>

          <View style={styles.section}>
            <Label>Sourced claims</Label>
            {result.detail.detail.claims.map((c, i) => (
              <View key={i} style={styles.claim}>
                <MathText text={c.statement} size={16} />
                <View style={styles.quote}>
                  <MathText text={c.quote} size={14} style={{ color: colors.muted }} />
                </View>
              </View>
            ))}
            {!result.detail.detail.claims.length && <Text style={styles.muted}>No claim could be matched to the paper.</Text>}
          </View>
        </>
      )}

      <Button label="Original paper on arXiv" kind="quiet" onPress={openOriginal} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  content: { padding: space.lg, gap: space.lg, maxWidth: 680, width: "100%", alignSelf: "center", paddingBottom: space.xl * 2 },
  original: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  badge: { color: colors.accent, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  section: { gap: space.sm, paddingTop: space.md, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  switch: { flexDirection: "row", gap: space.xs, marginBottom: space.sm },
  claim: { gap: space.xs, marginBottom: space.md },
  quote: { borderLeftWidth: 2, borderLeftColor: colors.border, paddingLeft: space.sm },
  state: { gap: space.sm, paddingVertical: space.xl },
  stateTitle: { ...serif, color: colors.text, fontSize: 20 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 21 },
});
