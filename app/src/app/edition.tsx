// Les cartes de l'édition : une carte par écran, glissement horizontal, progression toujours visible,
// puis l'écran de fin.

import { router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
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
import { Label, MathText, Tags, Toggle } from "../components/ui";
import { useApp } from "../lib/session";
import { colors, serif, space } from "../lib/theme";
import type { EditionCard, FeedbackType } from "../lib/types";

type Page = { key: string; card: EditionCard | null }; // card null = écran de fin

export default function Edition() {
  const { cards, state, shown, feedback, complete } = useApp();
  const { width } = useWindowDimensions();
  const list = useRef<FlatList<Page>>(null);
  const start = state.completed ? 0 : Math.min(state.index, Math.max(0, cards.length - 1));
  const [index, setIndex] = useState(start);
  const pages: Page[] = [...cards.map((card) => ({ key: card.arxiv_id, card })), { key: "end", card: null }];

  // Une carte est « montrée » quand elle est à l'écran ; l'écran de fin termine l'édition.
  useEffect(() => {
    const card = cards[index];
    if (card) shown(card.arxiv_id, index);
    else if (cards.length && index === cards.length) complete();
  }, [index, cards, shown, complete]);

  const onScrollEnd = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => setIndex(Math.round(e.nativeEvent.contentOffset.x / width)),
    [width],
  );

  const go = (i: number) => {
    const next = Math.max(0, Math.min(pages.length - 1, i));
    list.current?.scrollToOffset({ offset: next * width, animated: true });
    setIndex(next);
  };

  if (!cards.length) return <SafeAreaView style={styles.wrap} />;
  const onEnd = index >= cards.length;

  return (
    <SafeAreaView style={styles.wrap}>
      <View style={styles.top}>
        <Pressable onPress={() => router.back()} hitSlop={12} accessibilityRole="button" accessibilityLabel="Close">
          <Text style={styles.close}>Close</Text>
        </Pressable>
        <Text style={styles.count}>{onEnd ? "" : `${index + 1}/${cards.length}`}</Text>
      </View>
      <View style={styles.track}>
        <View style={[styles.fill, { width: `${(Math.min(index + 1, cards.length) / cards.length) * 100}%` }]} />
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
                given={state.feedback[item.card.arxiv_id] ?? []}
                onFeedback={(t) => feedback(item.card!.arxiv_id, t)}
              />
            ) : (
              <EndOfEdition cards={cards} state={state} />
            )}
          </View>
        )}
      />

      <View style={styles.nav}>
        <Pressable onPress={() => go(index - 1)} disabled={index === 0} hitSlop={12} accessibilityRole="button">
          <Text style={[styles.navLabel, index === 0 && { opacity: 0 }]}>‹ Back</Text>
        </Pressable>
        {onEnd ? (
          <Pressable onPress={() => router.back()} hitSlop={12} accessibilityRole="button">
            <Text style={styles.navLabel}>Done</Text>
          </Pressable>
        ) : (
          <Pressable onPress={() => go(index + 1)} hitSlop={12} accessibilityRole="button">
            <Text style={styles.navLabel}>{index === cards.length - 1 ? "Finish ›" : "Next ›"}</Text>
          </Pressable>
        )}
      </View>
    </SafeAreaView>
  );
}

function CardPage({
  card,
  given,
  onFeedback,
}: {
  card: EditionCard;
  given: FeedbackType[];
  onFeedback: (t: FeedbackType) => void;
}) {
  const c = card.card;
  const has = (t: FeedbackType) => given.includes(t);
  return (
    <ScrollView contentContainerStyle={styles.card}>
      {card.slot === "exploration" && <Text style={styles.badge}>Exploration · outside your usual fields</Text>}
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
});
