"use client";

import React, { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { CompareView } from "../../components/CompareView";
import { useWorkspace } from "../../context/WorkspaceContext";

function CompareContent() {
  const searchParams = useSearchParams();
  const {
    asset1,
    asset2,
    allAssets,
    setAsset1,
    setAsset2,
    setIsEvidenceModalOpen,
  } = useWorkspace();

  const asset1Param = searchParams.get("asset1");
  const asset2Param = searchParams.get("asset2");

  useEffect(() => {
    if (asset1Param) {
      const found = allAssets.find(
        (a) =>
          a.id.toLowerCase() === asset1Param.toLowerCase() ||
          a.name.toLowerCase() === asset1Param.toLowerCase()
      );
      if (found) setAsset1(found);
    }
  }, [asset1Param, allAssets, setAsset1]);

  useEffect(() => {
    if (asset2Param) {
      const found = allAssets.find(
        (a) =>
          a.id.toLowerCase() === asset2Param.toLowerCase() ||
          a.name.toLowerCase() === asset2Param.toLowerCase()
      );
      if (found) setAsset2(found);
    }
  }, [asset2Param, allAssets, setAsset2]);

  return (
    <CompareView
      asset1={asset1}
      asset2={asset2}
      allAssets={allAssets}
      onSelectAsset1={setAsset1}
      onSelectAsset2={setAsset2}
      onOpenEvidenceModal={() => setIsEvidenceModalOpen(true)}
    />
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<div className="p-6 text-xs text-slate-500">Loading comparison view...</div>}>
      <CompareContent />
    </Suspense>
  );
}
