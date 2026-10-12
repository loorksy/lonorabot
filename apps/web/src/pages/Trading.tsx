import { Trans } from "@lingui/react/macro";
import { useState } from "react";
import { AccountSummary } from "../components/trading/AccountSummary";
import { BrokerConnection } from "../components/trading/BrokerConnection";
import { Orders } from "../components/trading/Orders";
import { Positions } from "../components/trading/Positions";
import { TradeActionCard } from "../components/trading/TradeActionCard";
import { TradingJournal } from "../components/trading/TradingJournal";
import { TradingStatus } from "../components/trading/TradingStatus";
import { useMarket } from "../hooks/useMarket";
import { useTrading } from "../hooks/useTrading";
import { api } from "../lib/api";
import { userError } from "../lib/user_error";
import { useClient } from "../providers/ClientProvider";
export function Trading() {
  const { refresh } = useClient();
  const [id, setId] = useState("");
  const trading = useTrading(id);
  const market = useMarket(id, "");
  const [error, setError] = useState<unknown>();
  return (
    <section>
      <h1>
        <Trans>Trading</Trans>
      </h1>
      <TradingStatus />
      <BrokerConnection />
      <div className="row">
        <label>
          <Trans>Broker account</Trans>
          <select value={id} onChange={(e) => setId(e.target.value)}>
            <option value="">
              <Trans>Choose a connection</Trans>
            </option>
            {trading.connections.map((c) => (
              <option key={c.id} value={c.id}>
                {String(c.payload.account_id)} · {String(c.payload.provider)}
              </option>
            ))}
          </select>
        </label>
        {id && (
          <button
            type="button"
            className="danger"
            onClick={() =>
              void api
                .delete(`/trading/connections/${id}`)
                .then(() => {
                  setId("");
                  refresh();
                })
                .catch(setError)
            }
          >
            <Trans>Disconnect account</Trans>
          </button>
        )}
      </div>
      {trading.connections.find((c) => c.id === id)?.payload.provider === "simulation" && (
        <p className="notice">
          <Trans>Simulation · imported snapshot</Trans>
        </p>
      )}
      {(error ?? trading.error ?? market.error) != null && (
        <p role="alert">{userError(error ?? trading.error ?? market.error)}</p>
      )}
      <AccountSummary data={trading.account} />
      {id && (
        <>
          <div className="columns">
            <Positions
              accountId={id}
              positions={trading.account?.positions ?? []}
              onChange={refresh}
            />
            <Orders accountId={id} orders={trading.account?.orders ?? []} onChange={refresh} />
          </div>
          <TradeActionCard
            key={id}
            accountId={id}
            instruments={market.instruments}
            onChange={refresh}
          />
        </>
      )}
      <TradingJournal entries={trading.journal} />
    </section>
  );
}
