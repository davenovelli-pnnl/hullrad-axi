import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { chmod, mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { extractUvBinary } from "./extract-uv.mjs";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const version = "0.12.19";
const uvDir = join(root, ".axi-uv");
const uv = join(uvDir, process.platform === "win32" ? "uv.exe" : "uv");
const venv = join(root, ".axi-python");
const python = join(venv, process.platform === "win32" ? "Scripts/python.exe" : "bin/python");

function archiveName() {
  const arch = { x64: "x86_64", arm64: "aarch64" }[process.arch];
  if (!arch) throw new Error(`unsupported CPU architecture: ${process.arch}`);
  if (process.platform === "darwin") return `uv-${arch}-apple-darwin.tar.gz`;
  if (process.platform === "win32") return `uv-${arch}-pc-windows-msvc.zip`;
  if (process.platform === "linux") {
    const libc = process.report.getReport().header.glibcVersionRuntime ? "gnu" : "musl";
    return `uv-${arch}-unknown-linux-${libc}.tar.gz`;
  }
  throw new Error(`unsupported operating system: ${process.platform}`);
}

async function download(base, archive) {
  const checksumResponse = await fetch(`${base}/${archive}.sha256`);
  if (!checksumResponse.ok) throw new Error(`checksum download returned ${checksumResponse.status}`);
  const checksum = (await checksumResponse.text()).trim().split(/\s+/, 1)[0];
  if (!/^[0-9a-f]{64}$/i.test(checksum)) throw new Error("release checksum is malformed");
  const archiveResponse = await fetch(`${base}/${archive}`);
  if (!archiveResponse.ok) throw new Error(`binary download returned ${archiveResponse.status}`);
  const bytes = Buffer.from(await archiveResponse.arrayBuffer());
  if (createHash("sha256").update(bytes).digest("hex") !== checksum.toLowerCase()) {
    throw new Error("uv release checksum did not match");
  }
  return bytes;
}

async function installUv() {
  const current = existsSync(uv) ? spawnSync(uv, ["--version"], { encoding: "utf8" }) : null;
  if (current?.status === 0 && current.stdout.trim() === `uv ${version}`) return;
  const archive = archiveName();
  const bases = [
    `https://releases.astral.sh/github/uv/releases/download/${version}`,
    `https://github.com/astral-sh/uv/releases/download/${version}`,
  ];
  let bytes;
  let lastError;
  for (const base of bases) {
    try {
      bytes = await download(base, archive);
      break;
    } catch (error) {
      lastError = error;
    }
  }
  if (!bytes) throw new Error(`could not download verified uv ${version}: ${lastError?.message}`);

  const binary = extractUvBinary(bytes, archive);
  await mkdir(uvDir, { recursive: true });
  await writeFile(uv, binary);
  if (process.platform !== "win32") await chmod(uv, 0o755);
}

function runUv(args) {
  const result = spawnSync(uv, args, {
    cwd: root,
    stdio: "inherit",
    env: { ...process.env, UV_PYTHON_INSTALL_DIR: join(root, ".axi-managed-python") },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`uv ${args[0]} failed with exit code ${result.status}`);
}

try {
  await installUv();
  runUv(["venv", "--clear", "--no-project", "--managed-python", "--python", "3.11", venv]);
  runUv(["pip", "install", "--python", python, root]);
} catch (error) {
  process.stderr.write(`Cannot install this AXI's Python runtime: ${error.message}\n`);
  process.exitCode = 1;
}
