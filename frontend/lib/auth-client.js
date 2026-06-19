const JSON_HEADERS = {
  "Content-Type": "application/json"
};

export class ApiError extends Error {
  constructor(message, { status, code, body } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

export async function requestLoginChallenge({ walletAddress, chainId, domain, uri }) {
  return apiJson("/auth/challenges", {
    method: "POST",
    body: {
      walletAddress,
      domain,
      uri,
      chainId
    }
  });
}

export async function loginWithMetaMask({ walletAddress, message, signature, deviceId }) {
  return apiJson("/auth/sessions", {
    method: "POST",
    body: {
      walletAddress,
      message,
      signature,
      deviceId
    }
  });
}

export async function getCurrentUser() {
  try {
    return await apiJson("/auth/me", { method: "GET" });
  } catch (err) {
    if (err.status == 401 || err.status == 403 || err.status == 400) {
      return { user: null };
    }
    throw err;
  }
}

export async function listWallets() {
  return apiJson("/auth/wallets", { method: "GET" });
}

export async function requestWalletLinkChallenge({ walletAddress, chainId, domain, uri }) {
  return apiJson("/auth/wallets/challenges", {
    method: "POST",
    body: {
      walletAddress,
      domain,
      uri,
      chainId
    }
  });
}

export async function linkWallet({ walletAddress, message, signature, walletType = "EOA" }) {
  return apiJson("/auth/wallets", {
    method: "POST",
    body: {
      walletAddress,
      message,
      signature,
      walletType
    }
  });
}

export async function setPrimaryWallet(walletId) {
  return apiJson(`/auth/wallets/${encodeURIComponent(walletId)}/primary`, {
    method: "PATCH"
  });
}

export async function revokeWallet(walletId) {
  return apiJson(`/auth/wallets/${encodeURIComponent(walletId)}`, {
    method: "DELETE"
  });
}

export async function logout() {
  return apiJson("/auth/sessions", { method: "DELETE" });
}

export async function getCurrentUserProfile() {
  return apiJson("/auth/me/profile", { method: "GET" });
}

export async function updateCurrentUserProfile(displayName) {
  return apiJson("/auth/me/profile", {
    method: "PATCH",
    body: { displayName }
  });
}

export async function listMerchantStores() {
  return apiJson("/merchant/stores", { method: "GET" });
}

export async function listPublicStores() {
  return apiJson("/stores", { method: "GET" });
}

export async function requestOAuthAuthorization({ provider = "google", redirectUri, mode = "login" }) {
  return apiJson(`/auth/oauth/${encodeURIComponent(provider)}/authorize`, {
    method: "POST",
    body: {
      redirectUri,
      mode
    }
  });
}

export async function linkOAuthIdentity({ provider = "google", code, state, redirectUri }) {
  return apiJson(`/auth/oauth/${encodeURIComponent(provider)}/links`, {
    method: "POST",
    body: {
      code,
      state,
      redirectUri
    }
  });
}

export async function listOAuthIdentities() {
  return apiJson("/auth/oauth/identities", { method: "GET" });
}

export async function revokeOAuthIdentity(oauthIdentityId) {
  return apiJson(`/auth/oauth/identities/${encodeURIComponent(oauthIdentityId)}`, {
    method: "DELETE"
  });
}

export function browserSiweContext(chainId) {
  if (typeof window === "undefined") {
    return {
      domain: "localhost",
      uri: "https://localhost",
      chainId
    };
  }

  return {
    domain: window.location.host,
    uri: window.location.origin,
    chainId
  };
}

export function newBrowserDeviceId() {
  const randomId = typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
  return `browser-${randomId}`;
}

export async function apiJson(path, { method = "GET", body, idempotencyKey } = {}) {
  const headers = body === undefined ? {} : { ...JSON_HEADERS };
  const csrfToken = csrfCookie();
  if (csrfToken && !isSafeMethod(method)) headers["X-CSRF-Token"] = csrfToken;
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  const response = await fetch(path, {
    method,
    credentials: "include",
    headers: Object.keys(headers).length ? headers : undefined,
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const payload = await readJson(response);

  if (!response.ok) {
    const error = payload?.error || {};
    if (response.status === 401 || (response.status === 403 && (error.code === "CSRF_TOKEN_INVALID" || error.code === "CSRF_TOKEN_MISSING"))) {
      if (typeof window !== "undefined") {
        document.cookie = "csrf_token=; path=/; max-age=0;";
        window.dispatchEvent(new CustomEvent("token-payments-unauthorized"));
      }
    }
    const pathStr = typeof path === "string" ? path : "";
    const methodStr = typeof method === "string" ? method : "GET";
    const isSessionGet = methodStr.toUpperCase() === "GET" && (pathStr.startsWith("/auth/") || pathStr.startsWith("/merchant/"));
    if (isSessionGet && (response.status === 401 || response.status === 403 || response.status === 400)) {
      return payload || { error };
    }
    throw new ApiError(error.message || response.statusText || "API request failed", {
      status: response.status,
      code: error.code,
      body: payload
    });
  }

  return payload;
}

function csrfCookie() {
  if (typeof document === "undefined") return "";
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("csrf_token="))
    ?.split("=")
    .slice(1)
    .join("=") || "";
}

function isSafeMethod(method) {
  return ["GET", "HEAD", "OPTIONS"].includes(String(method).toUpperCase());
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function ensureLocalTestnet() {
  const ethereum = typeof window !== "undefined" ? window.ethereum : undefined;
  if (!ethereum?.request) return;
  const LOCAL_CHAIN_ID_HEX = "0x539"; // 1337 in hex
  try {
    await ethereum.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: LOCAL_CHAIN_ID_HEX }]
    });
  } catch (switchError) {
    if (switchError.code === 4902) {
      try {
        await ethereum.request({
          method: "wallet_addEthereumChain",
          params: [{
            chainId: LOCAL_CHAIN_ID_HEX,
            chainName: "Local Test Network",
            nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
            rpcUrls: ["http://127.0.0.1:8545"]
          }]
        });
      } catch (addError) {
        console.error("네트워크 추가 실패:", addError);
        throw addError;
      }
    } else {
      console.error("네트워크 전환 실패:", switchError);
      throw switchError;
    }
  }
}
