export function paymentOptionsFromItems(items) {
  const optionSets = items.map(paymentOptionsForItem).filter((options) => options.length > 0);
  if (optionSets.length === 0) return [];
  return optionSets.slice(1).reduce(
    (common, options) => common.filter((option) => options.some((candidate) => candidate.key === option.key)),
    uniqueOptions(optionSets[0])
  );
}

export function paymentOptionsForItem(item) {
  const capability = item.paymentCapability || {};
  const chainLabels = chainLabelMap(capability);
  const acceptedAssets = Array.isArray(capability.acceptedAssets) ? capability.acceptedAssets : [];
  if (acceptedAssets.length > 0) return uniqueOptions(acceptedAssets.map((asset) => paymentOptionFromAsset(asset, chainLabels)).filter(Boolean));

  const assets = Array.isArray(capability.assets) ? capability.assets : [];
  if (assets.length > 0) return uniqueOptions(assets.map((asset) => paymentOptionFromAsset(asset, chainLabels)).filter(Boolean));

  const chainId = Number(item.cryptoChainId || 0);
  if (!chainId) return [];
  return [
    {
      key: `${item.cryptoSymbol}:${chainId}:${item.cryptoTokenAddress || "native"}`,
      paymentAssetId: "",
      symbol: item.cryptoSymbol || "ETH",
      chainId,
      tokenAddress: item.cryptoTokenAddress || null,
      decimals: item.cryptoDecimals || 18,
      assetType: item.cryptoTokenAddress ? "ERC20" : "NATIVE",
      chainLabel: chainLabels.get(chainId) || `Chain ${chainId}`,
      label: `${item.cryptoSymbol || "ETH"} · ${chainLabels.get(chainId) || `Chain ${chainId}`}`
    }
  ];
}

export function isActiveWallet(wallet) {
  return wallet && wallet.verificationStatus === "VERIFIED" && !wallet.revokedAt;
}

export function walletLabel(wallet) {
  return `${shortWallet(wallet.walletAddress)} · Chain ${wallet.chainId}${wallet.primary ? " · Primary" : ""}`;
}

export function shortWallet(value = "") {
  return value.length > 12 ? `${value.slice(0, 6)}...${value.slice(-4)}` : value;
}

function paymentOptionFromAsset(asset, chainLabels) {
  const chainId = Number(asset.chainId || 0);
  const symbol = asset.symbol || "TOKEN";
  if (!chainId) return null;
  const tokenAddress = asset.tokenContract?.address || asset.tokenAddress || null;
  const assetType = asset.assetType || (tokenAddress ? "ERC20" : "NATIVE");
  const paymentAssetId = assetType === "NATIVE" ? "" : asset.assetId || "";
  const key = paymentAssetId || `${symbol}:${chainId}:${tokenAddress || "native"}`;
  const chainLabel = chainLabels.get(chainId) || `Chain ${chainId}`;
  return {
    key,
    paymentAssetId,
    symbol,
    chainId,
    tokenAddress,
    decimals: asset.decimals || 18,
    assetType,
    chainLabel,
    label: `${symbol} · ${chainLabel}${assetType === "ERC20" ? " · ERC-20" : ""}`
  };
}

function chainLabelMap(capability) {
  const labels = new Map();
  for (const chain of capability.supportedChains || []) {
    if (chain?.chainId) labels.set(Number(chain.chainId), chain.displayName || `Chain ${chain.chainId}`);
  }
  for (const chainId of capability.supportedChainIds || []) {
    labels.set(Number(chainId), labels.get(Number(chainId)) || `Chain ${chainId}`);
  }
  return labels;
}

function uniqueOptions(options) {
  const seen = new Set();
  return options.filter((option) => {
    if (!option || seen.has(option.key)) return false;
    seen.add(option.key);
    return true;
  });
}
