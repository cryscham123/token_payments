export function formatCryptoAmount(value) {
  const amount = Number.parseFloat(value);
  if (!Number.isFinite(amount)) return "0";
  const maximumFractionDigits = Math.abs(amount) < 1 ? 8 : 6;
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits
  }).format(amount);
}
