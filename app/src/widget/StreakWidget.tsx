// Widget d'écran d'accueil (Android) : série d'éditions terminées et articles lus par jour.
// Rendu par react-native-android-widget : ce ne sont pas des vues React Native, seulement
// FlexWidget et TextWidget, dessinés en vues Android natives.

import { FlexWidget, TextWidget } from "react-native-android-widget";

import { weekdayInitial } from "../lib/logic";
import type { WidgetData } from "../lib/types";

const C = {
  surface: "#17191c",
  text: "#e9e6df",
  muted: "#8e8c86",
  accent: "#c9b98a",
  track: "#2a2d32",
} as const;
const BAR_MAX = 34; // hauteur d'une barre pleine (toutes les cartes lues), en dp

function status(data: WidgetData): string {
  const t = data.today;
  if (!t) return "No edition yet";
  if (t.done) return `Today done · ${t.read} read`;
  return t.read ? `Today: ${t.read}/${t.size} read` : "Today's edition is waiting";
}

export function StreakWidget({ data }: { data: WidgetData | null }) {
  const days = data?.days ?? [];
  return (
    <FlexWidget
      clickAction="OPEN_APP"
      style={{
        height: "match_parent",
        width: "match_parent",
        backgroundColor: C.surface,
        borderRadius: 22,
        padding: 14,
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      <FlexWidget style={{ flexDirection: "row", alignItems: "center", width: "match_parent" }}>
        <TextWidget text={String(data?.streak ?? 0)} style={{ fontSize: 34, color: C.accent, fontFamily: "serif" }} />
        <FlexWidget style={{ flexDirection: "column", marginLeft: 10, flex: 1 }}>
          <TextWidget text="day streak" style={{ fontSize: 14, color: C.text }} />
          <TextWidget text={data ? status(data) : "Open the app once to load"} style={{ fontSize: 12, color: C.muted }} maxLines={1} />
        </FlexWidget>
      </FlexWidget>

      <FlexWidget style={{ flexDirection: "row", width: "match_parent", justifyContent: "space-between", alignItems: "flex-end" }}>
        {days.map((d) => {
          const h = d.size ? Math.max(3, Math.round((Math.min(d.read, d.size) / d.size) * BAR_MAX)) : 3;
          return (
            <FlexWidget key={d.date} style={{ flexDirection: "column", alignItems: "center", flex: 1 }}>
              <TextWidget text={d.read ? String(d.read) : ""} style={{ fontSize: 10, color: C.muted }} />
              <FlexWidget style={{ height: BAR_MAX, flexDirection: "column", justifyContent: "flex-end", marginTop: 2 }}>
                <FlexWidget style={{ width: 14, height: h, borderRadius: 4, backgroundColor: d.read ? C.accent : C.track }} />
              </FlexWidget>
              <TextWidget
                text={weekdayInitial(d.date)}
                style={{ fontSize: 10, color: d.done ? C.accent : C.muted, marginTop: 3, fontWeight: d.done ? "bold" : "normal" }}
              />
            </FlexWidget>
          );
        })}
      </FlexWidget>
    </FlexWidget>
  );
}
