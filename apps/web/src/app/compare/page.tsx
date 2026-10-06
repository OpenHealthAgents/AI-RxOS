"use client";

import React from "react";
import { CompareView } from "../../components/CompareView";
import { useWorkspace } from "../../context/WorkspaceContext";

export default function ComparePage() {
  const {
    asset1,
    asset2,
    allAssets,
    setAsset1,
    setAsset2,
    setIsEvidenceModalOpen,
  } = useWorkspace();

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
