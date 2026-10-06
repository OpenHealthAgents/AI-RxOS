"use client";

import React, { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { EvaluateView } from "../../components/EvaluateView";
import { useWorkspace } from "../../context/WorkspaceContext";

function EvaluateContent() {
  const searchParams = useSearchParams();
  const {
    asset1,
    allAssets,
    activeSection,
    setActiveSection,
    setAsset1,
    setIsEvidenceModalOpen,
  } = useWorkspace();

  const sectionParam = searchParams.get("section");

  useEffect(() => {
    if (sectionParam) {
      setActiveSection(sectionParam);
    }
  }, [sectionParam, setActiveSection]);

  return (
    <EvaluateView
      asset={asset1}
      allAssets={allAssets}
      activeSection={activeSection}
      onSelectAsset={setAsset1}
      onOpenEvidenceModal={() => setIsEvidenceModalOpen(true)}
      onSelectSection={setActiveSection}
    />
  );
}

export default function EvaluatePage() {
  return (
    <Suspense fallback={<div className="p-6 text-xs text-slate-500">Loading evaluation workspace...</div>}>
      <EvaluateContent />
    </Suspense>
  );
}
