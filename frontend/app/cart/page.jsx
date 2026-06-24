import Cart from "@/components/Cart";
import { Suspense } from "react";

export default function CartPage() {
  return (
    <Suspense fallback={<div className="flex min-h-screen items-center justify-center bg-slate-100"><span className="text-slate-500 font-medium">장바구니 불러오는 중...</span></div>}>
      <Cart />
    </Suspense>
  );
}
