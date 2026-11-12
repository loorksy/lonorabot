import { Trans } from "@lingui/react/macro";
import { BrokerConnection } from "../components/trading/BrokerConnection";
import { TradingStatus } from "../components/trading/TradingStatus";
export function TradingSettingsPanel() {
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
