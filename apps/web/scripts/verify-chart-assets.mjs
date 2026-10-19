import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const root = new URL("../public/charting_library/", import.meta.url);
const manifest = JSON.parse(await readFile(new URL("asset-manifest.json", root), "utf8"));
const found = [];
async function verify(directory, prefix = "") {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = prefix + entry.name;
    if (entry.isDirectory()) await verify(new URL(`${entry.name}/`, directory), `${path}/`);
    else if (path !== "asset-manifest.json") {
      const data = await readFile(new URL(entry.name, directory));
      if (manifest.files[path] !== createHash("sha256").update(data).digest("hex"))
        throw new Error(`chart_asset_hash_mismatch:${path}`);
      found.push(path);
    }
  }
}
await verify(root);
if (found.length !== Object.keys(manifest.files).length)
  throw new Error("chart_asset_inventory_mismatch");
console.log(
  `Verified ${found.length} licensed TradingView ${manifest.version} assets at ${fileURLToPath(root)}`,
);
