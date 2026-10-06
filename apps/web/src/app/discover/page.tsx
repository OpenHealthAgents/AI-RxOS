"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { DiscoverView } from "../../components/DiscoverView";
import { useWorkspace } from "../../context/WorkspaceContext";
import { AssetIntelligence } from "../../lib/types";

export default function DiscoverPage() {
  const router = useRouter();
  const { allAssets, setAsset1, setAsset2, setActiveSection } = useWorkspace();

  const handleSelectAssetForCompare = (asset: AssetIntelligence) => {
    setAsset2(asset);
    router.push("/compare");
  };

  const handleNavigateToEvaluate = (asset: AssetIntelligence) => {
    setAsset1(asset);
    setActiveSection("overview");
    router.push("/evaluate");
  };

  return (
    <DiscoverView
      assets={allAssets}
      onSelectAssetForCompare={handleSelectAssetForCompare}
      onNavigateToEvaluate={handleNavigateToEvaluate}
    />
  );
}
