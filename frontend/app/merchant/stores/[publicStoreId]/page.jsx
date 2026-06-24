import MerchantDashboard from "@/components/MerchantDashboard";
import { Suspense } from "react";

export default async function MerchantStorePage({ params }) {
  const { publicStoreId } = await params;
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center bg-slate-100"><span className="text-slate-500 font-medium">대시보드 불러오는 중...</span></div>}>
      <MerchantDashboard publicStoreId={publicStoreId} />
    </Suspense>
  );
}
