"use client";

import React, { useState } from "react";
import { useWorkspace } from "../context/WorkspaceContext";
import { StrategicAction } from "../lib/types";

export function HumanDecisionModal() {
  const {
    isHumanDecisionModalOpen,
    setIsHumanDecisionModalOpen,
    asset1,
    humanDecisions,
    recordHumanDecision,
    setCurrentWorkflowStep,
  } = useWorkspace();

  const [selectedAction, setSelectedAction] = useState<StrategicAction>(
    asset1.recommendation.action
  );
  const [signerName, setSignerName] = useState("Dr. S. Kalyan");
  const [signerRole, setSignerRole] = useState("Principal Translational Oncologist");
  const [justification, setJustification] = useState(
    `Endorsing ${asset1.recommendation.action} recommendation. Clinical data shows favorable therapeutic index and mutant selectivity against HER2 exon 20 insertions.`
  );

  const [checklist, setChecklist] = useState({
    targetSpecificityVerified: true,
    wtSparingConfirmed: true,
    cnsDataReviewed: true,
    safetyToxicityAcceptable: true,
    ftoIpNonInfringing: true,
  });

  const [activeTab, setActiveTab] = useState<"signoff" | "history">("signoff");

  if (!isHumanDecisionModalOpen) return null;

  const isOverride = selectedAction !== asset1.recommendation.action;

  const handleSubmitDecision = (e: React.FormEvent) => {
    e.preventDefault();
    recordHumanDecision({
      assetId: asset1.id,
      assetName: asset1.name,
      aiRecommendation: asset1.recommendation.action,
      humanRecommendation: selectedAction,
      isOverride,
      signerName,
      signerRole,
      clinicalJustification: justification,
      checklist,
    });
    setCurrentWorkflowStep("human-decision");
    setActiveTab("history");
  };

  const actions: StrategicAction[] = [
    "PURSUE",
    "INVESTIGATE",
    "PARTNER",
    "LICENSE",
    "MONITOR",
    "AVOID",
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4">
      <div className="relative flex h-[88vh] w-full max-w-4xl flex-col rounded-xl border border-slate-700 bg-white shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-900 px-6 py-4 text-white">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-600 text-white font-bold">
              ✓
            </div>
            <div>
              <h2 className="text-base font-bold tracking-tight text-white">
                Human Expert Decision Sign-Off & Governance
              </h2>
              <p className="text-xs text-slate-400">
                Workflow Step 10 • Expert verification, strategic override, and auditable governance log
              </p>
            </div>
          </div>
          <button
            onClick={() => setIsHumanDecisionModalOpen(false)}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition"
          >
            ✕
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-200 bg-slate-50 px-6">
          <button
            onClick={() => setActiveTab("signoff")}
            className={`border-b-2 py-2.5 px-4 text-xs font-bold transition ${
              activeTab === "signoff"
                ? "border-blue-600 text-blue-700 bg-white"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Ratify / Override Decision
          </button>
          <button
            onClick={() => setActiveTab("history")}
            className={`border-b-2 py-2.5 px-4 text-xs font-bold transition ${
              activeTab === "history"
                ? "border-blue-600 text-blue-700 bg-white"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            Governance Audit Trail ({humanDecisions.length})
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "signoff" ? (
            <form onSubmit={handleSubmitDecision} className="space-y-5">
              {/* Context Summary */}
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                      Target Asset Under Review
                    </span>
                    <h3 className="text-lg font-bold text-slate-900 mt-0.5">
                      {asset1.name} ({asset1.stage} • {asset1.target})
                    </h3>
                    <p className="text-xs text-slate-600 mt-0.5">
                      Sponsor: {asset1.owner} | Primary Indication: {asset1.primary_indication}
                    </p>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                      AI Model Recommendation
                    </span>
                    <div className="flex items-center justify-end gap-2 mt-0.5">
                      <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-bold text-blue-800">
                        {asset1.recommendation.action}
                      </span>
                      <span className="text-xs font-medium text-slate-600">
                        ({asset1.recommendation.confidence}% conf • DPS: {asset1.recommendation.development_potential_score}%)
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Selection */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                  Select Human Ratified Recommendation
                </label>
                <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                  {actions.map((act) => {
                    const isSelected = selectedAction === act;
                    const isAi = asset1.recommendation.action === act;
                    return (
                      <button
                        key={act}
                        type="button"
                        onClick={() => setSelectedAction(act)}
                        className={`rounded-lg border p-2 text-center text-xs font-bold transition ${
                          isSelected
                            ? "border-blue-600 bg-blue-600 text-white shadow"
                            : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <div>{act}</div>
                        {isAi && (
                          <div
                            className={`text-[9px] mt-0.5 ${
                              isSelected ? "text-blue-200" : "text-blue-600"
                            }`}
                          >
                            (AI Suggested)
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>

                {isOverride && (
                  <div className="mt-2 rounded-md bg-amber-50 border border-amber-200 p-2 text-xs text-amber-800 flex items-center gap-2">
                    <span className="font-bold">⚠️ Strategic Override:</span>
                    <span>
                      You are changing the AI recommendation from <strong>{asset1.recommendation.action}</strong> to <strong>{selectedAction}</strong>. Clinical justification is mandatory.
                    </span>
                  </div>
                )}
              </div>

              {/* Clinical Justification */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-1">
                  Clinical & Strategic Justification (Auditable Record)
                </label>
                <textarea
                  rows={3}
                  required
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  placeholder="Detail scientific rationale, risk mitigations, combination strategy, or translational counter-evidence..."
                  className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800 placeholder-slate-400 focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* Sign-Off Checklist */}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-700 mb-2">
                  Mandatory Translational Governance Checklist
                </label>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                  <label className="flex items-center gap-2 rounded border border-slate-200 p-2 bg-slate-50/50 cursor-pointer hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={checklist.targetSpecificityVerified}
                      onChange={(e) =>
                        setChecklist({ ...checklist, targetSpecificityVerified: e.target.checked })
                      }
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-slate-700 font-medium">
                      Target selectivity and potency validated
                    </span>
                  </label>

                  <label className="flex items-center gap-2 rounded border border-slate-200 p-2 bg-slate-50/50 cursor-pointer hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={checklist.wtSparingConfirmed}
                      onChange={(e) =>
                        setChecklist({ ...checklist, wtSparingConfirmed: e.target.checked })
                      }
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-slate-700 font-medium">
                      Wild-type sparing / GI toxicity index verified
                    </span>
                  </label>

                  <label className="flex items-center gap-2 rounded border border-slate-200 p-2 bg-slate-50/50 cursor-pointer hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={checklist.cnsDataReviewed}
                      onChange={(e) =>
                        setChecklist({ ...checklist, cnsDataReviewed: e.target.checked })
                      }
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-slate-700 font-medium">
                      CNS brain penetration data reviewed
                    </span>
                  </label>

                  <label className="flex items-center gap-2 rounded border border-slate-200 p-2 bg-slate-50/50 cursor-pointer hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={checklist.safetyToxicityAcceptable}
                      onChange={(e) =>
                        setChecklist({ ...checklist, safetyToxicityAcceptable: e.target.checked })
                      }
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-slate-700 font-medium">
                      Safety & maximum tolerated dose bounds confirmed
                    </span>
                  </label>

                  <label className="flex items-center gap-2 rounded border border-slate-200 p-2 bg-slate-50/50 cursor-pointer hover:bg-slate-50">
                    <input
                      type="checkbox"
                      checked={checklist.ftoIpNonInfringing}
                      onChange={(e) =>
                        setChecklist({ ...checklist, ftoIpNonInfringing: e.target.checked })
                      }
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-slate-700 font-medium">
                      Freedom-to-operate / IP landscape clear
                    </span>
                  </label>
                </div>
              </div>

              {/* Signer Identity */}
              <div className="grid grid-cols-2 gap-4 border-t border-slate-200 pt-4 text-xs">
                <div>
                  <label className="block font-semibold text-slate-600 mb-1">
                    Signatory Name
                  </label>
                  <input
                    type="text"
                    required
                    value={signerName}
                    onChange={(e) => setSignerName(e.target.value)}
                    className="w-full rounded border border-slate-300 p-2 text-xs text-slate-800"
                  />
                </div>
                <div>
                  <label className="block font-semibold text-slate-600 mb-1">
                    Professional Role / Title
                  </label>
                  <input
                    type="text"
                    required
                    value={signerRole}
                    onChange={(e) => setSignerRole(e.target.value)}
                    className="w-full rounded border border-slate-300 p-2 text-xs text-slate-800"
                  />
                </div>
              </div>

              {/* Submit Button */}
              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  className="rounded-lg bg-emerald-600 px-5 py-2.5 text-xs font-bold text-white hover:bg-emerald-500 shadow-md transition"
                >
                  ✓ Ratify & Commit Decision into Audit Log
                </button>
              </div>
            </form>
          ) : (
            /* History Tab */
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Historical Expert Sign-Offs & Decisions
                </h3>
                <span className="text-xs text-slate-400">
                  Immutable Governance Trail
                </span>
              </div>

              <div className="space-y-3">
                {humanDecisions.map((dec) => (
                  <div
                    key={dec.id}
                    className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-slate-900">
                            {dec.assetName}
                          </span>
                          <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-800">
                            Ratified: {dec.humanRecommendation}
                          </span>
                          {dec.isOverride && (
                            <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                              OVERRIDE (AI was {dec.aiRecommendation})
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                          Signed by <strong>{dec.signerName}</strong> ({dec.signerRole}) on{" "}
                          <span className="font-mono text-slate-600">{dec.timestamp}</span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-3 rounded bg-slate-50 p-3 border border-slate-100 text-xs text-slate-700 leading-relaxed">
                      <strong>Clinical Justification:</strong> {dec.clinicalJustification}
                    </div>

                    <div className="mt-2.5 flex flex-wrap gap-2 text-[10px]">
                      {dec.checklist.targetSpecificityVerified && (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          ✓ Target Verified
                        </span>
                      )}
                      {dec.checklist.wtSparingConfirmed && (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          ✓ WT-Sparing Confirmed
                        </span>
                      )}
                      {dec.checklist.cnsDataReviewed && (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          ✓ CNS Data Reviewed
                        </span>
                      )}
                      {dec.checklist.safetyToxicityAcceptable && (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          ✓ Safety Acceptable
                        </span>
                      )}
                      {dec.checklist.ftoIpNonInfringing && (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                          ✓ FTO Verified
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-3">
          <span className="text-[11px] text-slate-500">
            AI recommendations do not constitute formal medical or legal advice. Final responsibility rests with human decision-makers.
          </span>
          <button
            onClick={() => setIsHumanDecisionModalOpen(false)}
            className="rounded px-4 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
