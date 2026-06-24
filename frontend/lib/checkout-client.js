import { apiJson, newBrowserDeviceId } from "./auth-client";
import { products as demoProducts } from "./demo-data";

export async function createOrder({ storeId, publicStoreId, items, paymentAssetId, walletId }) {
  return apiJson("/orders", {
    method: "POST",
    idempotencyKey: newId("checkout"),
    body: {
      // Internal store UUID is redacted from public catalog reads; send the public id so the
      // server can resolve it. storeId is still sent when known (e.g. hardcoded demo store).
      ...(storeId ? { storeId } : {}),
      ...(publicStoreId ? { publicStoreId } : {}),
      deliveryAddress: {
        id: "local-browser-address",
        street: "Local browser checkout"
      },
      items: items.map((item) => {
        const productId = checkoutProductId(item);
        return {
          ...(productId ? { productId } : {}),
          ...(item.publicProductId ? { publicProductId: item.publicProductId } : {}),
          quantity: item.quantity,
          ...(item.publicVariantId ? { publicVariantId: item.publicVariantId } : {}),
          ...(item.selectedOptions ? { selectedOptions: item.selectedOptions } : {}),
          ...(item.thumb ? { thumb: item.thumb } : {}),
          ...(item.image ? { image: item.image } : {})
        };
      }),
      ...(paymentAssetId ? { paymentAssetId } : {}),
      ...(walletId ? { walletId } : {})
    }
  });
}

// Only return a value that is a real internal UUID. For products not in the hardcoded demo map
// this is empty, and the server resolves the order line from publicProductId instead.
function checkoutProductId(item) {
  return item.orderProductId || item.productId || demoProductIdForPublicId(item.publicProductId) || "";
}

function demoProductIdForPublicId(publicProductId) {
  return demoProducts.find((product) => product.publicProductId === publicProductId)?.id || "";
}

export async function getStoreProduct({ publicStoreId, publicProductId }) {
  return apiJson(`/stores/${encodeURIComponent(publicStoreId)}/products/${encodeURIComponent(publicProductId)}`, {
    method: "GET"
  });
}

export async function getCheckoutTracking(trackingId) {
  return apiJson(`/checkouts/tracking/${encodeURIComponent(trackingId)}`, { method: "GET" });
}

export async function submitTransactionHash({ trackingId, txHash }) {
  return apiJson("/payments/transaction-hashes", {
    method: "POST",
    idempotencyKey: `payment-submit-${trackingId}`,
    body: { trackingId, txHash }
  });
}

export async function cancelPayment({ trackingId }) {
  return apiJson("/payments/cancellations", {
    method: "POST",
    idempotencyKey: `payment-cancel-${trackingId}`,
    body: { trackingId }
  });
}

export async function completeOAuthSession({ provider, code, state, redirectUri }) {
  return apiJson(`/auth/oauth/${encodeURIComponent(provider)}/sessions`, {
    method: "POST",
    body: {
      code,
      state,
      redirectUri,
      deviceId: newBrowserDeviceId()
    }
  });
}

export async function sendPayment({ request, from }) {
  const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
  if (!ethereum?.request) throw new Error("MetaMask를 사용할 수 없습니다.");

  const amount = request.amount;
  const chainId = Number(request.chainId || amount.chainId);
  await ensureChain(chainId);

  if (amount.tokenAddress || request.tokenAddress || request.transferType === "ERC20_TRANSFER") {
    const tokenAddress = request.tokenAddress || amount.tokenAddress;
    if (!tokenAddress) throw new Error("ERC-20 토큰 주소를 받지 못했습니다.");
    return ethereum.request({
      method: "eth_sendTransaction",
      params: [
        {
          from,
          to: tokenAddress,
          value: "0x0",
          data: erc20TransferData(request.to, request.amountMinorUnits || toMinorUnits(amount.amount, amount.decimals || 18))
        }
      ]
    });
  }

  return ethereum.request({
    method: "eth_sendTransaction",
    params: [
      {
        from,
        to: request.to,
        value: toHexWei(amount.amount, amount.decimals || 18)
      }
    ]
  });
}

export async function sendNativePayment(args) {
  return sendPayment(args);
}

// RPC URL MetaMask should use for the local test network. MetaMask only accepts http for
// localhost; for any remote host it requires a trusted https endpoint. So on localhost we hit
// Ganache directly over http, and on a deployed host we go through the same-origin https
// /testnet-rpc proxy (which must have a trusted cert, e.g. Let's Encrypt — a self-signed cert
// is rejected by MetaMask).
export function localTestnetRpcUrl() {
  if (typeof window === "undefined") return "http://localhost:8545";
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") return "http://localhost:8545";
  return `${window.location.origin}/testnet-rpc`;
}

export async function ensureChain(chainId) {
  const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
  if (!ethereum?.request || !chainId) return;
  const current = await ethereum.request({ method: "eth_chainId" });
  const target = `0x${chainId.toString(16)}`;
  if (String(current).toLowerCase() === target.toLowerCase()) return;
  try {
    await ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: target }]
    });
  } catch (error) {
    if (Number(error?.code) !== 4902 || chainId !== 1337) throw error;
    await ethereum.request({
      method: "wallet_addEthereumChain",
      params: [
        {
          chainId: target,
          chainName: "Local Test Network",
          nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
          rpcUrls: [localTestnetRpcUrl()]
        }
      ]
    });
    await ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: target }]
    });
  }
}

function toHexWei(decimal, decimals) {
  return `0x${toMinorUnits(decimal, decimals).toString(16)}`;
}

function toMinorUnits(decimal, decimals) {
  const [whole, fraction = ""] = String(decimal).split(".");
  const padded = `${fraction}${"0".repeat(decimals)}`.slice(0, decimals);
  return BigInt(whole || "0") * 10n ** BigInt(decimals) + BigInt(padded || "0");
}

function erc20TransferData(to, amountMinorUnits) {
  const address = String(to || "").toLowerCase().replace(/^0x/, "");
  if (!/^[0-9a-f]{40}$/.test(address)) throw new Error("ERC-20 수신 주소가 올바르지 않습니다.");
  const amount = BigInt(amountMinorUnits);
  if (amount < 0n) throw new Error("ERC-20 전송 금액이 올바르지 않습니다.");
  const paddedAddress = address.padStart(64, "0");
  const paddedAmount = amount.toString(16).padStart(64, "0");
  return `0xa9059cbb${paddedAddress}${paddedAmount}`;
}

function newId(prefix) {
  const randomId = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${randomId}`;
}
