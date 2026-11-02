/** Evidence from the real avatar markup/controller, with no duplicate face renderer.
 * node scripts/capture-avatar-refinement.mjs --phase before --before .runtime/face-refinement/before-motion.js
 * node scripts/capture-avatar-refinement.mjs --phase after --before .runtime/face-refinement/before-motion.js
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { inflateSync } from "node:zlib";
import { chromium } from "@playwright/test";

/** Inspect browser PNG pixels without an image-processing dependency or altering them. */
function decodeScreenshotPng(buffer) {
  assert.equal(buffer.toString("hex", 0, 8), "89504e470d0a1a0a");
  let width = 0,
    height = 0,
    channels = 0;
  const chunks = [];
  for (let offset = 8; offset < buffer.length; ) {
    const length = buffer.readUInt32BE(offset),
      type = buffer.toString("ascii", offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === "IHDR") {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      assert.equal(data[8], 8, "Expected an 8-bit browser screenshot");
      channels = data[9] === 6 ? 4 : data[9] === 2 ? 3 : 0;
      assert(channels, "Expected RGB/RGBA browser screenshot");
      assert.equal(data[12], 0, "Expected a non-interlaced browser screenshot");
    } else if (type === "IDAT") chunks.push(data);
    offset += length + 12;
  }
  const stride = width * channels,
    raw = inflateSync(Buffer.concat(chunks)),
    pixels = new Uint8Array(stride * height);
  assert.equal(raw.length, (stride + 1) * height);
  const paeth = (a, b, c) => {
    const p = a + b - c,
      pa = Math.abs(p - a),
      pb = Math.abs(p - b),
      pc = Math.abs(p - c);
    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
  };
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    assert(filter <= 4, "Unknown PNG row filter");
    for (let x = 0; x < stride; x++) {
      const left = x >= channels ? pixels[y * stride + x - channels] : 0;
      const up = y ? pixels[(y - 1) * stride + x] : 0;
      const corner = y && x >= channels ? pixels[(y - 1) * stride + x - channels] : 0;
      const predict = [0, left, up, Math.floor((left + up) / 2), paeth(left, up, corner)][filter];
      pixels[y * stride + x] = (raw[y * (stride + 1) + x + 1] + predict) & 255;
    }
  }
  return { width, height, channels, pixels };
}

