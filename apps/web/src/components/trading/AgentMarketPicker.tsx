import { t } from "@lingui/core/macro";
import { Trans } from "@lingui/react/macro";
import type { AgentMarketMode } from "@lonora/core";
import { type BrokerPair, BrokerPairPicker } from "./BrokerPairPicker";

export function AgentMarketPicker({
  mode,
  pair,
  onMode,
  onPair,
  allowFixed = false,
}: {
  mode: AgentMarketMode;
  pair: BrokerPair;
  onMode: (mode: AgentMarketMode) => void;
  onPair: (pair: BrokerPair) => void;
  allowFixed?: boolean;
}) {
  return (
    <section className="permission-groups" aria-label={t`Agent market scope`}>
      <label>
        <Trans>Agent market scope</Trans>
        <select
          data-testid="agent-market-mode"
          value={mode}
          onChange={(e) => onMode(e.target.value as AgentMarketMode)}
        >
          {allowFixed && <option value="fixed">{t`Keep current fixed market`}</option>}
          <option value="general">{t`General agent`}</option>
          <option value="market">{t`Default market`}</option>
        </select>
      </label>
      {mode === "fixed" ? (
        <p>
          <bdi>{pair.trading_symbol}</bdi> ·{" "}
          <Trans>The existing fixed market stays unchanged until you choose a new scope.</Trans>
        </p>
      ) : mode === "market" ? (
        <BrokerPairPicker value={pair} onChange={onPair} />
      ) : null}
      {mode !== "fixed" && (
        <p className="muted">
          <Trans>
            The default market is optional. Other markets can be analyzed; trading follows your
            separate authorization.
          </Trans>
        </p>
      )}
    </section>
  );
}
