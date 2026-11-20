// Questions de compréhension d'un article (V2, étape 4).
// QCM : un appui sur une option donne la correction. Réponse courte : « Show answer », puis le
// lecteur dit lui-même s'il avait bon. Chaque réponse est gardée (historique), hors ligne compris.

import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { isRightOption } from "../lib/logic";
import { colors, space } from "../lib/theme";
import type { Attempt, QuestionRow } from "../lib/types";
import { MathText, Toggle } from "./ui";

export function QuestionBlock({
  q,
  last,
  onAnswer,
}: {
  q: QuestionRow;
  last: Attempt | undefined;
  onAnswer: (answer: string, correct: boolean | null) => void;
}) {
  // Une question déjà répondue s'affiche corrigée ; « Try again » la repose.
  const [fresh, setFresh] = useState(false);
  const [revealed, setRevealed] = useState(false);
  const shown = fresh ? undefined : last;

  const reveal = (
    <View style={styles.reveal}>
      {q.kind === "short" && <MathText text={q.answer} size={16} />}
      {q.explanation ? <MathText text={q.explanation} size={15} style={{ color: colors.muted }} /> : null}
      <View style={styles.quote}>
        <MathText text={q.quote} size={14} style={{ color: colors.muted }} />
      </View>
    </View>
  );

  return (
    <View style={styles.wrap}>
      <MathText text={q.prompt} size={17} />

      {q.kind === "mcq" && (
        <View style={styles.options}>
          {q.options.map((o) => {
            const chosen = shown?.answer === o;
            const right = isRightOption(q, o);
            const mark = shown ? (right ? styles.right : chosen ? styles.wrong : null) : null;
            return (
              <Pressable
                key={o}
                accessibilityRole="button"
                disabled={Boolean(shown)}
                onPress={() => {
                  setFresh(false);
                  onAnswer(o, isRightOption(q, o));
                }}
                style={[styles.option, mark]}
              >
                <MathText text={o} size={15} />
              </Pressable>
            );
          })}
        </View>
      )}

      {q.kind === "mcq" && shown && (
        <>
          <Text style={[styles.verdict, { color: shown.correct ? colors.accent : colors.muted }]}>
            {shown.correct ? "Correct" : "Not quite"}
          </Text>
          {reveal}
        </>
      )}

      {q.kind === "short" && !shown && !revealed && (
        <View style={styles.row}>
          <Toggle label="Show answer" active={false} onPress={() => setRevealed(true)} />
        </View>
      )}
      {q.kind === "short" && (shown || revealed) && (
        <>
          {reveal}
          {shown ? (
            <Text style={styles.verdict}>{shown.correct ? "You had it" : "You did not have it"}</Text>
          ) : (
            <View style={styles.row}>
              <Toggle label="I had it" active={false} onPress={() => { setFresh(false); setRevealed(false); onAnswer("", true); }} />
              <Toggle label="I didn't" active={false} onPress={() => { setFresh(false); setRevealed(false); onAnswer("", false); }} />
            </View>
          )}
        </>
      )}

      {shown && (
        <Pressable accessibilityRole="button" onPress={() => { setFresh(true); setRevealed(false); }}>
          <Text style={styles.again}>Try again</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm, marginBottom: space.lg },
  options: { gap: space.xs },
  option: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 4,
    paddingHorizontal: space.md,
    paddingVertical: 10,
  },
  right: { borderColor: colors.accent, borderWidth: 1 },
  wrong: { opacity: 0.6 },
  verdict: { color: colors.muted, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  reveal: { gap: space.xs },
  quote: { borderLeftWidth: 2, borderLeftColor: colors.border, paddingLeft: space.sm },
  row: { flexDirection: "row", gap: space.xs },
  again: { color: colors.muted, fontSize: 13, textDecorationLine: "underline" },
});
