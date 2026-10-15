import { spawnSync } from "node:child_process"
import { resolve } from "node:path"

const GENERATOR = "openapi-typescript@7.13.0"
const source = process.env.API_SCHEMA_URL ?? "http://localhost:8000/openapi.json"
const target = resolve(import.meta.dirname, "..", "src", "shared", "api", "schema.gen.ts")

const result = spawnSync("npx", ["--yes", GENERATOR, source, "--output", target], {
  stdio: "inherit",
  shell: process.platform === "win32",
})
if (result.status !== 0) process.stderr.write(`api:types: could not read ${source}\n`)
process.exitCode = result.status ?? 1
