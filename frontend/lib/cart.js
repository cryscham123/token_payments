const CART_KEY = "token-payments.cart.v1";

export function loadCart() {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(CART_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter(isCartItem) : [];
  } catch {
    return [];
  }
}

export function saveCart(items) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CART_KEY, JSON.stringify(items.filter(isCartItem)));
  window.dispatchEvent(new Event("token-payments-cart-changed"));
}

export function addCartItem(product, { quantity, option = "기본 옵션" } = {}) {
  const nextQuantity = Math.max(1, Number(quantity) || 1);
  const current = loadCart();
  const existing = current.find((item) => item.id === product.id && item.option === option);
  const next = existing
    ? current.map((item) =>
        item.id === product.id && item.option === option
          ? { ...item, quantity: item.quantity + nextQuantity }
          : item
      )
    : [...current, { ...product, option, quantity: nextQuantity }];
  saveCart(next);
  return next;
}

export function clearCart() {
  saveCart([]);
}

function isCartItem(value) {
  return (
    value &&
    typeof value === "object" &&
    typeof value.id === "string" &&
    typeof value.publicProductId === "string" &&
    typeof value.title === "string" &&
    Number.isFinite(Number(value.quantity)) &&
    Number(value.quantity) > 0
  );
}
