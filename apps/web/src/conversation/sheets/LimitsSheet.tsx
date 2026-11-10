import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { DeviceChallenge } from "@lonora/contracts";
import { webDeviceProof, webDeviceSupported } from "@lonora/core";
import { Icon } from "@lonora/ui-web";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../../lib/api";
import { userError } from "../../lib/user_error";
import { useClient } from "../../providers/ClientProvider";
import { useSheets } from "../../shell/sheets/SheetHost";
import { useToast } from "../../shell/Toast";

/* «حدود الحساب» (reference OA_R.set_account_limits, Desktop-37 7801-7812) on the server's fields
   (Q16): daily loss and free margin in the account's currency, trade and open risk in % of
   equity, old → new. Tightening saves at once; raising or removing a limit is signed with the
   passkey (the server answers 403 execution_policy_passkey_required, then the challenge binds
   the exact new policy). Per account: it applies to every agent of the account. */

type Field =
  | "max_daily_loss"
  | "max_trade_risk_equity_percent"
  | "max_open_risk_equity_percent"
  | "min_free_margin";
type Policy = { risk: Record<string, unknown> & { currency?: string | null } } & Record<
  string,
  unknown
>;
const FIELDS: Array<{
  key: Field;
  step: number;
  min: number;
  max: number;
  percent: boolean;
  label: () => string;
}> = [
  {
    key: "max_daily_loss",
    step: 10,
    min: 10,
    max: 1_000_000,
    percent: false,
    label: () => t`Daily loss limit`,
  },
  {
    key: "max_trade_risk_equity_percent",
    step: 0.25,
    min: 0.25,
    max: 10,
    percent: true,
    label: () => t`Trade risk limit`,
  },
  {
    key: "max_open_risk_equity_percent",
    step: 0.5,
    min: 1,
    max: 40,
    percent: true,
    label: () => t`Open risk limit`,
  },
  {
    key: "min_free_margin",
    step: 50,
    min: 50,
    max: 10_000_000,
    percent: false,
    label: () => t`Minimum free margin`,
  },
];
const num = (value: unknown) => (value == null || value === "" ? null : Number(value));
/** Looser = more may be lost: a loss/risk limit raised or removed, a margin floor lowered or removed. */
function looser(key: Field, from: number | null, to: number | null) {
  if (from === to) return false;
  if (to == null) return from != null;
  if (from == null) return false;
  return key === "min_free_margin" ? to < from : to > from;
}

