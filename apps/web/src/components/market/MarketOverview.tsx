import { Trans } from "@lingui/react/macro";
import type { Instrument } from "../../lib/api";
export function MarketOverview({ instrument }: { instrument?: Instrument }) {
  if (!instrument) return null;
  return (
    <dl className="card stats">
      <div>
        <dt>
          <Trans>Tick size</Trans>
        </dt>
        <dd>
          <bdi>{instrument.tick_size}</bdi>
        </dd>
      </div>
      <div>
        <dt>
          <Trans>Minimum volume</Trans>
        </dt>
        <dd>{instrument.volume_min}</dd>
      </div>
      <div>
        <dt>
          <Trans>Volume step</Trans>
        </dt>
        <dd>{instrument.volume_step}</dd>
      </div>
      <div>
        <dt>
          <Trans>Maximum volume</Trans>
        </dt>
        <dd>{instrument.volume_max}</dd>
      </div>
    </dl>
  );
}
