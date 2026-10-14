import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";

function fixture(data) {
  return JSON.parse(
    execFileSync(".venv/bin/python", ["tests/check_chart_browser.py"], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}

test("Expo renders durable live candles from the authenticated server event stream", async ({
  page,
  context,
}) => {
  const data = fixture({ action: "init" });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let sockets = 0;
  page.on("websocket", (socket) => {
    if (socket.url().includes("/api/ws/events")) {
      sockets++;
      expect(new URL(socket.url()).searchParams.has("token")).toBe(false);
    }
  });
  try {
    await context.addCookies(
      data.cookies.map((cookie) => ({
        ...cookie,
        url: test.info().project.use.baseURL,
        httpOnly: cookie.name === "lonora_session",
        sameSite: "Strict",
      })),
    );
    await page.goto("/charts");
    await page.getByRole("button", { name: `${data.symbol} · 15m`, exact: true }).click();
    const image = page.getByRole("img", { name: `${data.symbol} · 15m`, exact: true });
    await expect(image).toBeVisible();
    await expect.poll(() => sockets).toBeGreaterThan(0);
    const before = await image.screenshot();
    const publication = fixture({ ...data, action: "live", close: "250" });
    expect(publication.candles.at(-1).close).toBe("250");
    await expect(page.getByText(/C (250|٢٥٠)/)).toBeVisible();
    expect((await image.screenshot()).equals(before)).toBe(false);
    await page.reload();
    await page.getByRole("button", { name: `${data.symbol} · 15m`, exact: true }).click();
    await expect(page.getByText(/C (250|٢٥٠)/)).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    fixture({ ...data, action: "cleanup" });
  }
});
