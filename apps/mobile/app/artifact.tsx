// Preview/share detail flow adapted from Tampletgrok apps/mobile/app/artifact.tsx.
// See ../NOTICE. No demo artifact contracts, version history or unauthenticated URLs are used.
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Image, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Button, colors, ErrorNotice, Header, Loading, Screen } from "../components/ui";
import { formatFileSize, isImage, isolatedHtml, useArtifact } from "../lib/artifacts";
import { useSession } from "../lib/session";

function first(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

export default function ArtifactScreen() {
  const { artifactId } = useLocalSearchParams<{ artifactId?: string | string[] }>();
  const id = first(artifactId);
  const router = useRouter();
  const { ready, owner, t, rtl, locale, errorText } = useSession();
  const { content, error, loading, retry } = useArtifact(id);
  const [sharing, setSharing] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const share = async () => {
    if (!content || sharing) return;
    setSharing(true);
    setShareError(null);
    try {
      await content.share();
    } catch (reason) {
      setShareError(errorText(reason));
    } finally {
      setSharing(false);
    }
  };
  const back = () => (router.canGoBack() ? router.back() : router.replace("/artifacts"));
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <Header
        title={content?.artifact.payload.name ?? t("artifacts")}
        left={<Button label={t("back")} secondary onPress={back} />}
        right={
          content ? (
            <Button
              label={t(Platform.OS === "web" ? "download" : "share")}
              disabled={sharing}
              onPress={() => void share()}
            />
          ) : undefined
        }
      />
      <ErrorNotice text={error ?? shareError} />
      {error ? (
        <View style={{ padding: 16 }}>
          <Button label={t("retry")} secondary onPress={retry} />
        </View>
      ) : null}
      {loading ? (
        <Loading />
      ) : content ? (
        <View style={{ flex: 1, gap: 12, paddingHorizontal: 16, paddingBottom: 16 }}>
          <Text
            style={{ color: colors.secondary, fontSize: 13, textAlign: rtl ? "right" : "left" }}
          >
            {content.mediaType} · {formatFileSize(content.artifact.payload.size, locale)}
          </Text>
          {isImage(content.mediaType) ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={t("image")}
              style={{
                flex: 1,
                backgroundColor: colors.muted,
                borderRadius: 12,
                overflow: "hidden",
              }}
              onPress={() => router.push({ pathname: "/image", params: { artifactId: id } })}
            >
              <Image
                accessibilityLabel={content.artifact.payload.name}
                source={{ uri: content.uri }}
                resizeMode="contain"
                style={{ width: "100%", height: "100%" }}
              />
            </Pressable>
          ) : Platform.OS === "web" &&
            content.mediaType === "text/html" &&
            content.text !== null ? (
            <iframe
              title={t("preview")}
              sandbox=""
              referrerPolicy="no-referrer"
              srcDoc={isolatedHtml(content.text)}
              style={{
                width: "100%",
                flex: 1,
                minHeight: 320,
                border: 0,
                borderRadius: 12,
                background: "white",
              }}
            />
          ) : Platform.OS === "web" && content.mediaType === "application/pdf" ? (
            <iframe
              title={t("preview")}
              sandbox=""
              referrerPolicy="no-referrer"
              src={content.uri}
              style={{
                width: "100%",
                flex: 1,
                minHeight: 320,
                border: 0,
                borderRadius: 12,
                background: "white",
              }}
            />
          ) : content.text !== null ? (
            <>
              {content.mediaType === "text/html" ? (
                <Text
                  style={{
                    color: colors.secondary,
                    lineHeight: 22,
                    textAlign: rtl ? "right" : "left",
                  }}
                >
                  {t("nativeHtmlPreview")}
                </Text>
              ) : null}
              <ScrollView
                style={{ flex: 1, backgroundColor: colors.muted, borderRadius: 12 }}
                contentContainerStyle={{ padding: 16 }}
              >
                <Text
                  selectable
                  style={{
                    color: colors.foreground,
                    lineHeight: 23,
                    fontSize: 14,
                    fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
                    writingDirection: "auto",
                  }}
                >
                  {content.text}
                </Text>
              </ScrollView>
            </>
          ) : (
            <View
              style={{
                flex: 1,
                alignItems: "center",
                justifyContent: "center",
                gap: 16,
                padding: 20,
              }}
            >
              <Text style={{ color: colors.secondary, lineHeight: 24, textAlign: "center" }}>
                {t(
                  content.mediaType === "application/pdf"
                    ? "nativePdfPreview"
                    : "unsupportedPreview",
                )}
              </Text>
              <Button
                label={t(Platform.OS === "web" ? "download" : "share")}
                disabled={sharing}
                onPress={() => void share()}
              />
            </View>
          )}
          {content.truncated && content.text !== null ? (
            <Text
              style={{ color: colors.secondary, fontSize: 12, textAlign: rtl ? "right" : "left" }}
            >
              {t("previewTruncated")}
            </Text>
          ) : null}
          {content.artifact.thread_id ? (
            <Button
              label={t("openConversation")}
              secondary
              onPress={() =>
                router.push({ pathname: "/thread", params: { id: content.artifact.thread_id } })
              }
            />
          ) : null}
        </View>
      ) : null}
    </Screen>
  );
}
