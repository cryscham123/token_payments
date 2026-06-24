import StoreDetail from "@/components/StoreDetail";
import { Suspense } from "react";

export default async function StorePage({ params }) {
  const { publicStoreId } = await params;
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center bg-slate-100"><span className="text-slate-500 font-medium">스토어 불러오는 중...</span></div>}>
      <StoreDetail publicStoreId={publicStoreId} />
    </Suspense>
  );
}
