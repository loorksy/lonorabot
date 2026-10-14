import { randomUUID } from "node:crypto";
import { expect } from "@playwright/test";
export async function brokerFixture(context, headers) {
  const symbol = "EURUSD.test";
  const connected = await context.request.post("/api/trading/connections", {
    headers,
    data: { provider: "simulation", account_id: `ui-pair-${randomUUID()}`, enabled: true },
  });
  expect(connected.status()).toBe(201);
  const account = await connected.json();
  const imported = await context.request.post(`/api/trading/connections/${account.id}/simulation`, {
    headers,
    data: {
      snapshot: {
        balance: "10000",
        currency: "USD",
        instruments: [
          {
            symbol,
            digits: 5,
            tick_size: "0.00001",
            volume_min: "0.01",
            volume_max: "100",
            volume_step: "0.01",
          },
        ],
      },
    },
  });
  expect(imported.ok()).toBeTruthy();
  return {
    account: account.id,
    symbol,
    binding: { trading_account_id: account.id, trading_symbol: symbol },
    close: () => context.request.delete(`/api/trading/connections/${account.id}`, { headers }),
  };
}
