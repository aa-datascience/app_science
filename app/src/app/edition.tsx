// Les cartes de l'édition : une carte par écran, glissement horizontal, progression toujours visible,
// puis l'écran de fin. Le lundi, le bilan de la semaine passée précède la première carte.

import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AppState,
  FlatList,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { EndOfEdition } from "../components/EndOfEdition";
import { FigureImage, FigureViewer } from "../components/Figure";
import { Label, MathText, Tags, Toggle } from "../components/ui";
import { figuresFor, percent, shortDate } from "../lib/logic";
import { useApp } from "../lib/session";
import { colors, serif, space } from "../lib/theme";
import type { EditionCard, FeedbackType, FigureImage as Img, PaperFigure, WeekSummary } from "../lib/types";

type Page = { key: string; card: EditionCard | null }; // card null = bilan du lundi (clé « summary ») ou écran de fin
const MIN_VIEW_MS = 300; // en dessous, la carte n'a fait que défiler
const MAX_VIEW_MS = 10 * 60 * 1000;

export default function Edition() {
  const { cards, figures, state, summary, shown, viewed, feedback, complete } = useApp();
  const [viewing, setViewing] = useState<Img | null>(null);
  const { width } = useWindowDimensions();
  const list = useRef<FlatList<Page>>(null);
  // Le bilan est figé à l'ouverture de l'écran : une page qui apparaîtrait en cours de lecture décalerait tout.
  const [lead] = useState<WeekSummary | null>(summary);
  const offset = lead ? 1 : 0;
  const fresh = !state.completed && state.shown.length === 0;
  const start = fresh ? 0 : offset + (state.completed ? 0 : Math.min(state.index, Math.max(0, cards.length - 1)));
  const [page, setPage] = useState(start);
  const index = page - offset; // position dans les cartes : -1 sur le bilan, cards.length sur l'écran de fin
  const pages: Page[] = [
    ...(lead ? [{ key: "summary", card: null }] : []),
    ...cards.map((card) => ({ key: card.arxiv_id, card })),
    { key: "end", card: null },
  ];

  // Une carte est « montrée » quand elle est à l'écran ; l'écran de fin termine l'édition.
  useEffect(() => {
    const card = cards[index];
    if (card) shown(card.arxiv_id, index);
    else if (cards.length && index === cards.length) complete();
  }, [index, cards, shown, complete]);

  // Temps passé sur chaque carte, envoyé quand elle quitte l'écran : une carte passée en moins de
  // deux secondes ne compte pas comme « ignorée » dans le profil appris.
  const currentId = cards[index]?.arxiv_id ?? null;
  const dwell = useRef<{ id: string | null; since: number | null }>({ id: null, since: null });
  const flushDwell = useCallback(() => {
    const d = dwell.current;
    if (d.id && d.since) {
      const ms = Date.now() - d.since;
      if (ms >= MIN_VIEW_MS) viewed(d.id, Math.min(ms, MAX_VIEW_MS));
    }
    d.since = null;
  }, [viewed]);
  useEffect(() => {
    dwell.current = { id: currentId, since: currentId ? Date.now() : null };
    return flushDwell;
  }, [currentId, flushDwell]);
  useEffect(() => {
    // L'app en arrière-plan ne compte pas comme du temps de lecture.
    const sub = AppState.addEventListener("change", (next) => {
      if (next === "active") dwell.current.since = dwell.current.id ? Date.now() : null;
      else flushDwell();
    });
    return () => sub.remove();
  }, [flushDwell]);

  const onScrollEnd = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => setPage(Math.round(e.nativeEvent.contentOffset.x / width)),
    [width],
  );

  const go = (i: number) => {
    const next = Math.max(0, Math.min(pages.length - 1, i));
    list.current?.scrollToOffset({ offset: next * width, animated: true });
    setPage(next);
  };

  if (!cards.length) return <SafeAreaView style={styles.wrap} />;
  const onEnd = index >= cards.length;

  return (
    <SafeAreaView style={styles.wrap}>
      <View style={styles.top}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityRole="button" accessibilityLabel="Close">
          <Text style={styles.close}>Close</Text>
        </Pressable>
        <Text style={styles.count}>{onEnd ? "" : index < 0 ? "Last week" : `${index + 1}/${cards.length}`}</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${(Math.max(0, Math.min(index + 1, cards.length)) / cards.length) * 100}%` }]} />
      </View>

      <FlatList
        ref={list}
        data={pages}
        keyExtractor={(p) => p.key}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        initialScrollIndex={start}
        getItemLayout={(_, i) => ({ length: width, offset: width * i, index: i })}
        onMomentumScrollEnd={onScrollEnd}
        onScroll={onScrollEnd}
        scrollEventThrottle={64}
        renderItem={({ item }) => (
          <View style={{ width }}>
            {item.card ? (
              <CardPage
                card={item.card}
                figure={figuresFor(figures[item.card.arxiv_id] ?? []).card}
                onFigure={setViewing}
                given={state.feedback[item.card.arxiv_id] ?? []}
                onFeedback={(t) => feedback(item.card!.arxiv_id, t)}
              />
            ) : item.key === "summary" && lead ? (
              <WeekSummaryPage summary={lead} />
            ) : (
              <EndOfEdition cards={cards} state={state} />
            )}
          </View>
        )}
      />

      <FigureViewer image={viewing} onClose={() => setViewing(null)} />

      <View style={styles.nav}>
        <Pressable onPress={() => go(page - 1)} disabled={page === 0} hitSlop={12} accessibilityRole="button">
          <Text style={[styles.navLabel, page === 0 && { opacity: 0 }]}>‹ Back</Text>
        </Pressable>
        {onEnd ? (
          <Pressable onPress={() => router.back()} hitSlop={12} accessibilityRole="button">
            <Text style={styles.navLabel}>Done</Text>
          </Pressable>
        ) : (
          <Pressable onPress={() => go(page + 1)} hitSlop={12} accessibilityRole="button">
            <Text style={styles.navLabel}>{index < 0 ? "Start ›" : index === cards.length - 1 ? "Finish ›" : "Next ›"}</Text>
          </Pressable>
        )}
      </View>
    </SafeAreaView>
  );
}

/** Bilan de la semaine passée, en tête de l'édition du lundi. Des faits, pas de félicitations. */
function WeekSummaryPage({ summary: s }: { summary: WeekSummary }) {
  const rows: [string | number, string][] = [
    [s.read, "read"],
    [s.skipped, "skipped"],
    [s.saved, "saved"],
    [`${s.editions_completed}/7`, "editions finished"],
  ];
  return (
    <ScrollView contentContainerStyle={styles.card}>
      <Text style={styles.badge}>Week of {shortDate(s.week)}</Text>
      <Text style={styles.summaryTitle}>Last week</Text>
      <View style={styles.summaryRows}>
        {rows.map(([n, label]) => (
          <View key={label} style={styles.summaryRow}>
            <Text style={styles.summaryN}>{n}</Text>
            <Text style={styles.why}>{label}</Text>
          </View>
        ))}
      </View>
      <Text style={styles.why}>
        You opened {percent(s.shown ? s.read / s.shown : null)} of the {s.shown} papers shown.
        {s.most_read_category ? ` Most read: ${s.most_read_category}.` : ""}
        {s.most_skipped_category ? ` Most skipped: ${s.most_skipped_category}.` : ""}
      </Text>
    </ScrollView>
  );
}

function CardPage({
  card,
  figure,
  onFigure,
  given,
  onFeedback,
}: {
  card: EditionCard;
  figure: PaperFigure | null;
  onFigure: (image: Img) => void;
  given: FeedbackType[];
  onFeedback: (t: FeedbackType) => void;
}) {
  const c = card.card;
  const has = (t: FeedbackType) => given.includes(t);
  return (
    <ScrollView contentContainerStyle={styles.card}>
      {card.slot === "exploration" && <Text style={styles.badge}>Exploration · outside your usual fields</Text>}
      {figure ? <FigureImage image={figure.images[0]} onPress={() => onFigure(figure.images[0])} /> : null}
      <Pressable onPress={() => router.push(`/paper/${card.arxiv_id}`)} accessibilityRole="button" style={styles.body}>
        <MathText text={c.plain_title} size={25} style={styles.title} />
        <View>
          <Label>What they found</Label>
          <MathText text={c.finding} />
        </View>
        <View>
          <Label>Why it matters</Label>
          <MathText text={c.why_it_matters} />
        </View>
        <Tags items={c.tags} />
        {card.why ? (
          <View>
            <Label>Why this paper</Label>
            <Text style={styles.why}>{card.why}</Text>
          </View>
        ) : null}
        <Text style={styles.open}>Read the explanation →</Text>
      </Pressable>

      <View style={styles.feedback}>
        <Toggle label="Interesting" active={has("interesting")} onPress={() => onFeedback("interesting")} />
        <Toggle label="Not for me" active={has("not_interesting")} onPress={() => onFeedback("not_interesting")} />
        <Toggle label="Too easy" active={has("too_easy")} onPress={() => onFeedback("too_easy")} />
        <Toggle label="Too hard" active={has("too_hard")} onPress={() => onFeedback("too_hard")} />
        <Toggle label="Save" active={has("saved")} onPress={() => onFeedback("saved")} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: colors.background },
  top: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: space.lg, paddingVertical: space.sm },
  close: { color: colors.muted, fontSize: 15 },
  count: { color: colors.muted, fontSize: 15, fontVariant: ["tabular-nums"] },
  track: { height: 2, backgroundColor: colors.border, marginHorizontal: space.lg },
  fill: { height: 2, backgroundColor: colors.text },
  card: { padding: space.lg, paddingTop: space.xl, gap: space.lg, maxWidth: 640, width: "100%", alignSelf: "center" },
  body: { gap: space.lg },
  badge: { color: colors.accent, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  title: { lineHeight: 33 },
  why: { color: colors.muted, fontSize: 15, lineHeight: 22 },
  open: { color: colors.accent, fontSize: 15 },
  feedback: { flexDirection: "row", flexWrap: "wrap", gap: space.xs, paddingTop: space.md },
  nav: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: space.lg, paddingVertical: space.md },
  navLabel: { color: colors.muted, fontSize: 15 },
  summaryTitle: { ...serif, color: colors.text, fontSize: 34, lineHeight: 42 },
  summaryRows: { gap: space.sm, paddingVertical: space.md },
  summaryRow: { flexDirection: "row", alignItems: "baseline", gap: space.md },
  summaryN: { ...serif, color: colors.text, fontSize: 26, minWidth: 56, fontVariant: ["tabular-nums"] },
});