function LimitsBody({ accountId, close }: { accountId: string; close: () => void }) {
  const { refresh } = useClient();
  const toast = useToast();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [next, setNext] = useState<Record<Field, number | null> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const path = `/trading/accounts/${encodeURIComponent(accountId)}/execution-policy`;
  useEffect(() => {
    let live = true;
    void api
      .get<Policy>(path)
      .then((row) => {
        if (!live) return;
        setPolicy(row);
        setNext(
          Object.fromEntries(FIELDS.map(({ key }) => [key, num(row.risk[key])])) as Record<
            Field,
            number | null
          >,
        );
      })
      .catch((cause) => live && setError(cause));
    return () => {
      live = false;
    };
  }, [path]);
  if (!policy || !next)
    return error ? <p className="form-error">{userError(error)}</p> : <p className="note">…</p>;
  const from = (key: Field) => num(policy.risk[key]);
  const changed = FIELDS.some(({ key }) => from(key) !== next[key]);
  const loose = FIELDS.some(({ key }) => looser(key, from(key), next[key]));
  const unit = (percent: boolean) =>
    percent ? "%" : policy.risk.currency ? ` ${policy.risk.currency}` : "";
  const show = (value: number | null, percent: boolean) =>
    value == null ? t`No limit` : `${+value.toFixed(2)}${unit(percent)}`;
  const save = async () => {
    const body: Policy = {
      ...policy,
      risk: {
        ...policy.risk,
        ...Object.fromEntries(
          FIELDS.map(({ key }) => [key, next[key] == null ? null : String(next[key])]),
        ),
      },
    };
    setBusy(true);
    setError(undefined);
    try {
      try {
        await api.put(path, body);
      } catch (cause) {
        if (!(cause instanceof ApiError && cause.code === "execution_policy_passkey_required"))
          throw cause;
        const challenge = await api.post<DeviceChallenge>(`${path}/challenge`, body);
        const proof = await webDeviceProof(challenge);
        await api.post(`${path}/verify`, { policy: body, proof });
      }
      refresh();
      close();
      toast(
        FIELDS.filter(({ key }) => from(key) !== next[key])
          .map(({ key, label, percent }) => `${label()} ${show(next[key], percent)}`)
          .join(" · "),
        { type: "success" },
      );
    } catch (cause) {
      setError(cause);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="oa in-sheet act-set_account_limits st-pending">
      <p className="oa-sub">
        <Trans>Applies to every agent of this account</Trans>
      </p>
      <div className="oa-lims">
        {FIELDS.map(({ key, step, min, max, percent, label }) => {
          const a = from(key);
          const b = next[key];
          const ch = a !== b;
          return (
            <div
              key={key}
              className={`oa-lim edit${ch ? (looser(key, a, b) ? " loose" : " tight") : ""}`}
            >
              <span className="oa-l">{label()}</span>
              <span className="oa-diff">
                <span className="ltr old">{show(a, percent)}</span>
                <Icon name="chev" />
                {b == null ? (
                  <>
                    <span className="ltr new">{t`No limit`}</span>
                    <button
                      type="button"
                      className="oa-link"
                      onClick={() => setNext({ ...next, [key]: a ?? min })}
                    >
                      <Trans>Restore</Trans>
                    </button>
                  </>
                ) : (
                  <>
                    <span className="oa-num">
                      <button
                        type="button"
                        aria-label={t`Decrease`}
                        onClick={() =>
                          setNext({ ...next, [key]: Math.max(min, +(b - step).toFixed(2)) })
                        }
                      >
                        <Icon name="minus" />
                      </button>
                      <output className="ltr">{show(b, percent)}</output>
                      <button
                        type="button"
                        aria-label={t`Increase`}
                        onClick={() =>
                          setNext({ ...next, [key]: Math.min(max, +(b + step).toFixed(2)) })
                        }
                      >
                        <Icon name="plus" />
                      </button>
                    </span>
                    <button
                      type="button"
                      className="oa-x"
                      aria-label={t`Remove ${label()}`}
                      title={t`No limit`}
                      onClick={() => setNext({ ...next, [key]: null })}
                    >
                      <Icon name="close" />
                    </button>
                  </>
                )}
              </span>
            </div>
          );
        })}
      </div>
      <p className="oa-hint">
        <Icon name={loose ? "fingerprint" : "check"} />
        <span>
          {!changed
            ? t`Change a value to save it.`
            : loose
              ? t`Raising or removing a limit needs the passkey.`
              : t`Tightening is saved at once.`}
        </span>
      </p>
      {loose && !webDeviceSupported() && (
        <p className="oa-warn">{t`This browser cannot use a passkey.`}</p>
      )}
      {error != null && (
        <p className="oa-warn" role="alert">
          <Icon name="alert" />
          <span>{userError(error)}</span>
        </p>
      )}
      <div className="oa-actions">
        <button
          type="button"
          className={`btn primary${changed ? "" : " is-off"}${busy ? " is-busy" : ""}`}
          disabled={!changed || busy}
          onClick={() => void save()}
        >
          {loose && <Icon name="fingerprint" />}
          <span>{loose ? t`Save with the passkey` : t`Save`}</span>
        </button>
        <button type="button" className="btn" onClick={close}>
          <Trans>Cancel</Trans>
        </button>
      </div>
    </div>
  );
}

export function useLimitsSheet() {
  const sheets = useSheets();
  return useCallback(
    (accountId: string) => {
      const title = t`Account limits`;
      sheets.open({
        id: "limits",
        title,
        label: title,
        body: <LimitsBody accountId={accountId} close={() => sheets.close()} />,
      });
    },
    [sheets],
  );
}
