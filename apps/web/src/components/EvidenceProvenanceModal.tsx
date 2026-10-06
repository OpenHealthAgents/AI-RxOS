"use client";

import React, { useState } from "react";
import { AssetIntelligence } from "../lib/types";

export interface EvidenceProvenanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset1: AssetIntelligence;
  asset2?: AssetIntelligence;
}

export function EvidenceProvenanceModal({
  isOpen,
  onClose,
  asset1,
  asset2,
}: EvidenceProvenanceModalProps) {
  const [selectedAssetId, setSelectedAssetId] = useState<string>(asset1.id);
  const [activeTab, setActiveTab] = useState<"supporting" | "contradicting" | "unknowns" | "lineage" | "inferences">("supporting");

  if (!isOpen) return null;

  const currentAsset = selectedAssetId === asset1.id ? asset1 : (asset2 ?? asset1);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-4xl rounded-xl border border-slate-200 bg-white shadow-2xl overflow-hidden my-8">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">
                Evidence Provenance & Model Lineage Dossier
              </h2>
              <p className="text-xs text-slate-500">
                Auditable citations, contradictory observations, explicit unknowns, and calculation lineage
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Asset Selector Toggle */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-2.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-600">Select Asset:</span>
            <button
              onClick={() => setSelectedAssetId(asset1.id)}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
                selectedAssetId === asset1.id
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              {asset1.name} ({asset1.recommendation.action})
            </button>
            {asset2 && (
              <button
                onClick={() => setSelectedAssetId(asset2.id)}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
                  selectedAssetId === asset2.id
                    ? "bg-amber-600 text-white"
                    : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                }`}
              >
                {asset2.name} ({asset2.recommendation.action})
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
              ✓ Verified Lineage
            </span>
            <span className="text-xs text-slate-500">As of: {currentAsset.last_updated}</span>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-200 bg-slate-50/50 px-6 text-xs">
          <button
            onClick={() => setActiveTab("supporting")}
            className={`py-2.5 px-4 font-semibold border-b-2 transition-colors ${
              activeTab === "supporting"
                ? "border-blue-600 text-blue-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            Supporting Evidence ({currentAsset.supporting_evidence.length})
          </button>
          <button
            onClick={() => setActiveTab("contradicting")}
            className={`py-2.5 px-4 font-semibold border-b-2 transition-colors ${
              activeTab === "contradicting"
                ? "border-rose-600 text-rose-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            Contradicting Evidence ({currentAsset.contradicting_evidence.length})
          </button>
          <button
            onClick={() => setActiveTab("unknowns")}
            className={`py-2.5 px-4 font-semibold border-b-2 transition-colors ${
              activeTab === "unknowns"
                ? "border-purple-600 text-purple-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            Explicit Unknowns ({currentAsset.unknowns.length})
          </button>
          <button
            onClick={() => setActiveTab("lineage")}
            className={`py-2.5 px-4 font-semibold border-b-2 transition-colors ${
              activeTab === "lineage"
                ? "border-emerald-600 text-emerald-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            Model Calculation Lineage
          </button>
          <button
            onClick={() => setActiveTab("inferences")}
            className={`py-2.5 px-4 font-semibold border-b-2 transition-colors ${
              activeTab === "inferences"
                ? "border-sky-600 text-sky-700"
                : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            AI Inferences Disclosed ({currentAsset.ai_inferences.length})
          </button>
        </div>

        {/* Modal Body */}
        <div className="max-h-[60vh] overflow-y-auto p-6 space-y-4">
          {activeTab === "supporting" && (
            <div className="space-y-3">
              {currentAsset.supporting_evidence.length === 0 ? (
                <div className="text-center py-8 text-sm text-slate-500">
                  No verified supporting evidence recorded.
                </div>
              ) : (
                currentAsset.supporting_evidence.map((ev) => (
                  <div
                    key={ev.id}
                    className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-blue-300 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800 uppercase">
                          {ev.source_type}
                        </span>
                        <span className="font-mono text-xs font-semibold text-slate-900">
                          {ev.source_ref}
                        </span>
                        {ev.url && (
                          <a
                            href={ev.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-blue-600 hover:underline inline-flex items-center gap-0.5"
                          >
                            <span>Open</span>
                            <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                          </a>
                        )}
                      </div>
                      <span className="text-[11px] text-slate-500">
                        Published: {ev.as_of_date} ({ev.publication_year})
                      </span>
                    </div>

                    <h4 className="text-sm font-semibold text-slate-800 mb-1">{ev.title}</h4>
                    <p className="text-xs text-slate-500 italic mb-2">{ev.citation}</p>
                    <div className="rounded bg-slate-50 p-2.5 text-xs text-slate-700 border-l-2 border-emerald-500 font-mono">
                      "{ev.excerpt}"
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "contradicting" && (
            <div className="space-y-3">
              {currentAsset.contradicting_evidence.length === 0 ? (
                <div className="rounded-lg bg-emerald-50 p-6 text-center text-sm text-emerald-800">
                  No verified contradicting safety or efficacy signals currently recorded for {currentAsset.name}.
                </div>
              ) : (
                currentAsset.contradicting_evidence.map((ev) => (
                  <div
                    key={ev.id}
                    className="rounded-lg border border-rose-200 bg-rose-50/30 p-4 shadow-sm"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-800 uppercase">
                          CONTRADICTING ({ev.source_type})
                        </span>
                        <span className="font-mono text-xs font-semibold text-slate-900">
                          {ev.source_ref}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-500">
                        Observed: {ev.as_of_date}
                      </span>
                    </div>

                    <h4 className="text-sm font-semibold text-slate-800 mb-1">{ev.title}</h4>
                    <p className="text-xs text-slate-500 italic mb-2">{ev.citation}</p>
                    <div className="rounded bg-white p-2.5 text-xs text-rose-900 border-l-2 border-rose-500 font-mono">
                      "{ev.excerpt}"
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "unknowns" && (
            <div className="space-y-3">
              {currentAsset.unknowns.length === 0 ? (
                <div className="text-center py-8 text-sm text-slate-500">
                  No pending critical unknowns flagged for this asset.
                </div>
              ) : (
                currentAsset.unknowns.map((u) => (
                  <div
                    key={u.id}
                    className="rounded-lg border border-purple-200 bg-purple-50/30 p-4 shadow-sm"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="rounded bg-purple-100 px-2.5 py-0.5 text-[10px] font-bold text-purple-800 uppercase">
                        {u.category}
                      </span>
                      <span className="text-[11px] font-mono text-purple-700">{u.id}</span>
                    </div>
                    <h4 className="text-xs font-bold text-slate-900 mb-1">
                      ❓ {u.question}
                    </h4>
                    <div className="text-xs text-slate-600 mb-2">
                      <strong className="text-slate-700">Current Knowledge Gap:</strong> {u.current_gap}
                    </div>
                    <div className="rounded bg-white p-2 text-xs text-purple-900 border border-purple-100 font-medium">
                      🧪 <strong>Recommended Translational Study:</strong> {u.suggested_study}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "lineage" && (
            <div className="space-y-4 text-xs">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h4 className="font-bold text-slate-900 mb-2 text-sm">
                  Development Potential Score Lineage (DPS)
                </h4>
                <div className="font-mono bg-white p-3 rounded border border-slate-200 text-slate-800 mb-3">
                  DPS = 0.20*Selectivity + 0.15*Potency + 0.20*SafetyTI + 0.15*CNSPotential + 0.15*Biomarker + 0.15*Readiness - SafetyPenalty
                </div>
                <div className="grid grid-cols-2 gap-3 text-slate-700">
                  <div>• Target Selectivity: {currentAsset.biology_profile.target_selectivity} (weight 0.20)</div>
                  <div>• Potency: {currentAsset.biology_profile.potency} (weight 0.15)</div>
                  <div>• Safety/Therapeutic Index: {currentAsset.biology_profile.safety_ti} (weight 0.20)</div>
                  <div>• CNS Penetration: {currentAsset.biology_profile.cns_potential} (weight 0.15)</div>
                  <div>• Biomarker Strategy: {currentAsset.biology_profile.biomarker_strategy} (weight 0.15)</div>
                  <div>• Clinical Readiness: {currentAsset.biology_profile.clinical_readiness} (weight 0.15)</div>
                </div>
                <div className="mt-3 pt-3 border-t border-slate-200 flex justify-between font-bold text-sm">
                  <span>Computed Score: {currentAsset.recommendation.development_potential_score}%</span>
                  <span className="text-emerald-700">Tier: {currentAsset.recommendation.development_potential_tier}</span>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <h4 className="font-bold text-slate-900 mb-2 text-sm">
                  Stage Transition Probability Engine (Model v0.1)
                </h4>
                <p className="text-slate-600 mb-2">
                  Calibrated Bayesian transition probabilities conditioned on oncology benchmark historical cohorts:
                </p>
                <div className="grid grid-cols-2 gap-2 text-slate-700 font-mono">
                  <div>Preclinical → IND: {Math.round(currentAsset.stage_transitions.preclinical_to_ind * 100)}%</div>
                  <div>Phase I → II: {Math.round(currentAsset.stage_transitions.phase_i_to_ii * 100)}%</div>
                  <div>Phase II → III: {Math.round(currentAsset.stage_transitions.phase_ii_to_iii * 100)}%</div>
                  <div>Phase III → Approval: {Math.round(currentAsset.stage_transitions.phase_iii_to_approval * 100)}%</div>
                </div>
              </div>
            </div>
          )}

          {activeTab === "inferences" && (
            <div className="space-y-3">
              <div className="rounded-md bg-amber-50 p-3 text-xs text-amber-800 border border-amber-200 mb-3">
                ⚠️ <strong>Explicit AI Inference Disclosure:</strong> The items below are computational hypotheses, molecular descriptors, and heuristic extrapolations. They are not direct wet-lab measurements.
              </div>
              {currentAsset.ai_inferences.map((inf, idx) => (
                <div
                  key={idx}
                  className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-700 shadow-sm flex items-start gap-2.5"
                >
                  <span className="rounded bg-sky-100 px-2 py-0.5 text-[10px] font-bold text-sky-800 shrink-0">
                    INFERENCE #{idx + 1}
                  </span>
                  <span>{inf}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Modal Footer with Mandatory Disclaimers */}
        <div className="border-t border-slate-200 bg-slate-50 px-6 py-3 flex flex-col md:flex-row items-center justify-between gap-3 text-[11px] text-slate-500">
          <div className="italic">
            ⚖️ <strong>Legal & Scientific Notice:</strong> IP/FTO indications are not legal advice. Human experts remain responsible for all translational, clinical, and investment decisions.
          </div>
          <button
            onClick={onClose}
            className="rounded-md bg-slate-800 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-700"
          >
            Close Dossier
          </button>
        </div>
      </div>
    </div>
  );
}
