export function formatCryptoAmount(value) {
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) return "0";
  const maximumFractionDigits = Math.abs(amount) < 1 ? 8 : 6;
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits
  }).format(amount);
}

// Products are priced in fiat (USD). Render as a currency amount, e.g. "$30.00".
export function formatFiatAmount(value, currency = "USD") {
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) return "";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD"
  }).format(amount);
}

// "≈ 0.01 ETH / 30 USDC" hint built from the server's per-asset converted amounts.
export function formatAssetPriceHint(assetPrices, { max = 3 } = {}) {
  if (!assetPrices) return "";
  const entries = Object.values(assetPrices)
    .filter((asset) => asset && asset.amount != null)
    .slice(0, max)
    .map((asset) => `${formatCryptoAmount(asset.amount)} ${asset.symbol}`);
  return entries.length ? `≈ ${entries.join(" / ")}` : "";
}
