// Point d'entrée : Expo Router, plus le gestionnaire du widget d'écran d'accueil (Android),
// qui doit être enregistré hors de tout écran pour tourner app fermée.
import "expo-router/entry";

import { registerWidget } from "./src/widget";

registerWidget();
