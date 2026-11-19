import { Trans } from "@lingui/react/macro";
import { BrokerConnection } from "../components/trading/BrokerConnection";
export function TradingSettingsPanel() {
  return (
    <>
      <h2>
        <Trans>Global trading settings</Trans>
      </h2>
      <BrokerConnection />
    </>
  );
}
