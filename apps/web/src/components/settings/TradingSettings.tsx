import { Trans } from "@lingui/react/macro";
import { BrokerConnection } from "../trading/BrokerConnection";
import { TradingStatus } from "../trading/TradingStatus";
export function TradingSettings() {
  return (
    <>
      <h2>
        <Trans>Global trading settings</Trans>
      </h2>
      <TradingStatus />
      <BrokerConnection />
    </>
  );
}
