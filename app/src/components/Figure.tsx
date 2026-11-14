// Figures d'un article : vignette qui s'ouvre en plein écran, avec zoom.
// Les images sont mises en cache sur le téléphone (clé stable), donc lisibles hors ligne une fois vues.

import { Image } from "expo-image";
import { useMemo, useRef, useState } from "react";
import {
  Animated,
  Modal,
  PanResponder,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";

import { colors, space } from "../lib/theme";
import type { FigureImage as Img } from "../lib/types";

/** Une image de figure, sur fond blanc (les figures sont dessinées pour une page claire). */
export function FigureImage({ image, onPress }: { image: Img; onPress?: () => void }) {
  const [ratio, setRatio] = useState(1.6);
  return (
    <Pressable onPress={onPress} disabled={!onPress} accessibilityRole="imagebutton" accessibilityLabel="Open figure">
      <View style={styles.frame}>
        <Image
          source={{ uri: image.uri, cacheKey: image.cacheKey }}
          style={{ width: "100%", aspectRatio: ratio }}
          contentFit="contain"
          cachePolicy="disk"
          transition={150}
          onLoad={(e) => {
            const { width, height } = e.source;
            if (width > 0 && height > 0) setRatio(Math.max(0.5, Math.min(3, width / height)));
          }}
        />
      </View>
    </Pressable>
  );
}

/** Charge des images sans rien afficher, pour qu'elles soient en cache avant d'être hors ligne. */
export function Preload({ images }: { images: Img[] }) {
  return (
    <View style={styles.preload} pointerEvents="none">
      {images.map((image) => (
        <Image key={image.cacheKey} source={{ uri: image.uri, cacheKey: image.cacheKey }} style={styles.preloadItem} cachePolicy="disk" />
      ))}
    </View>
  );
}

const MAX_SCALE = 5;

/** Plein écran : pincer pour zoomer, glisser pour se déplacer, double appui pour basculer le zoom. */
export function FigureViewer({ image, onClose }: { image: Img | null; onClose: () => void }) {
  const { width, height } = useWindowDimensions();
  const scale = useRef(new Animated.Value(1)).current;
  const pan = useRef(new Animated.ValueXY()).current;
  const state = useRef({ scale: 1, x: 0, y: 0, startDist: 0, startScale: 1, lastTap: 0, moved: false });

  const reset = () => {
    state.current = { ...state.current, scale: 1, x: 0, y: 0 };
    scale.setValue(1);
    pan.setValue({ x: 0, y: 0 });
  };

  const responder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: () => {
          state.current.startDist = 0;
          state.current.moved = false;
        },
        onPanResponderMove: (e, g) => {
          const s = state.current;
          const t = e.nativeEvent.touches;
          if (t.length >= 2) {
            const dist = Math.hypot(t[0].pageX - t[1].pageX, t[0].pageY - t[1].pageY);
            if (!s.startDist) {
              s.startDist = dist;
              s.startScale = s.scale;
            }
            s.scale = Math.max(1, Math.min(MAX_SCALE, (s.startScale * dist) / s.startDist));
            s.moved = true;
            scale.setValue(s.scale);
          } else if (s.scale > 1) {
            if (Math.abs(g.dx) + Math.abs(g.dy) > 6) s.moved = true;
            pan.setValue({ x: s.x + g.dx, y: s.y + g.dy });
          }
        },
        onPanResponderRelease: (_e, g) => {
          const s = state.current;
          if (s.scale > 1 && !s.startDist) {
            s.x += g.dx;
            s.y += g.dy;
          }
          if (s.scale <= 1.02) reset();
          if (!s.moved) {
            const now = Date.now();
            if (now - s.lastTap < 300) {
              // Double appui : zoom x2,5 ou retour à la taille d'origine.
              if (s.scale > 1) reset();
              else {
                s.scale = 2.5;
                Animated.spring(scale, { toValue: 2.5, useNativeDriver: false }).start();
              }
              s.lastTap = 0;
            } else s.lastTap = now;
          }
        },
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  if (!image) return null;
  const close = () => {
    reset();
    onClose();
  };
  return (
    <Modal visible animationType="fade" onRequestClose={close} transparent={false} statusBarTranslucent>
      <View style={styles.viewer}>
        <Animated.View
          {...responder.panHandlers}
          style={{ width, height, transform: [{ translateX: pan.x }, { translateY: pan.y }, { scale }] }}
        >
          <Image
            source={{ uri: image.uri, cacheKey: image.cacheKey }}
            style={{ width, height }}
            contentFit="contain"
            cachePolicy="disk"
          />
        </Animated.View>
        <Pressable onPress={close} style={styles.close} hitSlop={16} accessibilityRole="button" accessibilityLabel="Close figure">
          <Text style={styles.closeLabel}>Close</Text>
        </Pressable>
        <Text style={styles.hint}>{Platform.OS === "web" ? "Double-click to zoom" : "Pinch or double-tap to zoom"}</Text>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  frame: { backgroundColor: "#ffffff", borderRadius: 4, padding: 6, overflow: "hidden" },
  preload: { position: "absolute", width: 1, height: 1, opacity: 0, overflow: "hidden" },
  preloadItem: { width: 1, height: 1 },
  viewer: { flex: 1, backgroundColor: "#ffffff", alignItems: "center", justifyContent: "center", overflow: "hidden" },
  close: {
    position: "absolute",
    top: 44,
    right: space.md,
    backgroundColor: colors.background,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 4,
  },
  closeLabel: { color: colors.text, fontSize: 15 },
  hint: { position: "absolute", bottom: 28, color: "#6b6b6b", fontSize: 13 },
});
