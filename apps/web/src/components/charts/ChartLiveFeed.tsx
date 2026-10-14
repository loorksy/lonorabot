import { Trans, useLingui } from "@lingui/react/macro";
import { userError } from "../../lib/user_error";
export function ChartLiveFeed({
  observedAt,
  status,
  errorCode,
}: {
  observedAt: string | null;
  status: string;
  errorCode?: string | null;
}) {
  const { i18n } = useLingui();
  return (
    <div className="row muted" role="status">
      {status === "failed" ? (
        <span>
          {userError(errorCode ?? "chart_unavailable")}{" "}
          <code>{errorCode ?? "chart_unavailable"}</code>
        </span>
      ) : (
        <span>
          <Trans>Cloud chart</Trans>
        </span>
      )}
      {observedAt && (
        <time dateTime={observedAt}>{new Date(observedAt).toLocaleString(i18n.locale)}</time>
      )}
    </div>
  );
}
