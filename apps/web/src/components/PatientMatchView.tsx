"use client";

import React, { useState } from "react";
import { AssetIntelligence } from "../lib/types";

export interface PatientMatchViewProps {
  assets: AssetIntelligence[];
}

export function PatientMatchView({ assets }: PatientMatchViewProps) {
  const [selectedMutation, setSelectedMutation] = useState<string>("HER2_MUTANT_L755S");
  const [hormoneStatus, setHormoneStatus] = useState<string>("ER_POS_NON_AMP");
  const [hasCnsMets, setHasCnsMets] = useState<boolean>(true);
  const [priorTherapy, setPriorTherapy] = useState<string>("POST_CDK46");

  const calculateMatches = () => {
    return assets.map((asset) => {
      let score = 50;
      const reasons: string[] = [];
      let combo = "";
      const resistanceRisks: string[] = [];
      let cnsBenefit = false;

      if (asset.id === "zongertinib") {
        if (selectedMutation === "HER2_MUTANT_L755S" || selectedMutation === "HER2_EXON_20") {
          score += 35;
          reasons.push("Potent selective inhibition against HER2 kinase mutations (L755S/V777L/exon 20).");
        }
        if (hasCnsMets) {
          score += 15;
          reasons.push("Blood-brain barrier penetration provides intracranial response.");
          cnsBenefit = true;
        }
        if (hormoneStatus === "ER_POS_NON_AMP") {
          combo = "+ Endocrine therapy (e.g., fulvestrant)";
          resistanceRisks.push("ER pathway compensatory reactivation requires concurrent endocrine suppression.");
        }
      } else if (asset.id === "neratinib") {
        if (selectedMutation === "HER2_AMP") {
          score += 30;
          reasons.push("Clinically validated in amplified disease (ExteNET).");
        } else {
          score -= 15;
          reasons.push("Lower mutant selectivity; wild-type EGFR-driven diarrhea limits dose intensity.");
        }
        if (hasCnsMets) {
          score += 5;
          cnsBenefit = false;
        }
        combo = "+ Capecitabine";
        resistanceRisks.push("High incidence of treatment-limiting diarrhea; HER2 reactivation.");
      } else if (asset.id === "tucatinib") {
        if (hasCnsMets) {
          score += 35;
          reasons.push("Clinically established intracranial OS advantage (HER2CLIMB).");
          cnsBenefit = true;
        }
        if (selectedMutation === "HER2_AMP") {
          score += 15;
        }
        combo = "+ Trastuzumab + Capecitabine";
      } else {
        score = 15;
        reasons.push("Narrow therapeutic window with severe off-target EGFR toxicities.");
      }

      return {
        asset,
        matchScore: Math.max(0, Math.min(100, score)),
        reasons,
        recommendedCombination: combo || "+ Trastuzumab",
        resistanceRisks,
        cnsBenefit,
      };
    }).sort((a, b) => b.matchScore - a.matchScore);
  };

  const matches = calculateMatches();

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-6 py-4 text-slate-800">
      <div className="border-b border-slate-200 pb-3">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">
          Precision Patient Stratification & Biomarker Match
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Stratify patient genomic alterations, line of therapy, and intracranial involvement to identify optimal asset candidates
        </p>
      </div>

      {/* Input Parameters Form */}
      <div className="mt-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-800 mb-3">
          Patient Profile Parameters
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">
              HER2 Alteration / Mutation
            </label>
            <select
              value={selectedMutation}
              onChange={(e) => setSelectedMutation(e.target.value)}
              className="w-full rounded border border-slate-300 bg-slate-50 p-2 text-xs font-medium text-slate-800 outline-none"
            >
              <option value="HER2_MUTANT_L755S">HER2 Kinase Domain Mutant (L755S / V777L)</option>
              <option value="HER2_EXON_20">HER2 Exon 20 Insertion (A775_G776insYVMA)</option>
              <option value="HER2_AMP">HER2 Amplified (IHC 3+ / FISH+)</option>
              <option value="HER2_LOW">HER2 Low (IHC 1+ or 2+/FISH-)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">
              Hormone Receptor (ER/PR) Status
            </label>
            <select
              value={hormoneStatus}
              onChange={(e) => setHormoneStatus(e.target.value)}
              className="w-full rounded border border-slate-300 bg-slate-50 p-2 text-xs font-medium text-slate-800 outline-none"
            >
              <option value="ER_POS_NON_AMP">ER-positive / HER2 Non-Amplified</option>
              <option value="ER_POS_HER2_AMP">Triple Positive (ER+ / HER2-amplified)</option>
              <option value="ER_NEG_HER2_AMP">ER-negative / HER2-amplified</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">
              Prior Systemic Regimens
            </label>
            <select
              value={priorTherapy}
              onChange={(e) => setPriorTherapy(e.target.value)}
              className="w-full rounded border border-slate-300 bg-slate-50 p-2 text-xs font-medium text-slate-800 outline-none"
            >
              <option value="POST_CDK46">Post-CDK4/6 inhibitor + Aromatase Inhibitor</option>
              <option value="POST_TRASTUZUMAB">Post-Adjuvant Trastuzumab</option>
              <option value="POST_TDXD">Post-Trastuzumab Deruxtecan (T-DXd)</option>
            </select>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-slate-600 mb-1">
              CNS / Brain Metastasis Status
            </label>
            <div className="flex items-center gap-3 mt-2">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="cns"
                  checked={hasCnsMets}
                  onChange={() => setHasCnsMets(true)}
                  className="text-blue-600"
                />
                <span className="font-medium text-slate-800">Active CNS Mets</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="cns"
                  checked={!hasCnsMets}
                  onChange={() => setHasCnsMets(false)}
                  className="text-blue-600"
                />
                <span className="font-medium text-slate-800">No CNS Mets</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      {/* Match Results */}
      <div className="mt-6 space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-600">
          Ranked Candidate Matches ({matches.length})
        </h2>

        {matches.map((item, idx) => (
          <div
            key={item.asset.id}
            className={`rounded-lg border p-4 shadow-sm bg-white transition-all ${
              idx === 0
                ? "border-emerald-300 ring-1 ring-emerald-400/40"
                : "border-slate-200"
            }`}
          >
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-900 text-[10px] font-bold text-white">
                    #{idx + 1}
                  </span>
                  <h3 className="text-base font-bold text-slate-900">
                    {item.asset.name}
                  </h3>
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800">
                    {item.asset.target}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                    {item.asset.stage}
                  </span>
                  {idx === 0 && (
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                      TOP STRATIFIED MATCH
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  Owner: {item.asset.owner} | Modality: {item.asset.modality}
                </div>
              </div>

              <div className="flex items-center gap-4">
                <div className="text-right">
                  <div className="text-[10px] text-slate-400 font-semibold uppercase">
                    Match Score
                  </div>
                  <div
                    className={`text-2xl font-bold ${
                      item.matchScore >= 80
                        ? "text-emerald-700"
                        : item.matchScore >= 50
                        ? "text-blue-700"
                        : "text-amber-700"
                    }`}
                  >
                    {item.matchScore}%
                  </div>
                </div>
              </div>
            </div>

            {/* Rationale and Details */}
            <div className="mt-3 pt-3 border-t border-slate-100 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
              <div className="md:col-span-2 space-y-1.5">
                <div className="font-semibold text-slate-700">Match Rationale:</div>
                <ul className="space-y-1 text-slate-600">
                  {item.reasons.map((r, rIdx) => (
                    <li key={rIdx} className="flex items-start gap-1.5">
                      <span className="text-blue-600 font-bold">•</span>
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>

                {item.resistanceRisks.length > 0 && (
                  <div className="mt-2 rounded bg-amber-50 p-2 text-amber-900 border border-amber-200">
                    ⚠️ <strong>Resistance Risk Alert:</strong> {item.resistanceRisks.join(" ")}
                  </div>
                )}
              </div>

              <div className="rounded bg-slate-50 p-3 space-y-2">
                <div>
                  <div className="text-[10px] font-semibold text-slate-500">
                    RECOMMENDED REGIMEN
                  </div>
                  <div className="font-bold text-slate-800">
                    {item.asset.name} {item.recommendedCombination}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold text-slate-500">
                    INTRACRANIAL PENETRATION
                  </div>
                  <div className={`font-semibold ${item.cnsBenefit ? "text-emerald-700" : "text-slate-600"}`}>
                    {item.cnsBenefit ? "✓ Blood-Brain Barrier Active" : "Limited Intracranial Coverage"}
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
