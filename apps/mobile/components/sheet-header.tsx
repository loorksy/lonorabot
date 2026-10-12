import { useRouter } from "expo-router";
import { useSession } from "../lib/session";
import { Button, Header } from "./ui";

export function SheetHeader({
  title,
  onClose,
  action,
  onAction,
  disabled,
}: {
  title: string;
  onClose?: () => void;
  action?: string;
  onAction?: () => void;
  disabled?: boolean;
}) {
  const router = useRouter();
  const { t } = useSession();
  return (
    <Header
      title={title}
      left={
        <Button
          label={t("back")}
          secondary
          onPress={onClose ?? (() => (router.canGoBack() ? router.back() : router.replace("/")))}
        />
      }
      right={
        action && onAction ? (
          <Button label={action} onPress={onAction} disabled={disabled} />
        ) : undefined
      }
    />
  );
}