const flags = Object.fromEntries(
  process.argv.slice(2).reduce((rows, value, i, values) => {
    if (value.startsWith("--")) rows.push([value.slice(2), values[i + 1]]);
    return rows;
  }, []),
);
const phase = flags.phase ?? "after";
assert(["before", "after"].includes(phase), "Use --phase before or after");
const output = resolve(flags.output ?? "docs/visual/avatar-refinement");
const beforePath = resolve(flags.before ?? ".runtime/face-refinement/before-motion.js");
const currentPath = resolve("packages/core/src/trading-avatar-motion.js");
const css = await readFile("packages/ui-web/src/trading-avatar.css", "utf8");
const before = await readFile(beforePath, "utf8");
const current = phase === "after" ? await readFile(currentPath, "utf8") : before;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: "/usr/bin/chromium", headless: true });
const context = await browser.newContext({
  viewport: { width: 1500, height: 1000 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
const pageErrors = [];
page.on("pageerror", (error) => pageErrors.push(error.message));
try {
  await page.setContent(`<meta charset="utf-8"><style>${css}
    *{box-sizing:border-box}body{margin:0;padding:24px;background:#090b0e;color:#f4f4f5;font:13px/1.4 system-ui,sans-serif}
    h1{margin:0 0 6px;font-size:22px}h2{font-size:15px;margin:0 0 16px}p{margin:0 0 20px;color:#a1a1aa;font-size:12px}
    .evidence{width:max-content;max-width:1452px;padding:24px;background:#0c0e12;border:1px solid #25272d;border-radius:20px}
    .columns{display:flex;align-items:flex-start;gap:32px}.grid{display:grid;grid-template-columns:repeat(4, minmax(0,1fr));gap:18px 16px}
    .card{display:flex;flex-direction:column;align-items:center;gap:8px;min-width:110px;text-align:center}.caption{font-size:11px;color:#b8bbc5;max-width:135px}
    .avatar-wrap{position:relative;display:inline-flex}.mta-avatar{--mta-primary:#8B5CF6}.guides{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible}
    .scale-row{display:flex;gap:18px;align-items:flex-end}.scale-cell{min-width:65px;display:flex;flex-direction:column;align-items:center;gap:8px}
    .pair-grid{display:grid;grid-template-columns:repeat(4, 152px);gap:24px}.pair{display:flex;flex-direction:column;gap:12px;align-items:center}.pair-smalls{display:flex;align-items:center;gap:8px}
    .state-row{display:flex;gap:20px;align-items:center}.transition-note{max-width:800px}
  </style><main class="evidence" id="capture"></main>`);
  await page.evaluate(
    async ({ beforeUrl, currentUrl }) => {
      window.avatarEvidence = {
        before: await import(beforeUrl),
        after: await import(currentUrl),
        controllers: [],
        counter: 0,
      };
    },
    {
      beforeUrl: `data:text/javascript;base64,${Buffer.from(before).toString("base64")}`,
      currentUrl: `data:text/javascript;base64,${Buffer.from(current).toString("base64")}`,
    },
  );
  async function render({
    title,
    subtitle,
    sets,
    size = 96,
    guides = false,
    colors,
    paired = false,
    defaultOnly = false,
  }) {
    await page.evaluate(
      ({ title, subtitle, sets, size, guides, colors, paired, defaultOnly }) => {
        const evidence = window.avatarEvidence;
        for (const controller of evidence.controllers) controller.destroy();
        evidence.controllers = [];
        const capture = document.getElementById("capture");
        capture.replaceChildren();
        const heading = document.createElement("h1");
        heading.textContent = title;
        capture.append(heading);
        const note = document.createElement("p");
        note.textContent = subtitle;
        capture.append(note);
        const columns = document.createElement("div");
        columns.className = "columns";
        capture.append(columns);
        function avatar(engine, id, dimension, quality = "lite", color = "#8B5CF6") {
          const wrap = document.createElement("div");
          wrap.className = "avatar-wrap";
          wrap.style.width = `${dimension}px`;
          wrap.style.height = `${dimension}px`;
          const root = document.createElement("span");
          root.className = "mta-avatar";
          root.style.width = `${dimension}px`;
          root.style.height = `${dimension}px`;
          root.style.setProperty("--mta-primary", color);
          root.innerHTML = engine.markup(`evidence-${++evidence.counter}`, quality);
          const controller = engine.mount(root, {
            face: id,
            state: "waiting",
            identity: "geometry-review",
            paused: true,
            look: "off",
            interactive: false,
          });
          controller.seek(0.3, 0, 0);
          evidence.controllers.push(controller);
          wrap.append(root);
          if (guides && evidence.after.FACIAL_GEOMETRY) {
            const geometry = evidence.after.FACIAL_GEOMETRY,
              shell = engine.GEOMETRY.shell,
              display = engine.GEOMETRY.face;
            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.classList.add("guides");
            svg.setAttribute("viewBox", engine.GEOMETRY.viewBox);
            const line = (x1, y1, x2, y2, color) => {
              const node = document.createElementNS(svg.namespaceURI, "line");
              for (const [key, value] of Object.entries({
                x1,
                y1,
                x2,
                y2,
                stroke: color,
                "stroke-width": 1,
                "stroke-dasharray": "4 4",
              }))
                node.setAttribute(key, String(value));
              svg.append(node);
            };
            const rectangle = (area, color) => {
              if (!area) return;
              const node = document.createElementNS(svg.namespaceURI, "rect");
              for (const [key, value] of Object.entries({
                x: area.x,
                y: area.y,
                width: area.width,
                height: area.height,
                rx: area.rx ?? 0,
                fill: "none",
                stroke: color,
                "stroke-width": 1.3,
              }))
                node.setAttribute(key, String(value));
              svg.append(node);
            };
            rectangle(display, "#6bb3d166");
            const safe = geometry.safeArea ?? geometry.facialSafeArea ?? geometry.expressionBounds;
            if (safe?.x !== undefined) rectangle(safe, "#f4bf5699");
            line(shell.cx, display.y, shell.cx, display.y + display.height, "#e7b0ff88");
            const projectAnchor = (anchor) => ({
              x: shell.cx + (anchor.x - shell.cx) * engine.GLYPH_SCALE,
              y:
                engine.GEOMETRY.centerY + (anchor.y - engine.GEOMETRY.centerY) * engine.GLYPH_SCALE,
            });
            const eyes = geometry.eyeAnchors;
            const anchors = Array.isArray(eyes) ? eyes : eyes ? [eyes.left, eyes.right] : [];
            for (const anchor of anchors) {
              if (anchor?.x === undefined) continue;
              const rendered = projectAnchor(anchor);
              line(rendered.x - 8, rendered.y, rendered.x + 8, rendered.y, "#92ecc9");
              line(rendered.x, rendered.y - 8, rendered.x, rendered.y + 8, "#92ecc9");
            }
            const mouth = geometry.mouthAnchor;
            if (mouth?.x !== undefined) {
              const rendered = projectAnchor(mouth);
              line(rendered.x - 10, rendered.y, rendered.x + 10, rendered.y, "#f1a0b8");
            }
            wrap.append(svg);
          }
          return wrap;
        }
        for (const set of sets) {
          const section = document.createElement("section");
          const label = document.createElement("h2");
          label.textContent = set.label;
          section.append(label);
          const grid = document.createElement("div");
          grid.className = paired ? "pair-grid" : "grid";
          section.append(grid);
          columns.append(section);
          const engine = evidence[set.engine];
          const options = defaultOnly ? [engine.AVATAR_FACES[0]] : engine.AVATAR_FACES;
          if (colors) {
            for (const color of colors) {
              const card = document.createElement("div");
              card.className = "card";
              card.append(avatar(engine, "face-smile", size, "lite", color));
              const caption = document.createElement("div");
              caption.className = "caption";
              caption.textContent = color;
              card.append(caption);
              grid.append(card);
            }
          } else
            for (const option of options) {
              const card = document.createElement("div");
              card.className = paired ? "pair" : "card";
              if (paired) {
                card.append(avatar(engine, option.id, 128, "full"));
                const smalls = document.createElement("div");
                smalls.className = "pair-smalls";
                for (const dimension of [32, 40, 64])
                  smalls.append(avatar(engine, option.id, dimension));
                card.append(smalls);
              } else card.append(avatar(engine, option.id, size, defaultOnly ? "full" : "lite"));
              const caption = document.createElement("div");
              caption.className = "caption";
              caption.textContent = option.label;
              card.append(caption);
              grid.append(card);
            }
        }
      },
      { title, subtitle, sets, size, guides, colors, paired, defaultOnly },
    );
    await page.evaluate(() => document.fonts.ready);
  }
  const snapshots = [];
  async function screenshot(file) {
    const bytes = await page.locator("#capture").screenshot({ path: `${output}/${file}` });
    snapshots.push(file);
    return bytes;
  }
  if (phase === "before") {
    await render({
      title: "Lonora facial geometry — before",
      subtitle:
        "Original pre-refinement implementation · 96 CSS pixels · actual markup and controller · 1× device scale",
      sets: [{ engine: "before", label: "All 16 existing presets" }],
    });
    await screenshot("before-grid.png");
    await render({
      title: "Original Lonora signal avatar",
      subtitle:
        "256 CSS pixels · original shell/display/materials · baseline before facial refinement",
      sets: [{ engine: "before", label: "Original default" }],
      size: 256,
      defaultOnly: true,
    });
    await screenshot("original-default.png");
  } else {
    const geometry = await page.evaluate(() => ({
      before: window.avatarEvidence.before.GEOMETRY,
      after: window.avatarEvidence.after.GEOMETRY,
      face: window.avatarEvidence.after.FACIAL_GEOMETRY ?? null,
      tokens: window.avatarEvidence.after.FACE_TOKENS ?? null,
    }));
    assert.deepEqual(geometry.after, geometry.before, "Fundamental avatar geometry changed");
    await render({
      title: "Original default signal avatar — before",
      subtitle: "256px · identical controlled pose, palette, markup quality and viewport",
      sets: [{ engine: "before", label: "Original signal bars" }],
      size: 256,
      defaultOnly: true,
    });
    const originalSignalBefore = await page
      .locator(".mta-avatar")
      .screenshot({ path: `${output}/original-signal-before.png` });
    await render({
      title: "Original default signal avatar — after",
      subtitle: "256px · identical controlled pose, palette, markup quality and viewport",
      sets: [{ engine: "after", label: "Original signal bars" }],
      size: 256,
      defaultOnly: true,
    });
    const originalSignalAfter = await page
      .locator(".mta-avatar")
      .screenshot({ path: `${output}/original-signal-after.png` });
    assert.deepEqual(
      originalSignalAfter,
      originalSignalBefore,
      "Original signal avatar raster changed",
    );
    await render({
      title: "Lonora — one character, calibrated expressions",
      subtitle:
        "Before / after at identical 96 CSS pixels · real production markup/controller · same shell, display, colors and viewBox",
      sets: [
        { engine: "before", label: "Before — mixed feature weights" },
        { engine: "after", label: "After — canonical geometry" },
      ],
    });
    await screenshot("before-after-grid.png");
    await render({
      title: "Canonical facial alignment",
      subtitle:
        "Original display contour + centerline and shared anchors · 128 CSS pixels · guides are evidence-only overlays",
      sets: [{ engine: "after", label: "All 16 calibrated expressions" }],
      size: 128,
      guides: true,
    });
    await screenshot("alignment-guides.png");
    for (const size of [32, 40, 48, 64, 96, 128, 256]) {
      await render({
        title: `Lonora expressions at ${size}px`,
        subtitle:
          "Actual CSS pixel size · 1× device scale · same expression definitions and uniform SVG viewBox",
        sets: [{ engine: "after", label: `All 16 presets / ${size}px` }],
        size,
      });
      await screenshot(`expressions-${size}px.png`);
    }
    await render({
      title: "Large preview and thumbnails",
      subtitle:
        "Each row uses one saved expression ID · 128px full-quality preview with 32px / 40px / 64px actual thumbnails",
      sets: [{ engine: "after", label: "Shared implementation at every size" }],
      paired: true,
    });
    const previewPng = decodeScreenshotPng(await screenshot("preview-thumbnails.png"));
    const previewBounds = await page.evaluate(() => {
      const capture = document.getElementById("capture").getBoundingClientRect();
      return [...document.querySelectorAll(".pair > .avatar-wrap")].map((node) => {
        const rect = node.getBoundingClientRect();
        return {
          x: rect.x - capture.x,
          y: rect.y - capture.y,
          size: rect.width,
          face: node.querySelector(".mta-avatar").dataset.face,
        };
      });
    });
    const safe = geometry.face.facialSafeArea,
      viewBox = geometry.after.viewBox.split(" ").map(Number);
    const fullQualityWhitePixelCounts = previewBounds.map((rect) => {
      const scale = rect.size / viewBox[2];
      const left = Math.ceil(rect.x + (safe.x - viewBox[0]) * scale),
        top = Math.ceil(rect.y + (safe.y - viewBox[1]) * scale);
      const right = Math.floor(rect.x + (safe.x + safe.width - viewBox[0]) * scale),
        bottom = Math.floor(rect.y + (safe.y + safe.height - viewBox[1]) * scale);
      let count = 0;
      for (let y = top; y <= bottom; y++)
        for (let x = left; x <= right; x++) {
          const offset = (y * previewPng.width + x) * previewPng.channels;
          if (
            previewPng.pixels[offset] > 200 &&
            previewPng.pixels[offset + 1] > 200 &&
            previewPng.pixels[offset + 2] > 200
          )
            count++;
        }
      assert(
        count > 10,
        `${rect.face}: full-quality facial whites disappeared in the actual raster`,
      );
      return { face: rect.face, whitePixels: count };
    });
    await render({
      title: "User-selected shell colors",
      subtitle:
        "One canonical smiling face · facial white/teal language stays unchanged while shell colors vary",
      sets: [{ engine: "after", label: "Color customization / 96px" }],
      colors: [
        "#8B5CF6",
        "#F97316",
        "#06B6D4",
        "#10B981",
        "#FFFFFF",
        "#64748B",
        "#EF4444",
        "#EAB308",
      ],
    });
    await screenshot("shell-colors.png");
    await render({
      title: "Animated expression transitions",
      subtitle:
        "Actual shared controller · same sphere/display before, during and after selection · no replacement renderer",
      sets: [{ engine: "after", label: "Smile → Wink" }],
      size: 128,
      defaultOnly: true,
    });
    const motion = await page.evaluate(async () => {
      const e = window.avatarEvidence,
        root = document.querySelector(".mta-avatar"),
        controller = e.controllers[0];
      controller.setFace("face-smile");
      controller.setPaused(false);
      await new Promise((resolve) => setTimeout(resolve, 1100));
      const shell = root.querySelector(".mta-shell").outerHTML,
        display = root.querySelector(".mta-face").outerHTML;
      const paths = () =>
        [...root.querySelectorAll("[data-mta-bar]")].map((path) => path.getAttribute("d"));
      document.querySelector(".caption").textContent = "Smile → Wink (during morph)";
      const before = paths();
      controller.setFace("face-wink");
      const immediate = paths();
      await new Promise((resolve) => setTimeout(resolve, 420));
      const middle = paths();
      return { shell, display, before, immediate, middle };
    });
    assert.deepEqual(
      motion.immediate,
      motion.before,
      "Face switch jumped instead of starting from displayed geometry",
    );
    assert.notDeepEqual(motion.middle, motion.before, "Face transition did not animate");
    await screenshot("transition-mid-animation.png");
    await page.waitForTimeout(1100);
    const final = await page.evaluate(() => {
      const root = document.querySelector(".mta-avatar");
      return {
        shell: root.querySelector(".mta-shell").outerHTML,
        display: root.querySelector(".mta-face").outerHTML,
        face: root.dataset.face,
        finite: [...root.querySelectorAll("[data-mta-bar]")].every(
          (path) => !/NaN|Infinity/.test(path.getAttribute("d")),
        ),
      };
    });
    assert.equal(final.shell, motion.shell);
    assert.equal(final.display, motion.display);
    assert.equal(final.face, "face-wink");
    assert(final.finite);
    await page.emulateMedia({ reducedMotion: "reduce" });
    // Let the browser dispatch the media change before comparing stable frames.
    await page.evaluate(
      () => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))),
    );
    const still = await page.locator("[data-mta-bars]").innerHTML();
    await page.waitForTimeout(160);
    assert.equal(
      await page.locator("[data-mta-bars]").innerHTML(),
      still,
      "Reduced motion did not stay still",
    );
    await writeFile(
      `${output}/validation.json`,
      `${JSON.stringify(
        {
          sourceHashes: {
            before: createHash("sha256").update(before).digest("hex"),
            after: createHash("sha256").update(current).digest("hex"),
          },
          browser: browser.version(),
          geometry,
          fullQualityWhitePixelCounts,
          snapshots,
          checks: {
            originalGeometryUnchanged: true,
            originalSignalRasterByteIdentical: true,
            immediateTransitionContinuous: true,
            transitionAnimated: true,
            shellDisplayStableDuringTransition: true,
            reducedMotionStill: true,
            finitePaths: true,
            fullQualityFacialWhitesVisible: true,
          },
          pageErrors,
        },
        null,
        2,
      )}\n`,
    );
  }
  assert.deepEqual(pageErrors, [], "Browser rendering errors");
  console.log(JSON.stringify({ phase, output, snapshots, pageErrors }, null, 2));
} finally {
  await context.close();
  await browser.close();
}
