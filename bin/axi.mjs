#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
const argv = process.argv.slice(2);
if (argv.length === 1 && ["-v", "-V", "--version"].includes(argv[0])) {
  process.stdout.write(`${pkg.version}\n`);
  process.exit(0);
}

const python = join(root, ".axi-python", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
if (!existsSync(python)) {
  process.stdout.write(`error: ${pkg.name} Python runtime is missing\nhelp: Reinstall ${pkg.name} with npm scripts enabled\n`);
  process.exit(1);
}
const result = spawnSync(python, ["-m", pkg.axiPythonModule, ...argv], {
  stdio: "inherit",
  env: { ...process.env, AXI_COMMAND_PATH: process.argv[1] },
});
if (result.error) {
  process.stdout.write(`error: ${pkg.name} could not start its Python runtime\nhelp: Reinstall ${pkg.name}\n`);
  process.exit(1);
}
process.exit(result.status ?? (result.signal === "SIGINT" ? 130 : 1));
