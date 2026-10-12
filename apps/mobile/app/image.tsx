// Full-screen image stack route adapted from Tampletgrok; see ../NOTICE.
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { Image, Platform, ScrollView, useWindowDimensions, View } from "react-native";
import { Button, ErrorNotice, Header, Loading, Screen } from "../components/ui";
import { isImage, useArtifact } from "../lib/artifacts";
import { useSession } from "../lib/session";

export default function ImageScreen() {
  const params = useLocalSearchParams<{ artifactId?: string | string[] }>();
  const id = (Array.isArray(params.artifactId) ? params.artifactId[0] : params.artifactId) ?? "";
  const router = useRouter();
  const { ready, owner, t, errorText } = useSession();
  const { content, error, loading, retry } = useArtifact(id);
  const [shareError, setShareError] = useState<string | null>(null);
  const [sharing, setSharing] = useState(false);
  const { width, height } = useWindowDimensions();
  const back = () => (router.canGoBack() ? router.back() : router.replace("/artifacts"));
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
  if (!ready) return <Loading />;
  if (!owner) return <Redirect href="/sign-in" />;
  return (
    <Screen>
      <Header
        title={content?.artifact.payload.name ?? t("image")}
        left={<Button label={t("back")} secondary onPress={back} />}
        right={
          content && isImage(content.mediaType) ? (
            <Button
              label={t(Platform.OS === "web" ? "download" : "share")}
              disabled={sharing}
              onPress={() => void share()}
            />
          ) : undefined
        }
      />
      <ErrorNotice
        text={error ?? shareError ?? (content && !isImage(content.mediaType) ? t("noImage") : null)}
      />
      {error ? (
        <View style={{ padding: 16 }}>
          <Button label={t("retry")} secondary onPress={retry} />
        </View>
      ) : null}
      {loading ? (
        <Loading />
      ) : content && isImage(content.mediaType) ? (
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={{ flexGrow: 1, alignItems: "center", justifyContent: "center" }}
          minimumZoomScale={1}
          maximumZoomScale={4}
          centerContent
        >
          <Image
            source={{ uri: content.uri }}
            accessibilityLabel={content.artifact.payload.name}
            resizeMode="contain"
            style={{ width: Math.max(width - 24, 120), height: Math.max(height - 160, 180) }}
          />
        </ScrollView>
      ) : null}
    </Screen>
  );
}
