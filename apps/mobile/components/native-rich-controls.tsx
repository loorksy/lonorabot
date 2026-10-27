import type { VisualNode, VisualScalar } from "@lonora/contracts";
import { parseVisualNumberDraft } from "@lonora/core";
import { visual } from "@lonora/ui-tokens";
import { useEffect, useRef, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import type { NativeVisualPalette } from "./native-rich-theme";

type Props = {
  node: VisualNode;
  value: VisualScalar;
  palette: NativeVisualPalette;
  rtl: boolean;
  onChange: (value: VisualScalar) => void;
};

export function NativeVisualInput({ node, value, palette, rtl, onChange }: Props) {
  const [draft, setDraft] = useState(String(value ?? ""));
  const focused = useRef(false);
  useEffect(() => {
    if (!focused.current) setDraft(String(value ?? ""));
  }, [value]);
  return (
    <View style={{ gap: visual.space.small }}>
      {node.label ? (
        <Text
          style={{
            color: palette.foreground,
            fontSize: visual.font.label,
            textAlign: rtl ? "right" : "left",
          }}
        >
          {node.label}
        </Text>
      ) : null}
      <TextInput
        accessibilityLabel={node.label ?? node.id}
        value={draft}
        maxLength={1000}
        keyboardType={node.input_kind === "number" ? "decimal-pad" : "default"}
        onFocus={() => {
          focused.current = true;
        }}
        onBlur={() => {
          focused.current = false;
          if (node.input_kind !== "number") return;
          const parsed = parseVisualNumberDraft(draft);
          if (parsed === undefined) setDraft(String(value ?? ""));
          else if (parsed === null) {
            onChange(null);
            setDraft("");
          } else {
            const bounded = Math.max(node.minimum ?? 0, Math.min(node.maximum ?? 100, parsed));
            onChange(bounded);
            setDraft(String(bounded));
          }
        }}
        onChangeText={(next) => {
          setDraft(next);
          if (node.input_kind === "number") {
            const parsed = parseVisualNumberDraft(next);
            if (
              parsed === null ||
              (parsed !== undefined &&
                parsed >= (node.minimum ?? 0) &&
                parsed <= (node.maximum ?? 100))
            )
              onChange(parsed);
          } else onChange(next);
        }}
        placeholderTextColor={palette["muted-foreground"]}
        style={{
          minHeight: visual.touch,
          borderWidth: visual.border,
          borderColor: palette.border,
          borderRadius: visual.radius.small,
          backgroundColor: palette.input,
          color: palette.foreground,
          paddingHorizontal: visual.space.normal,
          fontSize: visual.controlFont,
          textAlign: rtl ? "right" : "left",
          writingDirection: rtl ? "rtl" : "ltr",
        }}
      />
    </View>
  );
}

export function NativeVisualSlider({ node, value, palette, rtl, onChange }: Props) {
  const width = useRef(1);
  const min = node.minimum ?? 0,
    max = node.maximum ?? 100,
    step = node.step ?? 1;
  const number =
    typeof value === "number" && Number.isFinite(value) ? Math.max(min, Math.min(max, value)) : min;
  const fraction = max === min ? 0 : (number - min) / (max - min);
  const change = (x: number) => {
    const ratio = Math.min(1, Math.max(0, x / width.current));
    const next = min + (rtl ? 1 - ratio : ratio) * (max - min);
    onChange(min + Math.round((next - min) / step) * step);
  };
  return (
    <View style={{ gap: visual.space.small }}>
      <View
        style={{
          flexDirection: rtl ? "row-reverse" : "row",
          justifyContent: "space-between",
          gap: visual.space.small,
        }}
      >
        <Text style={{ color: palette.foreground, fontSize: visual.font.label }}>
          {node.label ?? node.id}
        </Text>
        <Text style={{ color: palette["muted-foreground"], fontSize: visual.font.label }}>
          {number}
        </Text>
      </View>
      <View
        testID={`visual-slider-${node.id}`}
        accessible
        accessibilityRole="adjustable"
        accessibilityLabel={node.label ?? node.id}
        accessibilityValue={{ min, max, now: number }}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={number}
        accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
        onAccessibilityAction={(event) =>
          onChange(number + (event.nativeEvent.actionName === "increment" ? step : -step))
        }
        onLayout={(event) => {
          width.current = Math.max(1, event.nativeEvent.layout.width);
        }}
        onStartShouldSetResponder={() => true}
        onMoveShouldSetResponder={() => true}
        onResponderGrant={(event) => change(event.nativeEvent.locationX)}
        onResponderMove={(event) => change(event.nativeEvent.locationX)}
        style={{ minHeight: visual.touch, justifyContent: "center" }}
      >
        <View
          pointerEvents="none"
          style={{ height: 5, borderRadius: visual.radius.small, backgroundColor: palette.border }}
        >
          <View
            style={{
              height: 5,
              width: `${fraction * 100}%`,
              alignSelf: rtl ? "flex-end" : "flex-start",
              borderRadius: visual.radius.small,
              backgroundColor: palette.link,
            }}
          />
        </View>
        <View
          pointerEvents="none"
          style={{
            position: "absolute",
            [rtl ? "right" : "left"]: `${fraction * 100}%`,
            marginLeft: rtl ? 0 : -8,
            marginRight: rtl ? -8 : 0,
            width: 16,
            height: 16,
            borderRadius: 8,
            backgroundColor: palette.link,
          }}
        />
      </View>
      <View style={{ flexDirection: rtl ? "row-reverse" : "row", gap: visual.space.small }}>
        {([-1, 1] as const).map((direction) => (
          <Pressable
            key={direction}
            accessibilityRole="button"
            accessibilityLabel={`${node.label ?? node.id} ${direction < 0 ? "−" : "+"}`}
            onPress={() => onChange(number + direction * step)}
            style={{
              minWidth: visual.touch,
              minHeight: visual.touch,
              alignItems: "center",
              justifyContent: "center",
              borderWidth: visual.border,
              borderColor: palette.border,
              borderRadius: visual.radius.small,
            }}
          >
            <Text style={{ color: palette.foreground, fontSize: visual.font.body }}>
              {direction < 0 ? "−" : "+"}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}
