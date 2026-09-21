import { gunzipSync, inflateRawSync } from "node:zlib";

function matches(name, executable) {
  const normalized = name.replaceAll("\\", "/");
  return normalized === executable || normalized.endsWith(`/${executable}`);
}

function fromTarGz(archive, executable) {
  const tar = gunzipSync(archive);
  for (let offset = 0; offset + 512 <= tar.length;) {
    const header = tar.subarray(offset, offset + 512);
    if (header.every((byte) => byte === 0)) break;
    const name = header.toString("utf8", 0, 100).split("\0", 1)[0];
    const prefix = header.toString("utf8", 345, 500).split("\0", 1)[0];
    const path = prefix ? `${prefix}/${name}` : name;
    const size = Number.parseInt(header.toString("ascii", 124, 136).split("\0", 1)[0].trim(), 8);
    const start = offset + 512;
    if (!Number.isSafeInteger(size) || size < 0 || start + size > tar.length) {
      throw new Error("uv release tar archive is malformed");
    }
    if ((header[156] === 0 || header[156] === 48) && matches(path, executable)) {
      return Buffer.from(tar.subarray(start, start + size));
    }
    offset = start + Math.ceil(size / 512) * 512;
  }
  throw new Error("uv binary was missing from its release archive");
}

function fromZip(archive, executable) {
  let end = -1;
  for (let offset = archive.length - 22; offset >= Math.max(0, archive.length - 65557); offset--) {
    if (archive.readUInt32LE(offset) === 0x06054b50) {
      end = offset;
      break;
    }
  }
  if (end < 0) throw new Error("uv release zip archive is malformed");
  const count = archive.readUInt16LE(end + 10);
  let offset = archive.readUInt32LE(end + 16);
  for (let index = 0; index < count; index++) {
    if (offset + 46 > archive.length || archive.readUInt32LE(offset) !== 0x02014b50) {
      throw new Error("uv release zip directory is malformed");
    }
    const method = archive.readUInt16LE(offset + 10);
    const compressedSize = archive.readUInt32LE(offset + 20);
    const size = archive.readUInt32LE(offset + 24);
    const nameLength = archive.readUInt16LE(offset + 28);
    const extraLength = archive.readUInt16LE(offset + 30);
    const commentLength = archive.readUInt16LE(offset + 32);
    const name = archive.toString("utf8", offset + 46, offset + 46 + nameLength);
    if (matches(name, executable)) {
      const local = archive.readUInt32LE(offset + 42);
      if (local + 30 > archive.length || archive.readUInt32LE(local) !== 0x04034b50) {
        throw new Error("uv release zip entry is malformed");
      }
      const start = local + 30 + archive.readUInt16LE(local + 26) + archive.readUInt16LE(local + 28);
      if (start + compressedSize > archive.length) throw new Error("uv release zip entry is truncated");
      const compressed = archive.subarray(start, start + compressedSize);
      const binary = method === 0 ? Buffer.from(compressed) : method === 8 ? inflateRawSync(compressed) : null;
      if (!binary || binary.length !== size) throw new Error("uv release zip entry could not be extracted");
      return binary;
    }
    offset += 46 + nameLength + extraLength + commentLength;
  }
  throw new Error("uv binary was missing from its release archive");
}

export function extractUvBinary(archive, filename) {
  return filename.endsWith(".zip") ? fromZip(archive, "uv.exe") : fromTarGz(archive, "uv");
}
