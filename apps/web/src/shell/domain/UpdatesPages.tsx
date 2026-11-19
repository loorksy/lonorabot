import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AttentionViewRow } from "@lonora/contracts";
import { Icon } from "@lonora/ui-web";
import { useAttentionLabels } from "../../components/ai/AttentionInbox";
import { api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useAttention } from "../../providers/AttentionProvider";
import { useShellData } from "../data";
import { useNavigation } from "../navigation";
import { SkHead, SkPage, SkRows } from "../Skeleton";
import { useToast } from "../Toast";
import { useLoad } from "./hooks";

/** «يحتاج انتباهك» (mandate 11.7): what needs the owner, across all agents, from one
 * server projection (GET /attention/view). A row opens its conversation, where the
 * fixed card or the question stands; opening it decides nothing. */
export function UpdatesPage() {
  const data = useShellData();
  const nav = useNavigation();
  const labels = useAttentionLabels();
  const attention = useAttention();
  const toast = useToast();
  const rows = useLoad(() => api.get<AttentionViewRow[]>("/attention/view"), "attention-view");
  if (rows.data === undefined && rows.error == null)
    return (
      <SkPage>
        <SkHead width={24} />
        <SkRows count={4} icon group />
      </SkPage>
    );
  const agentName = (id: string) => data.agents.find((agent) => agent.id === id)?.name ?? "";
  const title = (row: AttentionViewRow) =>
    row.kind === "owner_question"
      ? t`A question is waiting for your answer`
      : row.code
        ? labels[row.code]
        : "";
  const open = (row: AttentionViewRow) => {
    // Opening an alert reads it; a card or a question stays until it is answered.
    if (row.kind === "agent_alert" || row.kind === "system_alert")
      attention.seen(row.id).catch((cause) => toast(userError(cause), { type: "error" }));
    nav.go(
      row.group_id ? `/app/g/${row.group_id}` : `/app/${row.agent_id}?thread=${row.thread_id}`,
    );
  };
  const list = rows.data ?? [];
  return (
    <div className="domain-page">
      <div className="group" data-testid="attention-view">
        {rows.error != null ? (
          <p className="pad muted small">{userError(rows.error)}</p>
        ) : list.length ? (
          list.map((row) => (
            <button
              key={row.id}
              type="button"
              className="row"
              data-attention-id={row.id}
              data-attention-kind={row.kind}
              onClick={() => open(row)}
            >
              <span className="row-icon">
                <Icon name="bell" />
              </span>
              <span className="body">
                <strong>{title(row)}</strong>
                {row.summary ? (
                  <small dir="auto" data-testid="attention-summary">
                    {row.summary}
                  </small>
                ) : null}
                <small>
                  <bdi>{agentName(row.agent_id)}</bdi>
                  {row.symbol ? (
                    <>
                      {" · "}
                      <bdi>{row.symbol}</bdi>
                    </>
                  ) : null}
                </small>
              </span>
            </button>
          ))
        ) : (
          <p className="pad muted small">
            <Trans>Nothing needs you right now.</Trans>
          </p>
        )}
      </div>
    </div>
  );
}
