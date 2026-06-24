import Home from "@/components/Home";
import { Suspense } from "react";

export default function Page() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-100 flex items-center justify-center"><span className="text-slate-500 font-medium">로딩 중...</span></div>}>
      <Home />
    </Suspense>
  );
}
