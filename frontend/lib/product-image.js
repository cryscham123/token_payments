import { getS3Url } from "./s3";

// Neutral "no image" placeholder used whenever a product has no usable media. Kept as an inline
// SVG data URI so it never 404s and requires no network/extra file. Previously these fallbacks
// pointed at the demo hoodie photo, which made every image-less product look like a hoodie.
const PLACEHOLDER_SVG =
  "<svg xmlns='http://www.w3.org/2000/svg' width='400' height='400'>" +
  "<rect width='100%' height='100%' fill='#f1f5f9'/>" +
  "<g fill='none' stroke='#cbd5e1' stroke-width='3'>" +
  "<rect x='140' y='140' width='120' height='120' rx='10'/>" +
  "<circle cx='172' cy='176' r='12'/>" +
  "<path d='M146 244 l40 -42 28 28 24 -24 32 32'/>" +
  "</g></svg>";

export const PRODUCT_IMAGE_PLACEHOLDER = `data:image/svg+xml,${encodeURIComponent(PLACEHOLDER_SVG)}`;

function resolveMediaRef(ref) {
  if (!ref) return "";
  if (/^https?:\/\//.test(ref) || /^data:image\//.test(ref)) return ref;
  return getS3Url(ref) || "";
}

// Pick the first image-like entry from a product's media array and resolve it to a servable URL.
export function productImageFromMedia(media = []) {
  const imageFile = (media || []).find((file) => /^data:image\//.test(file) || /\.(png|jpe?g|webp|gif)$/i.test(file)) || (media || [])[0];
  return resolveMediaRef(imageFile) || PRODUCT_IMAGE_PLACEHOLDER;
}

// Resolve a single media ref (used for thumbnails / detail images), falling back to the placeholder.
export function resolveProductImage(file) {
  return resolveMediaRef(file) || PRODUCT_IMAGE_PLACEHOLDER;
}

// Resolve every image ref in a product's media list, keeping order. Empty list yields a single
// placeholder so callers always have something to render.
export function productImageGallery(media = []) {
  const images = (media || [])
    .filter((ref) => !/\.pdf$/i.test(ref))
    .map(resolveMediaRef)
    .filter(Boolean);
  return images.length > 0 ? images : [PRODUCT_IMAGE_PLACEHOLDER];
}

const CATEGORY_PLACEHOLDERS = {
  coffee: "https://images.unsplash.com/photo-1509042239860-f550ce710b93?auto=format&fit=crop&q=80&w=400",
  craft: "https://images.unsplash.com/photo-1459865264687-595d652de67e?auto=format&fit=crop&q=80&w=400",
  grocery: "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&q=80&w=400",
  groceries: "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&q=80&w=400",
  gadget: "https://images.unsplash.com/photo-1468495244123-6c6c332eeece?auto=format&fit=crop&q=80&w=400",
  electronics: "https://images.unsplash.com/photo-1468495244123-6c6c332eeece?auto=format&fit=crop&q=80&w=400",
  beauty: "https://images.unsplash.com/photo-1596462502278-27bfdc403348?auto=format&fit=crop&q=80&w=400",
  cosmetics: "https://images.unsplash.com/photo-1596462502278-27bfdc403348?auto=format&fit=crop&q=80&w=400",
  health: "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?auto=format&fit=crop&q=80&w=400",
  sports: "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?auto=format&fit=crop&q=80&w=400",
  decor: "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?auto=format&fit=crop&q=80&w=400",
  home: "https://images.unsplash.com/photo-1513519245088-0e12902e5a38?auto=format&fit=crop&q=80&w=400",
  books: "https://images.unsplash.com/photo-1497633762265-9d179a990aa6?auto=format&fit=crop&q=80&w=400",
  pets: "https://images.unsplash.com/photo-1450778869180-41d0601e046e?auto=format&fit=crop&q=80&w=400",
  animals: "https://images.unsplash.com/photo-1450778869180-41d0601e046e?auto=format&fit=crop&q=80&w=400",
  digital: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&q=80&w=400",
  fashion: "https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&q=80&w=400",
  apparel: "https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&q=80&w=400",
  music: "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&q=80&w=400",
  toy: "https://images.unsplash.com/photo-1531346878377-a5be20888e57?auto=format&fit=crop&q=80&w=400",
  toys: "https://images.unsplash.com/photo-1531346878377-a5be20888e57?auto=format&fit=crop&q=80&w=400",
};

export function getCategoryFallback(category) {
  const normalized = String(category || "").toLowerCase();
  for (const [key, url] of Object.entries(CATEGORY_PLACEHOLDERS)) {
    if (normalized.includes(key)) return url;
  }
  return CATEGORY_PLACEHOLDERS.fashion; // default fallback
}
