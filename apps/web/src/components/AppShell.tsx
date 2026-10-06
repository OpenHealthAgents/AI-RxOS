"use client";

import React from "react";
import { Header } from "./Header";
import { Sidebar } from "./Sidebar";
import { WorkflowStepper } from "./WorkflowStepper";
import { CanonicalResolutionModal } from "./CanonicalResolutionModal";
import { HumanDecisionModal } from "./HumanDecisionModal";
import { EvidenceProvenanceModal } from "./EvidenceProvenanceModal";
import { useWorkspace } from "../context/WorkspaceContext";

export function AppShell({ children }: { children: React.ReactNode }) {
  const {
    asset1,
    asset2,
    activeSection,
    setActiveSection,
    searchQuery,
    setSearchQuery,
    isEvidenceModalOpen,
    setIsEvidenceModalOpen,
  } = useWorkspace();

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[#f8fafc] text-slate-800 antialiased">
      {/* Top Application Header */}
      <Header
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
      />

      {/* Decision Workflow Stepper (10 Steps) */}
      <WorkflowStepper />

      {/* Main Workspace Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Navigation Sidebar (11 Evaluation Sections) */}
        <Sidebar
          activeSection={activeSection}
          onSelectSection={setActiveSection}
          onOpenEvidenceModal={() => setIsEvidenceModalOpen(true)}
        />

        {/* Dynamic Route Content */}
        <main className="flex flex-1 overflow-hidden bg-[#f8fafc]">
          {children}
        </main>
      </div>

      {/* Modal Dialogs */}
      <CanonicalResolutionModal />
      <HumanDecisionModal />
      <EvidenceProvenanceModal
        isOpen={isEvidenceModalOpen}
        onClose={() => setIsEvidenceModalOpen(false)}
        asset1={asset1}
        asset2={asset2}
      />
    </div>
  );
}
