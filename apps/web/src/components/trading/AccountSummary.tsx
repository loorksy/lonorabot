import { Trans } from "@lingui/react/macro";
import type { AccountSummary as Summary } from "../../lib/api";
export function AccountSummary({ data }: { data?: Summary }) {
  if (!data) return null;
  const a = data.account;
  return (
    <dl className="card stats">
      {a.broker && (
        <div>
          <dt>
            <Trans>Broker</Trans>
          </dt>
          <dd>
            <bdi>{a.broker}</bdi>
          </dd>
        </div>
      )}
      {a.login && (
        <div>
          <dt>
            <Trans>Account number</Trans>
          </dt>
          <dd>
            <bdi>{a.login}</bdi>
          </dd>
        </div>
      )}
      {a.server && (
        <div>
          <dt>
            <Trans>Broker server</Trans>
          </dt>
          <dd>
            <bdi>{a.server}</bdi>
          </dd>
        </div>
      )}
      <div>
        <dt>
          <Trans>Balance</Trans>
        </dt>
        <dd>
          {a.balance} <bdi>{a.currency}</bdi>
        </dd>
      </div>
      <div>
        <dt>
          <Trans>Equity</Trans>
        </dt>
        <dd>{a.equity}</dd>
      </div>
      <div>
        <dt>
          <Trans>Margin</Trans>
        </dt>
        <dd>{a.margin}</dd>
      </div>
      <div>
        <dt>
          <Trans>Free margin</Trans>
        </dt>
        <dd>{a.free_margin}</dd>
      </div>
    </dl>
  );
}
