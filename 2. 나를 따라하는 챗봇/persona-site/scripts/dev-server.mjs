import { createServer } from 'node:http';
import { readFile, writeFile, mkdir, readdir, rm } from 'node:fs/promises';
import { resolve, dirname, relative } from 'node:path';
import { pathToFileURL } from 'node:url';
import { execFileSync } from 'node:child_process';

const root = resolve(import.meta.dirname, '..');
execFileSync(process.execPath, [resolve(root, 'scripts/build-worker.mjs')]);
const worker = (await import(pathToFileURL(resolve(root, 'worker/index.js')).href + '?t=' + Date.now())).default;
const dataRoot = resolve(root, '.local-data');
const bucket = {
  async get(key) { try { const text = await readFile(resolve(dataRoot, key), 'utf8'); return { json: async () => JSON.parse(text) }; } catch (e) { if (e.code === 'ENOENT') return null; throw e; } },
  async put(key, value) { const file = resolve(dataRoot, key); await mkdir(dirname(file), { recursive: true }); await writeFile(file, value); },
  async list({ prefix, cursor, limit = 1000 }) { const files = []; async function walk(dir) { for (const ent of await readdir(dir, { withFileTypes: true }).catch(() => [])) { const p = resolve(dir, ent.name); if (ent.isDirectory()) await walk(p); else files.push(relative(dataRoot, p).replaceAll('\\', '/')); } } await walk(dataRoot); const matches = files.filter(x => x.startsWith(prefix)).sort(); const start = cursor ? Number(cursor) : 0; return { objects: matches.slice(start, start + limit).map(key => ({ key })), truncated: start + limit < matches.length, cursor: String(start + limit) }; },
  async delete(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) await rm(resolve(dataRoot, key), { force: true }); },
};
const envFile = await readFile(resolve(root, '..', '.env'), 'utf8').catch(() => '');
const apiKey = envFile.match(/^\s*anthropic_api_key\s*=\s*(.+)\s*$/im)?.[1]?.trim().replace(/^['"]|['"]$/g, '');
const env = { BUCKET: bucket, ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY || apiKey, ADMIN_PASSWORD: process.env.ADMIN_PASSWORD || 'local-admin', LOCAL_TEST_MODE: true };
createServer(async (req, res) => { try { const chunks = []; for await (const c of req) chunks.push(c); const response = await worker.fetch(new Request(`http://localhost:3000${req.url}`, { method: req.method, headers: req.headers, body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks) }), env); res.writeHead(response.status, Object.fromEntries(response.headers)); res.end(Buffer.from(await response.arrayBuffer())); } catch (e) { res.writeHead(500); res.end('Local server error'); console.error(e); } }).listen(3000, '127.0.0.1', () => console.log('Local site: http://127.0.0.1:3000  Admin: http://127.0.0.1:3000/admin.html  Password: local-admin'));
