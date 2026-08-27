import { readFile } from "node:fs/promises";
import { basename } from "node:path";
import { gzipSync } from "node:zlib";

const distDir = new URL("../dist/", import.meta.url);
const html = await readFile(new URL("index.html", distDir), "utf8");
const entryMatch = html.match(/<script[^>]+src="([^"]+)"/);
if (!entryMatch) throw new Error("Unable to find the production entry script");

const preloadPaths = [
  ...html.matchAll(/rel="modulepreload"[^>]+href="([^"]+)"/g),
].map((match) => match[1]);
const paths = [entryMatch[1], ...preloadPaths];
const uniquePaths = [...new Set(paths)];
const assets = await Promise.all(
  uniquePaths.map(async (assetPath) => {
    const file = new URL(assetPath.replace(/^\//, ""), distDir);
    const content = await readFile(file);
    return {
      name: basename(assetPath),
      gzipBytes: gzipSync(content).byteLength,
    };
  }),
);

const totalGzipBytes = assets.reduce(
  (total, asset) => total + asset.gzipBytes,
  0,
);
const limits = {
  totalPreloadedGzipBytes: 220 * 1024,
  entryGzipBytes: 25 * 1024,
};
const entry = assets[0];

console.log(
  assets
    .map(
      (asset) =>
        `${asset.name}: ${(asset.gzipBytes / 1024).toFixed(2)} KiB gzip`,
    )
    .join("\n"),
);
console.log(
  `total preloaded JS: ${(totalGzipBytes / 1024).toFixed(2)} KiB gzip`,
);

if (entry.gzipBytes > limits.entryGzipBytes) {
  throw new Error(
    `Entry bundle exceeds ${limits.entryGzipBytes / 1024} KiB gzip budget`,
  );
}
if (totalGzipBytes > limits.totalPreloadedGzipBytes) {
  throw new Error(
    `Preloaded JavaScript exceeds ${limits.totalPreloadedGzipBytes / 1024} KiB gzip budget`,
  );
}
