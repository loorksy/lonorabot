// biome-ignore-all lint/suspicious/noArrayIndexKey: Stateless text tokens have positional identity within a server message.
// Native, selectable message typography. Links open only on explicit user action.
import { Linking, Platform, Text, View } from "react-native";
import { useSession } from "../lib/session";
import type { NativeVisualPalette } from "./native-rich-theme";
import { colors } from "./ui";

function Inline({
  value,
  onChartLink,
  palette,
}: {
  value: string;
  onChartLink?: (url: string) => boolean;
  palette?: NativeVisualPalette;
}) {
  const ink = palette ? { ...colors, link: palette.link, accent: palette.accent } : colors;
  return (
    <>
      {value
        .split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((?:https?:\/\/|\/charts\?)[^\s)]+\))/g)
        .map((part, index) => {
          const link = /^\[([^\]]+)\]\(((?:https?:\/\/|\/charts\?)[^\s)]+)\)$/.exec(part);
          if (link)
            return (
              <Text
                key={index}
                accessibilityRole="link"
                style={{ color: ink.link }}
                onPress={() => {
                  if (!onChartLink?.(link[2])) void Linking.openURL(link[2]).catch(() => undefined);
                }}
              >
                {link[1]}
              </Text>
            );
          if (part.startsWith("**") && part.endsWith("**"))
            return (
              <Text key={index} style={{ fontWeight: "600" }}>
                {part.slice(2, -2)}
              </Text>
            );
          if (part.startsWith("`") && part.endsWith("`"))
            return (
              <Text
                key={index}
                style={{
                  fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
                  backgroundColor: ink.accent,
                  fontSize: 14,
                }}
              >
                {part.slice(1, -1)}
              </Text>
            );
          return <Text key={index}>{part}</Text>;
        })}
    </>
  );
}
export function Markdown({
  content,
  onChartLink,
  palette,
}: {
  content: string;
  onChartLink?: (url: string) => boolean;
  palette?: NativeVisualPalette;
}) {
  const { rtl } = useSession();
  const ink = palette
    ? {
        ...colors,
        foreground: palette.foreground,
        secondary: palette["muted-foreground"],
        muted: palette.muted,
      }
    : colors;
  const blocks = content.split(/(```[^\n]*\n[\s\S]*?```)/g).filter(Boolean);
  return (
    <View style={{ gap: 8 }}>
      {blocks.map((block, index) => {
        if (block.startsWith("```")) {
          const firstLine = block.indexOf("\n");
          return (
            <View
              key={index}
              style={{ borderRadius: 12, padding: 14, backgroundColor: ink.muted, gap: 8 }}
            >
              <Text style={{ color: ink.secondary, fontSize: 12 }}>
                {block.slice(3, firstLine)}
              </Text>
              <Text
                selectable
                style={{
                  fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
                  fontSize: 13,
                  lineHeight: 20,
                  color: ink.foreground,
                  writingDirection: "ltr",
                }}
              >
                {block.slice(firstLine + 1, -3)}
              </Text>
            </View>
          );
        }
        return (
          <View key={index} style={{ gap: 5 }}>
            {block
              .trim()
              .split("\n")
              .map((line, lineIndex) => {
                const heading = /^(#{1,3})\s+(.+)$/.exec(line);
                const value = heading ? heading[2] : line.replace(/^\s*[-*]\s+/, "• ");
                return (
                  <Text
                    key={lineIndex}
                    selectable
                    style={{
                      color: ink.foreground,
                      fontSize: heading ? 19 : 16,
                      lineHeight: heading ? 28 : 25,
                      fontWeight: heading ? "600" : "400",
                      writingDirection: "auto",
                      textAlign: rtl ? "right" : "left",
                    }}
                  >
                    <Inline value={value} onChartLink={onChartLink} palette={palette} />
                  </Text>
                );
              })}
          </View>
        );
      })}
    </View>
  );
}
