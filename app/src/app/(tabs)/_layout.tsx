import { Tabs } from "expo-router";

import { colors } from "../../lib/theme";

// Today, Notebook, Concepts, Stats, Settings (spec §7).
export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.background },
        tabBarStyle: { backgroundColor: colors.background, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.text,
        tabBarInactiveTintColor: colors.muted,
        // Pas d'icônes : libellés seuls. Avec cinq onglets, la place est comptée sur un téléphone :
        // aucune marge réservée à une icône, taille fixe (indépendante de la police système).
        tabBarIcon: () => null,
        tabBarIconStyle: { display: "none" },
        tabBarLabelPosition: "below-icon",
        tabBarAllowFontScaling: false,
        tabBarLabelStyle: { fontSize: 12, marginLeft: 0, marginTop: 0, paddingHorizontal: 0 },
        tabBarItemStyle: { paddingHorizontal: 0, justifyContent: "center" },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "Today" }} />
      <Tabs.Screen name="notebook" options={{ title: "Notebook" }} />
      <Tabs.Screen name="concepts" options={{ title: "Concepts" }} />
      <Tabs.Screen name="stats" options={{ title: "Stats" }} />
      <Tabs.Screen name="settings" options={{ title: "Settings" }} />
    </Tabs>
  );
}
