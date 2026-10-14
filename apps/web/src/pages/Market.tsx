import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { ChartWorkspace } from "../components/charts/ChartWorkspace";
import { EconomicCalendar } from "../components/market/EconomicCalendar";
import { MarketOverview } from "../components/market/MarketOverview";
import { MarketQuote } from "../components/market/MarketQuote";
import { MarketWatch } from "../components/market/MarketWatch";
import { SymbolSearch } from "../components/market/SymbolSearch";
import { useMarket } from "../hooks/useMarket";
import { useTrading } from "../hooks/useTrading";
import type { Agent } from "../lib/api";
import { brokerIdentityLabel } from "../lib/broker-identity";
import { userError } from "../lib/user_error";
export function Market({ agents }: { agents: Agent[] }) {
  const [account, setAccount] = useState("");
  const [symbol, setSymbol] = useState("");
  const trading = useTrading(account);
  const market = useMarket(account, symbol);
  const connection = trading.connections.find((c) => c.id === account);
  return (
    <section>
      <h1>
        <Trans>Market</Trans>
      </h1>
      <div className="form-grid">
        <label>
          <Trans>Broker account</Trans>
          <select
            value={account}
            onChange={(e) => {
              setAccount(e.target.value);
              setSymbol("");
            }}
          >
            <option value="">
              <Trans>Choose a connection</Trans>
            </option>
            {trading.connections.map((c, index) => (
              <option key={c.id} value={c.id}>
                {brokerIdentityLabel(c, index)}
              </option>
            ))}
          </select>
        </label>
        <SymbolSearch symbols={market.symbols} value={symbol} onChange={setSymbol} />
      </div>
      {connection?.payload.provider === "simulation" && (
        <p className="notice">
          <Trans>Simulation · imported snapshot</Trans>
        </p>
      )}
      {market.error != null && <p role="alert">{userError(market.error)}</p>}
      <MarketQuote quote={market.quote} />
      <MarketOverview instrument={market.instrument} />
      {account && symbol && (
        <ChartWorkspace key={`${account}:${symbol}`} accountId={account} symbol={symbol} />
      )}
      <MarketWatch accountId={account} symbol={symbol} agents={agents} />
      <EconomicCalendar />
    </section>
  );
}
