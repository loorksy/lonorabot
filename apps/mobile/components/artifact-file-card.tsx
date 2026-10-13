// Inline cards use authenticated artifact bytes; never put session credentials in image URLs.
import type { Artifact } from "@lonora/contracts";
import { ActivityIndicator, Image, Pressable, Text, View } from "react-native";
import { formatFileSize, isImage, mimeBadge, useArtifact } from "../lib/artifacts";
import { useSession } from "../lib/session";
import { NativeSymbol } from "./native-symbol";
import { colors } from "./ui";
export function ArtifactFileCard({
  id,
  artifact,
  onOpen,
}: {
  id: string;
  artifact?: Artifact;
  onOpen: () => void;
}) {
  return artifact && isImage(artifact.payload.media_type.split(";")[0].toLowerCase()) ? (
    <ImageArtifact id={id} artifact={artifact} onOpen={onOpen} />
  ) : (
    <FileArtifact artifact={artifact} onOpen={onOpen} />
  );
}
function FileArtifact({ artifact, onOpen }: { artifact?: Artifact; onOpen: () => void }) {
  const { rtl, locale, t } = useSession();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={artifact?.payload.name ?? t("attach")}
      onPress={onOpen}
      style={({ pressed }) => ({
        flexDirection: rtl ? "row-reverse" : "row",
        alignItems: "center",
        gap: 12,
        borderRadius: 14,
        borderWidth: 0.5,
        borderColor: colors.border,
        padding: 14,
        backgroundColor: colors.muted,
        opacity: pressed ? 0.6 : 1,
      })}
    >
      <NativeSymbol name="file" size={24} color={colors.secondary} />
      <View style={{ flex: 1, gap: 4 }}>
        <Text
          numberOfLines={2}
          style={{ color: colors.foreground, fontSize: 14, writingDirection: "auto" }}
        >
          {artifact?.payload.name ?? t("attach")}
        </Text>
        {artifact ? (
          <Text style={{ color: colors.secondary, fontSize: 12, writingDirection: "ltr" }}>
            {mimeBadge(artifact.payload.media_type)} ·{" "}
            {formatFileSize(artifact.payload.size, locale)}
          </Text>
        ) : null}
      </View>
      <NativeSymbol name="chevron" size={16} color={colors.secondary} />
    </Pressable>
  );
}
function ImageArtifact({
  id,
  artifact,
  onOpen,
}: {
  id: string;
  artifact: Artifact;
  onOpen: () => void;
}) {
  const { content, loading, error } = useArtifact(id);
  const { t } = useSession();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={artifact.payload.name}
      onPress={onOpen}
      style={({ pressed }) => ({
        width: "100%",
        maxWidth: 560,
        borderRadius: 14,
        overflow: "hidden",
        backgroundColor: colors.muted,
        borderWidth: 0.5,
        borderColor: colors.border,
        opacity: pressed ? 0.75 : 1,
      })}
    >
      {content ? (
        <Image
          source={{ uri: content.uri }}
          accessibilityLabel={artifact.payload.name}
          resizeMode="contain"
          style={{ width: "100%", height: 230 }}
        />
      ) : (
        <View style={{ height: 150, alignItems: "center", justifyContent: "center", gap: 8 }}>
          {loading ? (
            <ActivityIndicator color={colors.secondary} />
          ) : (
            <NativeSymbol name="file" size={28} color={colors.secondary} />
          )}
          {error ? (
            <Text style={{ color: colors.secondary, padding: 12, textAlign: "center" }}>
              {t("preview")}
            </Text>
          ) : null}
        </View>
      )}
      <View style={{ flexDirection: "row", padding: 12, alignItems: "center", gap: 8 }}>
        <NativeSymbol name="chart" size={16} color={colors.secondary} />
        <Text
          numberOfLines={1}
          style={{ flex: 1, color: colors.foreground, fontSize: 13, writingDirection: "auto" }}
        >
          {artifact.payload.name}
        </Text>
        <NativeSymbol name="chevron" size={14} color={colors.secondary} />
      </View>
    </Pressable>
  );
}
