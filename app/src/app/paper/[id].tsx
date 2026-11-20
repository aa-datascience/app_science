// Vue profondeur : explication (bascule Curious / Physicist), contexte, concepts et questions (V2, étape 4), article original. À la première ouverture, le détail est
// généré : état de chargement. « Regenerate » le refait à la demande (appel payant).
// Les affirmations sourcées ne sont pas affichées (illisibles, demande d'Antoine du 20 novembre) :
// elles servent seulement à la vérification des citations, donc au badge « Quotes found ».

import { router, useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

import { FigureImage, FigureViewer } from "../../components/Figure";
import { QuestionBlock } from "../../components/Questions";
import { Button, Label, MathText, Toggle } from "../../components/ui";
import { cachedNotebook, type DetailResult, loadDetail, loadLearning, recordAttempt, regenerateDetail } from "../../lib/data";
import { figuresFor, lastAttempts } from "../../lib/logic";
import { useApp } from "../../lib/session";
import { colors, serif, space } from "../../lib/theme";
import type { FigureImage as Img, Learning } from "../../lib/types";

export default function Paper() {
  // `title` : passé par la fiche d'un concept, pour un article qui n'est ni du jour ni au carnet.
  const { id, title: titleParam } = useLocalSearchParams<{ id: string; title?: string }>();
  const { cards, figures, refreshFigures, opened } = useApp();
  const [viewing, setViewing] = useState<Img | null>(null);
  const card = cards.find((c) => c.arxiv_id === id);
  // Article ouvert depuis le carnet, hors de l'édition du jour : titres lus dans le carnet.
  const [saved, setSaved] = useState<{ plain: string | null; title: string } | null>(null);
  useEffect(() => {
    if (card) return;
    cachedNotebook().then((all) => {
      const e = all.find((x) => x.paper_id === id);
      setSaved(e ? { plain: e.plain_title, title: e.title } : null);
    });
  }, [id, card]);
  const plainTitle = card?.card.plain_title ?? saved?.plain;
  const title = card?.title ?? saved?.title ?? titleParam;
  const [result, setResult] = useState<DetailResult | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [level, setLevel] = useState<"lay" | "expert">("lay");
  const [learning, setLearning] = useState<Learning | null>(null);
  const [regen, setRegen] = useState<"idle" | "confirm" | "running" | string>("idle");

  useEffect(() => {
    let alive = true;
    setResult(null);
    loadDetail(id).then((r) => {
      if (!alive) return;
      setResult(r);
      if (r.ok) {
        opened(id); // « lu » = la vue profondeur a réellement été affichée
        void refreshFigures(id); // le détail vient peut-être de choisir ses figures
        loadLearning(id).then((l) => alive && setLearning(l));
      }
    });
    return () => {
      alive = false;
    };
  }, [id, attempt, opened, refreshFigures]);

  const openOriginal = () => WebBrowser.openBrowserAsync(`https://arxiv.org/abs/${id}`);

  const answer = (questionId: number) => (text: string, correct: boolean | null) => {
    const attempt = { question_id: questionId, answer: text, correct, created_at: new Date().toISOString() };
    setLearning((l) => (l ? { ...l, attempts: [...l.attempts, attempt] } : l));
    void recordAttempt(id, attempt);
  };

  const regenerate = async () => {
    if (regen !== "confirm") return setRegen("confirm");
    setRegen("running");
    const r = await regenerateDetail(id);
    if (!r.ok) {
      setRegen(r.reason === "budget" ? "This month's budget is used up." : r.reason === "offline" ? "You seem to be offline." : "Regeneration failed.");
      return;
    }
    setResult(r);
    setLearning(await loadLearning(id));
    void refreshFigures(id);
    setRegen("idle");
  };
  const last = lastAttempts(learning?.attempts ?? []);
  const nothingLearned = learning !== null && !learning.concepts.length && !learning.questions.length;
  const detailFigures = result?.ok ? figuresFor(figures[id] ?? [], result.detail.detail.figures).detail : [];

  return (
    <ScrollView style={styles.wrap} contentContainerStyle={styles.content}>
      {plainTitle ? <MathText text={plainTitle} size={24} style={{ lineHeight: 32 }} /> : null}
      {title ? <Text style={styles.original}>{title}</Text> : null}

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

          {detailFigures.length > 0 && (
            <View style={styles.section}>
              <Label>Figures</Label>
              {detailFigures.map((f) => (
                <View key={f.label} style={styles.figure}>
                  {f.images.map((image) => (
                    <FigureImage key={image.cacheKey} image={image} onPress={() => setViewing(image)} />
                  ))}
                  <Text style={styles.figureLabel}>Fig. {f.label}</Text>
                  {f.what_to_look_at ? <MathText text={f.what_to_look_at} size={16} /> : null}
                  <MathText text={f.caption} size={14} style={{ color: colors.muted }} />
                </View>
              ))}
            </View>
          )}

          <View style={styles.section}>
            <Label>Before this paper</Label>
            <MathText text={result.detail.detail.context.before} size={16} />
            <Label>What it changes</Label>
            <MathText text={result.detail.detail.context.change} size={16} />
            <Label>Limitations</Label>
            <MathText text={result.detail.detail.context.limitations} size={16} />
          </View>

          {learning && learning.concepts.length > 0 && (
            <View style={styles.section}>
              <Label>Concepts</Label>
              <View style={styles.pills}>
                {learning.concepts.map((c) => (
                  <Toggle key={c.id} label={c.name} active={false} onPress={() => router.push(`/concept/${c.id}`)} />
                ))}
              </View>
            </View>
          )}

          {learning && learning.questions.length > 0 && (
            <View style={styles.section}>
              <Label>Questions</Label>
              {learning.questions.map((q) => (
                <QuestionBlock key={q.id} q={q} last={last[q.id]} onAnswer={answer(q.id)} />
              ))}
            </View>
          )}

          <View style={styles.section}>
            {nothingLearned && (
              <Text style={styles.muted}>
                This explanation was written before concepts and questions existed. Regenerate it to get them.
              </Text>
            )}
            {regen === "running" ? (
              <View style={styles.regenerating}>
                <ActivityIndicator color={colors.muted} />
                <Text style={styles.muted}>Rewriting the explanation from the full text…</Text>
              </View>
            ) : (
              <Button
                label={regen === "confirm" ? "Tap again to regenerate (about $0.01)" : "Regenerate this explanation"}
                kind="quiet"
                onPress={regenerate}
              />
            )}
            {regen !== "idle" && regen !== "confirm" && regen !== "running" && <Text style={styles.muted}>{regen}</Text>}
          </View>
        </>
      )}

      <Button label="Original paper on arXiv" kind="quiet" onPress={openOriginal} />
      <FigureViewer image={viewing} onClose={() => setViewing(null)} />
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
  figure: { gap: space.sm, marginBottom: space.lg },
  figureLabel: { color: colors.accent, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  regenerating: { flexDirection: "row", alignItems: "center", gap: space.sm },
  state: { gap: space.sm, paddingVertical: space.xl },
  stateTitle: { ...serif, color: colors.text, fontSize: 20 },
  muted: { color: colors.muted, fontSize: 14, lineHeight: 21 },
});
