// Notifications push : autorisation, jeton Expo, enregistrement dans profile.push_token.
// L'envoi est fait par le pipeline (GitHub Actions) : une le matin, un rappel le soir, rien d'autre.
//
// Ne fonctionne que dans l'APK : Expo Go sur Android ne reçoit plus de notifications distantes.

import Constants, { ExecutionEnvironment } from "expo-constants";
import { Platform } from "react-native";

import { supabase } from "./supabase";

export type PushState =
  | { state: "enabled" }
  | { state: "denied" } // l'utilisateur a refusé l'autorisation
  | { state: "unsupported"; reason: string } // Expo Go, navigateur
  | { state: "error"; message: string };

/**
 * Enregistre ce téléphone pour les notifications. `ask` : demander l'autorisation si elle
 * n'a pas encore été donnée (sinon on se contente de constater).
 */
export async function registerPush(ask: boolean): Promise<PushState> {
  if (Platform.OS === "web") return { state: "unsupported", reason: "Not available in a browser." };
  if (Constants.executionEnvironment === ExecutionEnvironment.StoreClient) {
    return { state: "unsupported", reason: "Not available in Expo Go: install the app build." };
  }
  try {
    // Chargé à la demande : le module se plaint dès l'import dans Expo Go.
    const Notifications = await import("expo-notifications");

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "Daily edition",
        importance: Notifications.AndroidImportance.DEFAULT,
      });
    }
    let { status } = await Notifications.getPermissionsAsync();
    if (status !== "granted" && ask) status = (await Notifications.requestPermissionsAsync()).status;
    if (status !== "granted") return { state: "denied" };

    const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
    if (!projectId) return { state: "error", message: "Expo project id missing from the app config." };
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;

    const { error } = await supabase
      .from("profile")
      .update({ push_token: token, updated_at: new Date().toISOString() })
      .eq("id", 1);
    if (error) return { state: "error", message: error.message };
    return { state: "enabled" };
  } catch (e) {
    return { state: "error", message: e instanceof Error ? e.message : String(e) };
  }
}

/** Une notification reçue pendant que l'app est ouverte s'affiche quand même, sans son ni pastille. */
export async function configureForeground(): Promise<void> {
  if (Platform.OS === "web" || Constants.executionEnvironment === ExecutionEnvironment.StoreClient) return;
  const Notifications = await import("expo-notifications");
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldPlaySound: false,
      shouldSetBadge: false,
      shouldShowBanner: true,
      shouldShowList: true,
    }),
  });
}
