import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import { Icon } from "@lonora/ui-web";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, type Resource } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { SkPage, SkRows } from "../Skeleton";
import { useSheets } from "../sheets/SheetHost";
import { useToast } from "../Toast";
import { accountLabel, useRead } from "./shared";
import "./agent.css";

type Recovery = {
  status?: string;
  reason_code?: string;
  since?: string;
  observed_at?: string;
  last_success_at?: string | null;
  unresolved_operations?: string[];
};
const DOWN = new Set(["degraded", "disconnected", "recovering", "reconciling"]);
const recoveryOf = (row: Resource) => (row.state?.broker_recovery ?? {}) as Recovery;
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : "—");

function statusName(status: string | undefined) {
  switch (status) {
    case "recovering":
      return t({ message: "Reconnecting", context: "broker" });
    case "reconciling":
      return t({ message: "Checking with the broker", context: "broker" });
    default:
      return t({ message: "Paused for now", context: "execution" });
  }
}

/* «التعطل والاستعادة» (route recovery): the broker session's own recovery state
   (lonora_trading.broker_recovery, the broker_degraded attention code), not a toast. While a
   session is down the executor holds the affected trading until reconnect and reconciliation. */
export function RecoveryPage() {
  const [params] = useSearchParams();
  const sheets = useSheets();
  const toast = useToast();
  const connections = useRead<Resource[]>("/trading/connections");
  const [busy, setBusy] = useState(false);
  if (connections.error != null) return <p role="alert">{userError(connections.error)}</p>;
  if (!connections.value)
    return (
      <SkPage>
        <SkRows count={3} />
      </SkPage>
    );
  const all = connections.value;
  const wanted = params.get("account");
  const down = all.filter(
    (row) => DOWN.has(recoveryOf(row).status ?? "") && (!wanted || row.id === wanted),
  );
  if (!down.length)
    return (
      <>
        <div className="hero recovered">
          <Icon name="check" />
          <h2>
            <Trans>The broker is connected</Trans>
          </h2>
        </div>
        <p className="muted">
          <Trans>Every linked trading account answers normally. Nothing is held.</Trans>
        </p>
      </>
    );
  const retry = async () => {
    setBusy(true);
    try {
      // A fresh read through the broker manager; the reconciliation writes the new state.
      for (const row of down) await api.get(`/trading/accounts/${row.id}`).catch(() => undefined);
      connections.reload();
      toast(t`Retried. The state updates when the broker answers.`, { type: "info" });
    } finally {
      setBusy(false);
    }
  };
  const details = () =>
    sheets.open({
      id: "recovery-details",
      title: t`State details`,
      body: (
        <>
          {down.map((row) => {
            const state = recoveryOf(row);
            return (
              <div className="group" key={row.id}>
                <div className="row">
                  <span className="body">
                    <Trans>Account</Trans>
                  </span>
                  <span className="value">
                    <bdi>{accountLabel(all, row.id)}</bdi>
                  </span>
                </div>
                <div className="row">
                  <span className="body">
                    <Trans>Since</Trans>
                  </span>
                  <span className="value ltr">{when(state.since)}</span>
                </div>
                <div className="row">
                  <span className="body">
                    <Trans>Last successful read</Trans>
                  </span>
                  <span className="value ltr">{when(state.last_success_at)}</span>
                </div>
                <div className="row">
                  <span className="body">
                    <Trans>Reason</Trans>
                  </span>
                  <span className="value ltr">{state.reason_code ?? "—"}</span>
                </div>
                <div className="row">
                  <span className="body">
                    <Trans>Operations awaiting confirmation</Trans>
                  </span>
                  <span className="value ltr">{state.unresolved_operations?.length ?? 0}</span>
                </div>
              </div>
            );
          })}
        </>
      ),
    });
  return (
    <>
      <div className="hero">
        <Icon name="alert" />
        <h2>
          <Trans>The broker connection dropped</Trans>
        </h2>
      </div>
      <p className="muted">
        <Trans>Affected execution stops until the connection is restored and checked.</Trans>
      </p>
      <div className="group">
        {down.map((row) => (
          <div className="row" key={row.id}>
            <span className="body">
              <Trans>Execution state</Trans>
              {down.length > 1 && (
                <small>
                  <bdi>{accountLabel(all, row.id)}</bdi>
                </small>
              )}
            </span>
            <span className="value">{statusName(recoveryOf(row).status)}</span>
          </div>
        ))}
      </div>
      <button type="button" className="btn full" onClick={details}>
        <Trans>State details</Trans>
      </button>
      <button
        type="button"
        className="btn full primary"
        disabled={busy}
        onClick={() => void retry()}
      >
        <Trans>Try again</Trans>
      </button>
    </>
  );
}
