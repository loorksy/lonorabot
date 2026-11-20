import { fittedLine, plainLine } from "@lonora/core";
import { useState } from "react";
import { StyleSheet, Text, type TextProps } from "react-native";

/**
 * A message cut in the core (`fittedLine`) to the lines it is given at the width it is drawn
 * in, before its numbers are isolated. React Native's own line limit cuts where the box ends,
 * which can fall inside a signed number («−1.5%» read as «.5%»); this line always fits, so
 * that cut never comes and a figure shows whole or not at all (17, 0.4). Until the width is
 * known the whole line is drawn.
 */
export function FittedText({
  text,
  numberOfLines = 1,
  style,
  ...props
}: Omit<TextProps, "children"> & { text: string }) {
  const [width, setWidth] = useState(0);
  const fontSize = StyleSheet.flatten(style)?.fontSize ?? 14;
  return (
    <Text
      {...props}
      numberOfLines={numberOfLines}
      style={[{ flex: 1 }, style]}
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
    >
      {width ? fittedLine(text, { width, fontSize, lines: numberOfLines }) : plainLine(text)}
    </Text>
  );
}
