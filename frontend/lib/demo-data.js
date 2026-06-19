export const demoStore = {
  id: "44444444-4444-4444-8444-444444444444",
  publicStoreId: "st_demo_store_001",
  name: "종합마켓",
  tagline: "크립토 최저가 쇼핑",
  wallet: "0x2222222222222222222222222222222222222222",
  acceptedAssets: ["ETH"]
};

export const products = [
  {
    id: "55555555-5555-4555-8555-555555555555",
    publicProductId: "prd_local_hoodie_001",
    name: "Local Hoodie",
    koreanName: "로컬 체크아웃 후디",
    category: "apparel",
    priceKrw: 79000,
    cryptoAmount: "0.010000000000000000",
    cryptoSymbol: "ETH",
    stock: 25,
    image: "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=900",
    thumb: "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&q=80&w=300",
    description: "Local checkout test hoodie"
  }
];

export const orders = [
  {
    id: "ORD-LOCAL-0001",
    date: "2026.06.01",
    status: "배송중",
    product: products[0],
    amount: "0.010000 ETH",
    txHash: "0x71C7656EC7ab88b098defB751B7401B5f6d1476B"
  }
];

export function formatKrw(value) {
  return new Intl.NumberFormat("ko-KR").format(value);
}

export function formatCryptoAmount(value) {
  const normalized = Number.parseFloat(value || "0");
  return normalized.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 6
  });
}
