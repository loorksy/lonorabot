import type { InputAnswer, InputRequest } from "@lonora/contracts";
import { useRef, useState } from "react";
import { Pressable, Text, View } from "react-native";
import { useSession } from "../lib/session";
import { NativeSymbol } from "./native-symbol";
import { colors, ErrorNotice } from "./ui";

export function ConversationQuestion({
  request,
  onAnswer,
}: {
  request: InputRequest;
  onAnswer: (answer: InputAnswer, label: string, messageId: string) => Promise<void>;
}) {
  const { rtl, t, errorText } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef(false);
  async function answer(choice: InputRequest["choices"][number]) {
    if (pending.current || request.status !== "pending") return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      await onAnswer(
        { run_id: request.run_id, question_id: request.id, choice_id: choice.id },
        choice.label,
        request.message_id,
      );
    } catch (cause) {
      setError(errorText(cause));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <View
      testID={`question-${request.id}`}
      style={{ backgroundColor: colors.muted, borderRadius: 20, padding: 16, gap: 12 }}
    >
      <Text style={{ color: colors.foreground, fontSize: 16, textAlign: rtl ? "right" : "left" }}>
        {request.question}
      </Text>
      <View
        style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 16, overflow: "hidden" }}
      >
        {request.choices.map((choice, index) => (
          <Pressable
            key={choice.id}
            accessibilityRole="button"
            aria-selected={request.selected_choice_id === choice.id}
            accessibilityLabel={choice.label}
            accessibilityState={{
              disabled: busy || request.status !== "pending",
              selected: request.selected_choice_id === choice.id,
            }}
            disabled={busy || request.status !== "pending"}
            onPress={() => void answer(choice)}
            style={{
              flexDirection: rtl ? "row-reverse" : "row",
              alignItems: "center",
              gap: 10,
              padding: 14,
              minHeight: 48,
              backgroundColor: colors.background,
              borderTopWidth: index ? 1 : 0,
              borderTopColor: colors.border,
              opacity:
                request.status !== "pending" && request.selected_choice_id !== choice.id ? 0.55 : 1,
            }}
          >
            <Text style={{ color: colors.secondary, fontSize: 12 }}>
              {String.fromCharCode(65 + index)}
            </Text>
            <Text
              style={{
                flex: 1,
                color: colors.foreground,
                fontSize: 16,
                textAlign: rtl ? "right" : "left",
              }}
            >
              {choice.label}
            </Text>
            {request.selected_choice_id === choice.id && (
              <NativeSymbol name="check" size={18} color={colors.foreground} />
            )}
          </Pressable>
        ))}
      </View>
      <Text accessibilityLiveRegion="polite" style={{ color: colors.secondary, fontSize: 12 }}>
        {t(
          request.status === "pending"
            ? "questionPending"
            : request.status === "answered"
              ? "questionAnswered"
              : "questionClosed",
        )}
      </Text>
      <ErrorNotice text={error} />
    </View>
  );
}
