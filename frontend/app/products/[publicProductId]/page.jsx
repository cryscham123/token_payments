import ProductDetail from "@/components/ProductDetail";

export default async function ProductPage({ params }) {
  const { publicProductId } = await params;
  return <ProductDetail publicProductId={publicProductId} />;
}
