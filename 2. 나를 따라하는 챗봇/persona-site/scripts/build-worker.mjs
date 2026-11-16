import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const require = createRequire(import.meta.url);
const prompts = require(resolve(root, "lib/prompts.js"));
const source = await readFile(resolve(root, "worker/runtime.js"), "utf8");
const index = await readFile(resolve(root, "public/index.html"), "utf8");
const admin = await readFile(resolve(root, "public/admin.html"), "utf8");
const promptLiteral = `{${Object.entries(prompts).map(([key, value]) => `${key}:${typeof value === "function" ? value.toString() : JSON.stringify(value)}`).join(",")}}`;
const built = source
  .replace("__INDEX_HTML__", JSON.stringify(index))
  .replace("__ADMIN_HTML__", JSON.stringify(admin))
  .replace("__PROMPTS__", promptLiteral);
await writeFile(resolve(root, "worker/index.js"), built);
console.log("Prepared Sites Worker from public pages and chat prompts.");
