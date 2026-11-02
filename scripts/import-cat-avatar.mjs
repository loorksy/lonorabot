/** Render the supplied index-13.html artwork into portable, transparent avatar shells.
 * Usage: node scripts/import-cat-avatar.mjs /path/to/index-13.html
 * Uses the existing Playwright dependency; no network, production services, or runtime GPU needed.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { deflateSync, inflateSync } from "node:zlib";
import { chromium } from "@playwright/test";

const sourceHash = "78730d07165f72f555db3874df1a9d0b2641a8bdced7fef41e7daca5f7e5e117";
assert(process.argv[2], "Pass the original index-13.html attachment as the first argument.");
const original = await readFile(resolve(process.argv[2]), "utf8");
assert.equal(
  createHash("sha256").update(original).digest("hex"),
  sourceHash,
  "Unexpected source artwork revision",
);
const meshLoop = "for(const m of meshList){\n const c=";
const apiStart = "window.avatar={setState:chooseState";
assert(original.includes(meshLoop) && original.includes(apiStart), "Capture anchors missing");
const html = original
  .replace(
    meshLoop,
    "for(const m of meshList){\n if(window.captureShell && (m.kind==='eyes'||m.kind==='signals'))continue;\n const c=",
  )
  .replace(
    apiStart,
    "window.captureShellFrame=(next)=>{setTheme(next);setMotion(false);yaw=targetYaw=pitch=targetPitch=aimX=aimY=gazeX=gazeY=0;window.captureShell=true;draw();const output=document.createElement('canvas');output.width=output.height=400;output.getContext('2d').drawImage(canvas,40,20,320,320,0,0,400,400);return output.toDataURL('image/png');};window.avatar={setState:chooseState",
  );

// Recompress IDAT bytes without changing any RGBA pixels (Chromium uses a fast PNG compressor).
function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}
function chunk(name, data) {
  const body = Buffer.concat([Buffer.from(name), data]);
  const length = Buffer.alloc(4),
    crc = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}
function recompress(png) {
  const chunks = [],
    idat = [];
  for (let at = 8; at < png.length; ) {
    const length = png.readUInt32BE(at),
      type = png.toString("ascii", at + 4, at + 8);
    const data = png.subarray(at + 8, at + 8 + length);
    if (type === "IDAT") idat.push(data);
    else if (type !== "IEND") chunks.push(chunk(type, data));
    at += length + 12;
  }
  return Buffer.concat([
    png.subarray(0, 8),
    ...chunks,
    chunk("IDAT", deflateSync(inflateSync(Buffer.concat(idat)), { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}
const browser = await chromium.launch({
  executablePath: process.env.LONORA_UI_TEST_BROWSER_PATH || "/usr/bin/chromium",
  headless: true,
  args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1400, height: 1200 },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
  });
  await page.setContent(html);
  await page.waitForFunction(() => window.avatar);
  await page.locator("#avatar").evaluate((canvas) => {
    canvas.style.width = "400px";
    canvas.style.height = "400px";
    canvas.style.maxWidth = "none";
  });
  const assets = {};
  await mkdir("packages/core/assets/cat-avatar", { recursive: true });
  for (const theme of ["night", "day"]) {
    const data = await page.evaluate((next) => window.captureShellFrame(next), theme);
    const png = recompress(Buffer.from(data.split(",")[1], "base64"));
    await writeFile(`packages/core/assets/cat-avatar/${theme}.png`, png);
    assets[theme] = `data:image/png;base64,${png.toString("base64")}`;
    console.log(`${theme}: ${png.length} bytes, 400×400 transparent shell`);
  }
  const stats = await page.evaluate(() => window.avatar.stats());
  assert.equal(stats.error, 0, "WebGL rendering failed");
  const file = `// Generated from the user-supplied index-13.html WebGL scene.\n// Source SHA256: ${sourceHash}\n// See scripts/import-cat-avatar.mjs for reproducible rendering.\nexport const CAT_AVATAR_ASSETS = ${JSON.stringify(assets, null, 2)} as const;\n`;
  await writeFile("packages/core/src/cat-avatar-assets.ts", file);
} finally {
  await browser.close();
}
