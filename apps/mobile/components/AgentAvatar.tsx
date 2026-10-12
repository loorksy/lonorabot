// Modified from Tampletgrok apps/mobile/components/bot-avatar.tsx (Apache-2.0).
// Upstream attribution is preserved in NOTICE. Native dependency-heavy animation is omitted.
import { View } from "react-native";

export function AgentAvatar({
  color,
  size = 54,
  working = false,
  variant = "orb",
}: {
  color: string;
  size?: number;
  working?: boolean;
  variant?: string;
}) {
  const rounded = variant === "square" ? Math.round(size * 0.27) : size / 2;
  return (
    <View style={{ width: size, height: size }}>
      <View
        style={{
          width: size,
          height: size,
          borderRadius: rounded,
          backgroundColor: color,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <View
          style={{
            width: size * 0.68,
            height: size * 0.44,
            borderRadius: size * 0.23,
            backgroundColor: "#0C0C0E",
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "center",
            gap: size * 0.11,
          }}
        >
          {[0, 1].map((eye) => (
            <View
              key={eye}
              style={{
                width: Math.max(3, size * 0.11),
                height: Math.max(4, size * 0.17),
                borderRadius: size * 0.05,
                backgroundColor: "#fff",
              }}
            />
          ))}
        </View>
      </View>
      {working ? (
        <View
          style={{
            position: "absolute",
            right: 0,
            bottom: 0,
            width: Math.max(7, size * 0.18),
            height: Math.max(7, size * 0.18),
            borderRadius: size,
            backgroundColor: "#F5A03C",
          }}
        />
      ) : null}
    </View>
  );
}
