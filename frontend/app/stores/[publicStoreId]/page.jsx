import StoreDetail from "@/components/StoreDetail";

export default async function StorePage({ params }) {
  const { publicStoreId } = await params;
  return <StoreDetail publicStoreId={publicStoreId} />;
}
