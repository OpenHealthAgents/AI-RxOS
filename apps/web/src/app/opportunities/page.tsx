"use client";

import React, { useCallback } from "react";
import { useRouter } from "next/navigation";
import { OpportunitiesView } from "../../components/OpportunitiesView";
import { useWorkspace } from "../../context/WorkspaceContext";

export default function OpportunitiesPage() {
  const router = useRouter();
  const { setActiveSection } = useWorkspace();

  const handleSelectAssetForCompare = useCallback(
    (assetId: string) => {
      router.push(`/compare?asset=${encodeURIComponent(assetId)}`);
    },
    [router],
  );

  const handleNavigateToEvaluate = useCallback(
    (assetId: string) => {
      setActiveSection("overview");
      router.push(`/evaluate?asset=${encodeURIComponent(assetId)}`);
    },
    [router, setActiveSection],
  );

  return (
    <OpportunitiesView
      onNavigateToCompare={handleSelectAssetForCompare}
      onNavigateToEvaluate={handleNavigateToEvaluate}
    />
  );
}
