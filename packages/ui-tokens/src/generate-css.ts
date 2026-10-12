import { writeFile } from "node:fs/promises";
import { appearance } from "./appearance";
const css=Object.entries(appearance).map(([theme,tokens])=>`[data-theme="${theme}"] {\n${Object.entries(tokens).map(([name,value])=>`  --${name}: ${value};`).join("\n")}\n}`).join("\n");
await writeFile(new URL("./tokens.css",import.meta.url),css+"\n");
