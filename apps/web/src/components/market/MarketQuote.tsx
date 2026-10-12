import { Trans } from "@lingui/react/macro";
import type { Quote } from "../../lib/api";
export function MarketQuote({ quote }: { quote?: Quote }) {
  return quote ? (
    <section className="quote-card">
      <h2>
        <bdi>{quote.symbol}</bdi>
      </h2>
      <dl className="stats">
        <div>
          <dt>
            <Trans>Bid</Trans>
          </dt>
          <dd dir="ltr">{quote.bid}</dd>
        </div>
        <div>
          <dt>
            <Trans>Ask</Trans>
          </dt>
          <dd dir="ltr">{quote.ask}</dd>
        </div>
        <div>
          <dt>
            <Trans>Spread</Trans>
          </dt>
          <dd dir="ltr">{(Number(quote.ask) - Number(quote.bid)).toPrecision(5)}</dd>
        </div>
      </dl>
      <small className="muted">
        <Trans>Source</Trans>: <bdi>{quote.source}</bdi> ·{" "}
        <time>{new Date(quote.observed_at).toLocaleString()}</time>
      </small>
    </section>
  ) : (
    <p className="muted">
      <Trans>Choose a connected account and an instrument to load market data.</Trans>
    </p>
  );
}
