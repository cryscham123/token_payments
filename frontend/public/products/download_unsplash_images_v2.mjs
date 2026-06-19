#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";

const ACCESS_KEY = process.env.UNSPLASH_ACCESS_KEY;

const args = process.argv.slice(2);

function getArg(name, fallback) {
  const idx = args.indexOf(name);
  return idx >= 0 ? args[idx + 1] : fallback;
}

const manifestPath = getArg("--manifest", "IMAGE_MANIFEST.md");
const publicRoot = getArg("--public-root", "..");
const offset = Number(getArg("--offset", "0"));
const limit = Number(getArg("--limit", "50"));
const force = args.includes("--force");
const dryRun = args.includes("--dry-run");

if (!ACCESS_KEY && !dryRun) {
  console.error("UNSPLASH_ACCESS_KEY is required");
  process.exit(1);
}

function parseManifest(text) {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim().startsWith("| `products/"))
    .map((line) => {
      const cells = line
        .split("|")
        .map((x) => x.trim())
        .filter(Boolean);

      const filePath = cells[0].match(/`([^`]+)`/)?.[1];
      const productName = cells[1];

      return { filePath, productName };
    })
    .filter((x) => x.filePath && x.productName);
}

function buildQuery(productName) {
  return productName
    .replace(/\b(pack|set|kit|pair|trio|duo|mini|pro)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
}

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function unsplashJson(url) {
  const res = await fetch(url, {
    headers: {
      Authorization: `Client-ID ${ACCESS_KEY}`,
      "Accept-Version": "v1",
    },
  });

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${body}`);
  }

  return res.json();
}

async function downloadFile(url, outPath) {
  const res = await fetch(url);

  if (!res.ok) {
    throw new Error(`image download failed: ${res.status} ${res.statusText}`);
  }

  const buf = Buffer.from(await res.arrayBuffer());
  await fs.mkdir(path.dirname(outPath), { recursive: true });
  await fs.writeFile(outPath, buf);
}

async function main() {
  const text = await fs.readFile(manifestPath, "utf8");
  const allItems = parseManifest(text);
  const items = allItems.slice(offset, offset + limit);

  console.log(`manifest items: ${allItems.length}`);
  console.log(`processing offset=${offset}, limit=${limit}`);
  console.log(`public root: ${publicRoot}`);
  console.log("");

  let ok = 0;
  let skipped = 0;
  let failed = 0;

  for (let i = 0; i < items.length; i++) {
    const item = items[i];
    const index = offset + i;
    const outPath = path.join(publicRoot, item.filePath);
    const query = buildQuery(item.productName);

    if (!force && await exists(outPath)) {
      skipped++;
      console.log(`[${index}] SKIP ${item.filePath}`);
      continue;
    }

    if (dryRun) {
      console.log(`[${index}] DRY query="${query}" -> ${outPath}`);
      continue;
    }

    try {
      const searchUrl = new URL("https://api.unsplash.com/search/photos");
      searchUrl.searchParams.set("query", query);
      searchUrl.searchParams.set("per_page", "1");
      searchUrl.searchParams.set("orientation", "squarish");

      const search = await unsplashJson(searchUrl);
      const photo = search.results?.[0];

      if (!photo) {
        failed++;
        console.log(`[${index}] NO RESULT query="${query}"`);
        continue;
      }

      if (photo.links?.download_location) {
        const trackUrl = new URL(photo.links.download_location);
        trackUrl.searchParams.set("client_id", ACCESS_KEY);
        await fetch(trackUrl);
      }

      const imageUrl = photo.urls.regular || photo.urls.small || photo.urls.full;
      await downloadFile(imageUrl, outPath);

      ok++;
      console.log(`[${index}] OK ${item.filePath} <- "${query}"`);
    } catch (err) {
      failed++;
      console.error(`[${index}] FAIL ${item.filePath}`);
      console.error(err.message);

      if (err.message.includes("429")) {
        console.error("rate limit reached");
        break;
      }
    }
  }

  console.log("");
  console.log(`done: ok=${ok}, skipped=${skipped}, failed=${failed}`);
}

main();
