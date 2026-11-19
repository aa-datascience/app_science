// Widget d'écran d'accueil (Android). Version web : src/widget/index.web.ts, sans effet.
//
// Deux chemins de mise à jour :
// - depuis l'app, `updateWidget(state)` à chaque changement de lecture (carte ouverte, édition terminée) ;
// - sans l'app, le gestionnaire en arrière-plan : à l'ajout du widget, puis toutes les heures
//   (updatePeriodMillis dans app.json), il relit la base, ou le cache du téléphone hors ligne.

import { registerWidgetTaskHandler, requestWidgetUpdate, type WidgetTaskHandler } from "react-native-android-widget";

import { loadState, loadWidgetDays } from "../lib/data";
import { widgetData } from "../lib/logic";
import type { ReadingState } from "../lib/types";
import { StreakWidget } from "./StreakWidget";

export const WIDGET_NAME = "Streak";

async function render(local?: ReadingState | null) {
  const days = await loadWidgetDays();
  const data = days.length ? widgetData(days, local ?? (await loadState())) : null;
  return <StreakWidget data={data} />;
}

const handler: WidgetTaskHandler = async ({ widgetAction, renderWidget }) => {
  if (widgetAction === "WIDGET_DELETED" || widgetAction === "WIDGET_CLICK") return;
  renderWidget(await render());
};

export function registerWidget(): void {
  registerWidgetTaskHandler(handler);
}

export async function updateWidget(local: ReadingState): Promise<void> {
  try {
    await requestWidgetUpdate({ widgetName: WIDGET_NAME, renderWidget: () => render(local) });
  } catch {
    // Pas de widget posé, ou module natif absent (Expo Go) : rien à faire.
  }
}
