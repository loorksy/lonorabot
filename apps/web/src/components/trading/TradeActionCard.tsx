import { Trans } from "@lingui/react/macro";
import { useRef, useState } from "react";
import type { Instrument, Payload } from "../../lib/api";
import { executeTrade } from "../../lib/trading";
import { userError } from "../../lib/user_error";
export function TradeActionCard({
  accountId,
  instruments,
  onChange,
}: {
  accountId: string;
  instruments: Instrument[];
  onChange: () => void;
}) {
  const [symbol, setSymbol] = useState("");
  const [action, setAction] = useState("buy");
  const [volume, setVolume] = useState("");
  const [price, setPrice] = useState("");
  const [sl, setSL] = useState("");
  const [tp, setTP] = useState("");
  const [result, setResult] = useState<Payload>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const operation = useRef<string | null>(null);
  const pending = action.includes("_");
  const instrument = instruments.find((i) => i.symbol === symbol);
  return (
    <form
      className="card"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        operation.current ??= crypto.randomUUID();
        try {
          const r = await executeTrade({
            account_id: accountId,
            operation_id: operation.current,
            action,
            symbol,
            volume,
            price: pending ? price : undefined,
            stop_loss: sl || undefined,
            take_profit: tp || undefined,
          });
          setResult(r);
          setError(undefined);
          if (r.status !== "ambiguous" && r.status !== "submitted") operation.current = null;
          onChange();
        } catch (err) {
          setError(err);
        } finally {
          setBusy(false);
        }
      }}
    >
      <h2>
        <Trans>Trade action</Trans>
      </h2>
      <div className="form-grid">
        <label>
          <Trans>Exact broker symbol</Trans>
          <select
            required
            value={symbol}
            disabled={!!operation.current}
            onChange={(e) => setSymbol(e.target.value)}
          >
            <option value="">
              <Trans>Choose an instrument</Trans>
            </option>
            {instruments.map((i) => (
              <option key={i.symbol} value={i.symbol}>
                {i.symbol}
              </option>
            ))}
          </select>
        </label>
        <label>
          <Trans>Action</Trans>
          <select
            value={action}
            disabled={!!operation.current}
            onChange={(e) => setAction(e.target.value)}
          >
            <option value="buy">
              <Trans>Market buy</Trans>
            </option>
            <option value="sell">
              <Trans>Market sell</Trans>
            </option>
            <option value="buy_limit">
              <Trans>Buy limit</Trans>
            </option>
            <option value="sell_limit">
              <Trans>Sell limit</Trans>
            </option>
            <option value="buy_stop">
              <Trans>Buy stop</Trans>
            </option>
            <option value="sell_stop">
              <Trans>Sell stop</Trans>
            </option>
          </select>
        </label>
        <label>
          <Trans>Volume</Trans>
          <input
            required
            type="number"
            min={instrument?.volume_min ?? "0.01"}
            max={instrument?.volume_max}
            step={instrument?.volume_step ?? "any"}
            disabled={!!operation.current}
            value={volume}
            onChange={(e) => setVolume(e.target.value)}
          />
        </label>
        {pending && (
          <label>
            <Trans>Order price</Trans>
            <input
              required
              type="number"
              step="any"
              disabled={!!operation.current}
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </label>
        )}
        <label>
          <Trans>Stop loss · optional</Trans>
          <input
            type="number"
            step="any"
            disabled={!!operation.current}
            value={sl}
            onChange={(e) => setSL(e.target.value)}
          />
        </label>
        <label>
          <Trans>Take profit · optional</Trans>
          <input
            type="number"
            step="any"
            disabled={!!operation.current}
            value={tp}
            onChange={(e) => setTP(e.target.value)}
          />
        </label>
      </div>
      <button type="submit" className="primary" disabled={busy || !accountId}>
        {operation.current ? <Trans>Check existing operation</Trans> : <Trans>Execute</Trans>}
      </button>
      {error != null && <p role="alert">{userError(error)}</p>}
      {result && (
        <p role="status">
          {result.status === "confirmed" ? (
            <Trans>Operation confirmed</Trans>
          ) : result.status === "ambiguous" || result.status === "submitted" ? (
            <Trans>Awaiting reconciliation. This operation will not be sent again.</Trans>
          ) : (
            <Trans>Operation failed</Trans>
          )}
        </p>
      )}
    </form>
  );
}
