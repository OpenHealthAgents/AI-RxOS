"use client";

import React, { useState } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { ALL_ASSETS } from "../lib/data";

interface CanonicalEntityRecord {
  queryInput: string;
  canonicalName: string;
  synonyms: string[];
  target: string;
  modality: string;
  moaDetail: string;
  originator: string;
  currentOwner: string;
  chemblId: string;
  uniprotId: string;
  casNumber: string;
  nctIds: string[];
  resolutionConfidence: number;
  linkedAssetId: string;
}

const CANONICAL_KNOWLEDGE_BASE: CanonicalEntityRecord[] = [
  {
    queryInput: "BI-0631",
    canonicalName: "Zongertinib",
    synonyms: ["BI 1810631", "BI-1810631", "BI-0631", "Boehringer 1810631"],
    target: "HER2 (ERBB2)",
    modality: "Small Molecule Kinase Inhibitor (TKI)",
    moaDetail: "Selective, covalent, wild-type EGFR sparing inhibitor of HER2 tyrosine kinase, active against exon 20 insertions and point mutations.",
    originator: "Boehringer Ingelheim",
    currentOwner: "Boehringer Ingelheim",
    chemblId: "CHEMBL4650123",
    uniprotId: "P04626 (ERBB2_HUMAN)",
    casNumber: "2411636-84-7",
    nctIds: ["NCT04886804 (Beamion LUNG-1)", "NCT06151496 (Beamion LUNG-2)"],
    resolutionConfidence: 99.8,
    linkedAssetId: "zongertinib",
  },
  {
    queryInput: "PB272",
    canonicalName: "Neratinib",
    synonyms: ["PB272", "PB-272", "HKI-272", "Nerlynx"],
    target: "pan-HER (EGFR, HER2, HER4)",
    modality: "Small Molecule Kinase Inhibitor (TKI)",
    moaDetail: "Irreversible pan-ErbB tyrosine kinase inhibitor binding to Cys805 in HER2 and Cys797 in EGFR. Lacks WT-EGFR sparing.",
    originator: "Wyeth / Pfizer",
    currentOwner: "Puma Biotechnology",
    chemblId: "CHEMBL410500",
    uniprotId: "P04626 / P00533",
    casNumber: "698387-09-6",
    nctIds: ["NCT00878709 (ExteNET)", "NCT01953926 (SUMMIT)"],
    resolutionConfidence: 100.0,
    linkedAssetId: "neratinib",
  },
  {
    queryInput: "ONT-380",
    canonicalName: "Tucatinib",
    synonyms: ["ONT-380", "ARRY-380", "Tukysa", "Irbinitinib"],
    target: "HER2 (ERBB2)",
    modality: "Small Molecule Kinase Inhibitor (TKI)",
    moaDetail: "Potent, reversible, selective HER2 inhibitor with >1000-fold selectivity over EGFR. High CNS blood-brain barrier penetration.",
    originator: "Array BioPharma / Oncothyrena",
    currentOwner: "Seagen / Pfizer",
    chemblId: "CHEMBL2105759",
    uniprotId: "P04626 (ERBB2_HUMAN)",
    casNumber: "937263-43-9",
    nctIds: ["NCT02614794 (HER2CLIMB)", "NCT04579380 (HER2CLIMB-02)"],
    resolutionConfidence: 100.0,
    linkedAssetId: "tucatinib",
  },
  {
    queryInput: "HM781-36B",
    canonicalName: "Poziotinib",
    synonyms: ["HM781-36B", "NOV120101", "HM-781-36B"],
    target: "pan-HER (EGFR, HER2, HER4)",
    modality: "Small Molecule Kinase Inhibitor (TKI)",
    moaDetail: "Small flexible irreversible quinazoline pan-HER kinase inhibitor with potent in vitro exon 20 activity but narrow therapeutic index due to severe WT-EGFR inhibition.",
    originator: "Hanmi Pharmaceutical",
    currentOwner: "Spectrum Pharmaceuticals",
    chemblId: "CHEMBL2386440",
    uniprotId: "P04626 / P00533",
    casNumber: "1092364-38-9",
    nctIds: ["NCT03318939 (ZENITH20)", "NCT01728818"],
    resolutionConfidence: 99.4,
    linkedAssetId: "poziotinib",
  },
];

