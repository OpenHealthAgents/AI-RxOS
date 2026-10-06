"use client";

import React, { createContext, useContext, useState, ReactNode } from "react";
import { ALL_ASSETS, NERATINIB, ZONGERTINIB } from "../lib/data";
import { AssetIntelligence, StrategicAction } from "../lib/types";

export interface HumanDecisionRecord {
  id: string;
  assetId: string;
  assetName: string;
  timestamp: string;
  aiRecommendation: StrategicAction;
  humanRecommendation: StrategicAction;
  isOverride: boolean;
  signerName: string;
  signerRole: string;
  clinicalJustification: string;
  checklist: {
    targetSpecificityVerified: boolean;
    wtSparingConfirmed: boolean;
    cnsDataReviewed: boolean;
    safetyToxicityAcceptable: boolean;
    ftoIpNonInfringing: boolean;
  };
}

export type WorkflowStepId =
  | "user-query"
  | "opportunity-discovery"
  | "canonical-resolution"
  | "evidence-retrieval"
  | "temporal-filtering"
  | "multidimensional-analysis"
  | "decision-recommendation"
  | "explanation"
  | "evidence-inspection"
  | "human-decision";

export interface WorkflowStep {
  id: WorkflowStepId;
  number: number;
  label: string;
  shortLabel: string;
  description: string;
  status: "completed" | "active" | "pending";
}

interface WorkspaceContextType {
  asset1: AssetIntelligence;
  setAsset1: (asset: AssetIntelligence) => void;
  asset2: AssetIntelligence;
  setAsset2: (asset: AssetIntelligence) => void;
  allAssets: AssetIntelligence[];
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  activeSection: string;
  setActiveSection: (section: string) => void;
  currentWorkflowStep: WorkflowStepId;
  setCurrentWorkflowStep: (step: WorkflowStepId) => void;
  isEvidenceModalOpen: boolean;
  setIsEvidenceModalOpen: (open: boolean) => void;
  isResolutionModalOpen: boolean;
  setIsResolutionModalOpen: (open: boolean) => void;
  isHumanDecisionModalOpen: boolean;
  setIsHumanDecisionModalOpen: (open: boolean) => void;
  humanDecisions: HumanDecisionRecord[];
  recordHumanDecision: (decision: Omit<HumanDecisionRecord, "id" | "timestamp">) => void;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WORKFLOW_STEPS: WorkflowStep[] = [
  {
    id: "user-query",
    number: 1,
    label: "User Query",
    shortLabel: "Query",
    description: "Natural language query, indication scope, or target class entry",
    status: "completed",
  },
  {
    id: "opportunity-discovery",
    number: 2,
    label: "Opportunity Discovery",
    shortLabel: "Discover",
    description: "Scan landscape, unmet medical needs, pipeline gaps, and clinical white-space",
    status: "completed",
  },
  {
    id: "canonical-resolution",
    number: 3,
    label: "Canonical Asset Resolution",
    shortLabel: "Resolution",
    description: "Entity disambiguation across ChEMBL, PubChem, NCT trials, and company codes",
    status: "completed",
  },
  {
    id: "evidence-retrieval",
    number: 4,
    label: "Evidence Retrieval",
    shortLabel: "Retrieval",
    description: "Multi-source evidence provenance (trials, labels, patents, preprints)",
    status: "completed",
  },
  {
    id: "temporal-filtering",
    number: 5,
    label: "Temporal Filtering",
    shortLabel: "Temporal",
    description: "Strict zero-leakage cutoffs for prospective decision auditing & backtesting",
    status: "completed",
  },
  {
    id: "multidimensional-analysis",
    number: 6,
    label: "Multidimensional Analysis",
    shortLabel: "Analysis",
    description: "Biology, potency, CNS penetration, safety TI, resistance, and market IP",
    status: "completed",
  },
  {
    id: "decision-recommendation",
    number: 7,
    label: "Decision Recommendation",
    shortLabel: "Recommend",
    description: "Bayesian transition probabilities & Development Potential Score (DPS)",
    status: "active",
  },
  {
    id: "explanation",
    number: 8,
    label: "Explanation",
    shortLabel: "Explain",
    description: "Transparent model lineage, factor attribution, and confidence intervals",
    status: "active",
  },
  {
    id: "evidence-inspection",
    number: 9,
    label: "Evidence Inspection",
    shortLabel: "Inspect",
    description: "Granular audit trail of supporting and contradicting empirical evidence",
    status: "pending",
  },
  {
    id: "human-decision",
    number: 10,
    label: "Human Decision",
    shortLabel: "Sign-Off",
    description: "Translational expert sign-off, clinical override, and governance logging",
    status: "pending",
  },
];

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [asset1, setAsset1] = useState<AssetIntelligence>(ZONGERTINIB);
  const [asset2, setAsset2] = useState<AssetIntelligence>(NERATINIB);
  const [allAssets] = useState<AssetIntelligence[]>(ALL_ASSETS);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [activeSection, setActiveSection] = useState<string>("overview");
  const [currentWorkflowStep, setCurrentWorkflowStep] = useState<WorkflowStepId>("decision-recommendation");
  const [isEvidenceModalOpen, setIsEvidenceModalOpen] = useState<boolean>(false);
  const [isResolutionModalOpen, setIsResolutionModalOpen] = useState<boolean>(false);
  const [isHumanDecisionModalOpen, setIsHumanDecisionModalOpen] = useState<boolean>(false);

  const [humanDecisions, setHumanDecisions] = useState<HumanDecisionRecord[]>([
    {
      id: "dec-001",
      assetId: "zongertinib",
      assetName: "Zongertinib",
      timestamp: "2026-10-04 16:30 UTC",
      aiRecommendation: "PURSUE",
      humanRecommendation: "PURSUE",
      isOverride: false,
      signerName: "Dr. S. Kalyan",
      signerRole: "Principal Translational Oncologist",
      clinicalJustification: "Target selectivity and WT-EGFR sparing clinical data (Beamion LUNG-1) confirms breakthrough therapeutic index. Endocrine combination trial warranted.",
      checklist: {
        targetSpecificityVerified: true,
        wtSparingConfirmed: true,
        cnsDataReviewed: true,
        safetyToxicityAcceptable: true,
        ftoIpNonInfringing: true,
      },
    },
  ]);

  const recordHumanDecision = (decision: Omit<HumanDecisionRecord, "id" | "timestamp">) => {
    const record: HumanDecisionRecord = {
      ...decision,
      id: `dec-${Date.now().toString(36)}`,
      timestamp: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
    };
    setHumanDecisions((prev) => [record, ...prev]);
  };

  return (
    <WorkspaceContext.Provider
      value={{
        asset1,
        setAsset1,
        asset2,
        setAsset2,
        allAssets,
        searchQuery,
        setSearchQuery,
        activeSection,
        setActiveSection,
        currentWorkflowStep,
        setCurrentWorkflowStep,
        isEvidenceModalOpen,
        setIsEvidenceModalOpen,
        isResolutionModalOpen,
        setIsResolutionModalOpen,
        isHumanDecisionModalOpen,
        setIsHumanDecisionModalOpen,
        humanDecisions,
        recordHumanDecision,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
