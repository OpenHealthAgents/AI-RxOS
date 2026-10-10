"use client";

import React, { Suspense } from "react";
import { EvaluateView } from "../../components/EvaluateView";

export default function EvaluatePage() {
  return (
    <Suspense
      fallback={
        <div className="p-6 text-xs text-slate-500">
          Loading evaluation workspace...
        </div>
      }
    >
      <EvaluateView />
    </Suspense>
  );
}