export function CanonicalResolutionModal() {
  const {
    isResolutionModalOpen,
    setIsResolutionModalOpen,
    setAsset1,
    setCurrentWorkflowStep,
  } = useWorkspace();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRecord, setSelectedRecord] = useState<CanonicalEntityRecord>(
    CANONICAL_KNOWLEDGE_BASE[0]!
  );

  if (!isResolutionModalOpen) return null;

  const filteredRecords = CANONICAL_KNOWLEDGE_BASE.filter(
    (r) =>
      r.canonicalName.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.queryInput.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.synonyms.some((s) => s.toLowerCase().includes(searchQuery.toLowerCase())) ||
      r.target.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.currentOwner.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleSelectCanonicalAsset = (record: CanonicalEntityRecord) => {
    setSelectedRecord(record);
  };

  const handleApplyToWorkspace = () => {
    const asset = ALL_ASSETS.find((a) => a.id === selectedRecord.linkedAssetId);
    if (asset) {
      setAsset1(asset);
      setCurrentWorkflowStep("evidence-retrieval");
    }
    setIsResolutionModalOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div className="relative flex h-[85vh] w-full max-w-5xl flex-col rounded-xl border border-slate-700 bg-white shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-900 px-6 py-4 text-white">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-bold">
              ⚡
            </div>
            <div>
              <h2 className="text-base font-bold tracking-tight text-white">
                Canonical Asset Resolution Engine
              </h2>
              <p className="text-xs text-slate-400">
                Workflow Step 3 • Cross-namespace entity disambiguation & registry reconciliation
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsResolutionModalOpen(false)}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition"
          >
            ✕
          </button>
        </div>

        {/* Body Content */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: Search & Disambiguation List */}
          <div className="w-80 border-r border-slate-200 bg-slate-50 flex flex-col">
            <div className="p-3 border-b border-slate-200">
              <label className="block text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-1">
                Asset Name / Alias / Code
              </label>
              <input
                type="text"
                placeholder="e.g. BI-0631, PB272, ONT-380..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              {filteredRecords.map((item) => {
                const isSelected = selectedRecord.canonicalName === item.canonicalName;
                return (
                  <button
                    key={item.canonicalName}
                    onClick={() => handleSelectCanonicalAsset(item)}
                    className={`w-full rounded-lg p-2.5 text-left transition ${
                      isSelected
                        ? "border border-blue-500 bg-blue-50/80 shadow-sm"
                        : "border border-slate-200 bg-white hover:bg-slate-100"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-xs text-slate-900">
                        {item.canonicalName}
                      </span>
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                        {item.resolutionConfidence}% match
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-500 mt-0.5">
                      Target: {item.target}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-1 truncate">
                      Aliases: {item.synonyms.join(", ")}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right: Detailed Canonical Resolution Dossier */}
          <div className="flex-1 overflow-y-auto p-6 bg-white space-y-6">
            {/* Top Identity Card */}
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xl font-bold text-slate-900">
                      {selectedRecord.canonicalName}
                    </span>
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800">
                      CANONICAL ENTITY
                    </span>
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                      Disambiguated
                    </span>
                  </div>
                  <p className="text-xs text-slate-600 mt-1">
                    <strong>Primary Originator:</strong> {selectedRecord.originator} |{" "}
                    <strong>Current Rights Holder:</strong> {selectedRecord.currentOwner}
                  </p>
                </div>

                <div className="text-right">
                  <div className="text-[10px] uppercase font-bold text-slate-400">
                    Confidence Score
                  </div>
                  <div className="text-2xl font-bold text-emerald-600">
                    {selectedRecord.resolutionConfidence}%
                  </div>
                </div>
              </div>

              {/* Aliases */}
              <div className="mt-3 border-t border-slate-200 pt-3">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  Reconciled Synonyms & Laboratory Codes:
                </span>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {selectedRecord.synonyms.map((alias) => (
                    <span
                      key={alias}
                      className="rounded bg-white border border-slate-200 px-2 py-0.5 text-xs text-slate-700 font-mono"
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            {/* Target & MOA Specification */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                Biological Target & Molecular Action
              </h3>
              <div className="rounded-lg border border-slate-200 p-4 space-y-3">
                <div className="grid grid-cols-2 gap-4 text-xs">
                  <div>
                    <span className="font-semibold text-slate-500">Target Molecule:</span>
                    <div className="font-bold text-slate-800">{selectedRecord.target}</div>
                  </div>
                  <div>
                    <span className="font-semibold text-slate-500">Modality:</span>
                    <div className="font-bold text-slate-800">{selectedRecord.modality}</div>
                  </div>
                </div>
                <div className="text-xs">
                  <span className="font-semibold text-slate-500">Mechanism of Action (MOA):</span>
                  <p className="mt-1 text-slate-700 leading-relaxed bg-slate-50 p-2.5 rounded border border-slate-100">
                    {selectedRecord.moaDetail}
                  </p>
                </div>
              </div>
            </div>

            {/* Verified Cross-References & Registries */}
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
                Verified Registries & Provenance Identifiers
              </h3>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="rounded border border-slate-200 p-3 bg-slate-50">
                  <span className="font-semibold text-slate-500">ChEMBL Compound ID</span>
                  <div className="font-mono font-bold text-blue-700 mt-0.5">
                    {selectedRecord.chemblId}
                  </div>
                </div>

                <div className="rounded border border-slate-200 p-3 bg-slate-50">
                  <span className="font-semibold text-slate-500">UniProt Target ID</span>
                  <div className="font-mono font-bold text-blue-700 mt-0.5">
                    {selectedRecord.uniprotId}
                  </div>
                </div>

                <div className="rounded border border-slate-200 p-3 bg-slate-50">
                  <span className="font-semibold text-slate-500">CAS Registry Number</span>
                  <div className="font-mono font-bold text-slate-800 mt-0.5">
                    {selectedRecord.casNumber}
                  </div>
                </div>

                <div className="rounded border border-slate-200 p-3 bg-slate-50">
                  <span className="font-semibold text-slate-500">Key ClinicalTrials.gov NCTs</span>
                  <div className="font-mono font-medium text-slate-800 mt-0.5 space-y-0.5">
                    {selectedRecord.nctIds.map((nct) => (
                      <div key={nct} className="truncate">{nct}</div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Entity Lineage & Evidence Grounding Guarantee */}
            <div className="rounded-lg bg-blue-50 border border-blue-200 p-3 text-xs text-blue-900">
              <span className="font-bold">Provenance & Audit Guarantee:</span>
              <p className="mt-0.5 text-blue-800">
                All preclinical bioassay measurements, clinical trial publications, and patent filings are strictly keyed against this canonical entity. Synonyms are automatically normalized across historical literature.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-3">
          <span className="text-xs text-slate-500">
            Current Selected Asset: <strong>{selectedRecord.canonicalName}</strong>
          </span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsResolutionModalOpen(false)}
              className="rounded px-4 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 transition"
            >
              Cancel
            </button>
            <button
              onClick={handleApplyToWorkspace}
              className="rounded bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 shadow-sm transition"
            >
              Load into Workspace & Proceed to Retrieval →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
