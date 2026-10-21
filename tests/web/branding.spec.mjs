import { expect, test } from "@playwright/test";

test("site icons and install manifest serve real brand images rather than the SPA fallback", async ({
  page,
  context,
}) => {
  await page.goto("/");
  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute(
    "href",
    "/favicon.svg",
  );
  const logo = page.locator("img.brand-mark");
  await expect(logo).toBeVisible();
  expect(await logo.evaluate((image) => image.complete && image.naturalWidth > 0)).toBeTruthy();
  const manifestResponse = await context.request.get("/site.webmanifest");
  expect(manifestResponse.ok()).toBeTruthy();
  const manifest = await manifestResponse.json();
  expect(manifest.name).toBe("Lonora");
  expect(manifest.start_url).toBe("/app/");
  expect(manifest.icons.some((icon) => icon.purpose === "maskable")).toBeTruthy();
  for (const icon of manifest.icons) {
    const response = await context.request.get(icon.src);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).toContain("image/png");
    const bytes = await response.body();
    expect(bytes.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    expect(`${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`).toBe(icon.sizes);
  }
  for (const asset of [
    "/favicon.ico",
    "/favicon.svg",
    "/apple-touch-icon.png",
    "/brand/logo.svg",
    "/og-image-1200x630.png",
    "/twitter-card-1200x600.png",
  ]) {
    const response = await context.request.get(asset);
    expect(response.status()).toBe(200);
    expect(response.headers()["content-type"]).not.toContain("text/html");
  }
});
