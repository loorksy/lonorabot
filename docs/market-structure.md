# Confirmed market structure

The existing market tools expose `market_structure`, a read-only measurement over
the same account, exact broker symbol and candle history used by the Agent.
Specialist scope remains unchanged. The result uses the existing `Observation`
contract and does not create another market runtime or grant execution authority.

The caller chooses a timeframe, left/right windows and absolute-price tolerance.
A swing high must be strictly higher than every high in both windows; a swing low
must be strictly lower than every low. Equal extrema are excluded. Only closed
bars participate. A pivot's time identifies the extreme; its availability time
identifies the close of the last required right-hand bar. These times must not be
confused in analysis or replay. Developing bars cannot confirm historical pivots.

Same-side confirmed pivots supply alternative support or resistance lines using
the existing `TrendlineAnchor` geometry. Touches and closed-price breaks are
measured against the explicit tolerance. A closed price breaking through the line
invalidates that candidate; a wick alone is not a closed-price break. Candidates
are hypotheses and can disagree. There is no automatic winning line or entry
recommendation. Returned anchors can be passed to the existing chart annotation
path, whose ownership and revision checks still apply. Chart inspection verifies
the resulting drawing; measurement alone does not place it on a chart.

Results retain the exact symbol/timeframe, source hashes, input coverage,
confirmation boundaries and health assessment. Relevant corrected source bars
change the proof. A stale, mixed, unordered, duplicate or future series fails
explicitly. Insufficient healthy closed history produces no confirmed pivots.
The analyzer does not infer continuous trading across missing intervals, broker
sessions or holidays. These limitations remain visible in its result.

The bounded history and output counts limit computation/context, not trading
authority. Decimal prices are preserved. The same calculation supports forex,
metals, indices and crypto without pair-specific rules or suffix removal. It is
not a backtest, profitability proof, full formation catalog or financial approval.
