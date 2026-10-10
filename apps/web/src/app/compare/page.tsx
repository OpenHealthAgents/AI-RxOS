"use client";

import React, { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CompareView } from "../../components/CompareView";

function ComparePageContent() {
  const searchParams = useSearchParams();
  return (
    <CompareView
      initialAssetId={searchParams.get("asset") ?? searchParams.get("asset1")}
      initialAsset2Id={searchParams.get("asset2")}
    />
  );
}

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <div role="status" className="p-6 text-sm text-slate-600">
          Loading comparison workspace…
        </div>
      }
    >
      <ComparePageContent />
    </Suspense>
  );
}
