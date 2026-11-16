import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const source = await readFile(resolve(root, "dist/server/index.js"), "utf8");
const config = JSON.parse(await readFile(resolve(root, "dist/.openai/hosting.json"), "utf8"));
assert.equal(config.project_id, "appgprj_6af1d6e7d4c48191b08d052e1778ad9a");
assert.equal(config.r2, "BUCKET");
const mod = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
assert.equal(typeof mod.default?.fetch, "function");
console.log("Sites Worker artifact is valid.");
