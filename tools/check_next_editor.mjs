// Exercise the configured editor SDK over tsserver's actual editor protocol.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const settings = JSON.parse(readFileSync(join(root, ".vscode/settings.json"), "utf8"));
assert.equal(settings["js/ts.tsdk.path"], settings["typescript.tsdk"], "Current and legacy VS Code settings must select the same SDK");
assert.equal(settings["typescript.experimental.useTsgo"], false);
assert.equal(settings["js/ts.experimental.useTsgo"], false);
const sdk = resolve(root, settings["typescript.tsdk"]);
const serverPath = join(sdk, "tsserver.js");
assert.ok(readFileSync(serverPath).length, "The configured editor SDK must ship tsserver");

const source = [
  'import { useState } from "react";',
  'export const runtime = "invalid";',
  "export default function Page() { return useState(0)[0]; }",
].join("\n");

async function inspect(disablePlugin) {
  // Keep synthetic app files out of the real app and the production build.
  mkdirSync(join(root, ".next"), { recursive: true });
  const fixture = mkdtempSync(join(root, ".next/editor-plugin-"));
  const file = join(fixture, "app/page.tsx");
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, source);
  writeFileSync(join(fixture, "tsconfig.json"), JSON.stringify({
    extends: join(root, "tsconfig.json"),
    compilerOptions: disablePlugin ? { plugins: [] } : {},
    include: ["app/**/*.tsx"],
    exclude: ["node_modules"],
  }));

  const server = spawn(process.execPath, [serverPath, "--allowLocalPluginLoads", "--disableAutomaticTypingAcquisition"], {
    cwd: fixture,
    stdio: ["pipe", "pipe", "inherit"],
  });
  const exited = once(server, "exit");
  const lines = createInterface({ input: server.stdout });
  const pending = new Map();
  let sequence = 0;
  lines.on("line", (line) => {
    // Responses are Content-Length framed, with one JSON object on its own line.
    if (!line.startsWith("{")) return;
    const response = JSON.parse(line);
    if (response.type !== "response") return;
    const callback = pending.get(response.request_seq);
    if (!callback) return;
    pending.delete(response.request_seq);
    callback(response);
  });
  const request = (command, args) => new Promise((resolveResponse, reject) => {
    const seq = ++sequence;
    const timeout = setTimeout(() => reject(new Error(`tsserver timed out: ${command}`)), 30000);
    pending.set(seq, (response) => {
      clearTimeout(timeout);
      if (response.success) resolveResponse(response.body);
      else if (command === "completionInfo" && response.message === "No content available.") resolveResponse({ entries: [] });
      else reject(new Error(`${command}: ${response.message}`));
    });
    server.stdin.write(JSON.stringify({ seq, type: "request", command, arguments: args }) + "\n");
  });
  try {
    await request("open", { file, projectRootPath: fixture });
    const diagnostics = await request("semanticDiagnosticsSync", { file });
    const completions = await request("completionInfo", {
      file, line: 2, offset: source.split("\n")[1].indexOf("invalid") + 2,
    });
    return { diagnostics, completions };
  } finally {
    lines.close();
    server.kill();
    await exited;
    rmSync(fixture, { recursive: true, force: true });
  }
}

function assertNextFeatures({ diagnostics, completions }) {
  assert.ok(diagnostics.some(({ code }) => code === 71001), "Missing Next.js Server Component hook diagnostic (71001)");
  assert.ok(diagnostics.some(({ code }) => code === 71003), "Missing Next.js route runtime diagnostic (71003)");
  assert.ok(completions.entries.some(({ name, data }) => name === '"nodejs"' &&
    data?.moduleSpecifier === "next/typescript/entry_option_value"), "Missing Next.js route runtime completion");
}

// Falsifier: the same valid TypeScript without the plugin loses Next-only behavior.
const disabled = await inspect(true);
assert.equal(disabled.diagnostics.length, 0, "The synthetic source must be valid ordinary TypeScript");
assert.throws(() => assertNextFeatures(disabled), /Missing Next.js/);
assert.ok(!disabled.completions.entries.some(({ data }) => data?.moduleSpecifier?.startsWith("next/typescript/")));
assertNextFeatures(await inspect(false));
console.log("PASS: configured editor SDK provides Next.js diagnostics and completions; plugin-disabled negative control fails them.");
