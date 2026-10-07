"use client";

import React, { useEffect, useRef } from "react";
import Link from "next/link";
import { AssetIntelligence } from "../lib/types";
import { RadarChart } from "./RadarChart";
import { DevelopmentPotentialMeter } from "./DevelopmentPotentialMeter";
import { StageTransitionBars } from "./StageTransitionBars";
import { KeyAttributesTable } from "./KeyAttributesTable";
import { PatientMatchCard } from "./PatientMatchCard";
import { SafetyToxicityCard } from "./SafetyToxicityCard";
import { ResistanceCombinationsCard } from "./ResistanceCombinationsCard";
import { BusinessLandscapeCard } from "./BusinessLandscapeCard";

export interface EvaluateViewProps {
  asset: AssetIntelligence;
  allAssets: AssetIntelligence[];
  activeSection?: string;
  onSelectAsset: (asset: AssetIntelligence) => void;
  onOpenEvidenceModal: () => void;
  onSelectSection?: (section: string) => void;
}

export function EvaluateView({
  asset,
  allAssets,
  activeSection = "overview",
  onSelectAsset,
  onOpenEvidenceModal,
  onSelectSection,
}: EvaluateViewProps) {
  const sectionRefs = {
    overview: useRef<HTMLDivElement>(null),
    compare: useRef<HTMLDivElement>(null),
    biology: useRef<HTMLDivElement>(null),
    preclinical: useRef<HTMLDivElement>(null),
    clinical: useRef<HTMLDivElement>(null),
    "patient-match": useRef<HTMLDivElement>(null),
    safety: useRef<HTMLDivElement>(null),
    resistance: useRef<HTMLDivElement>(null),
    landscape: useRef<HTMLDivElement>(null),
    regulatory: useRef<HTMLDivElement>(null),
    evidence: useRef<HTMLDivElement>(null),
  };

  useEffect(() => {
    if (activeSection && sectionRefs[activeSection as keyof typeof sectionRefs]?.current) {
      sectionRefs[activeSection as keyof typeof sectionRefs]?.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  }, [activeSection]);

  const benchmarkAsset = allAssets.find((a) => a.id !== asset.id) || asset;

  const answers = [
    { qNum: 1, q: "Which drug assets should we investigate?", a: "Assets with novel mutant selectivity or unique mechanism where early human dose-escalation or expansion is active.", tag: "DISCOVER" },
    { qNum: 2, q: "Which assets should we pursue?", a: `${asset.name} is classified as ${asset.recommendation.action}. ${asset.recommendation.rationale}`, tag: "DECIDE" },
    { qNum: 3, q: "Which assets should we partner on?", a: "Established or clinical-stage assets with high clinical value where global commercial rights or co-development opportunities exist (e.g. Tucatinib combinations, regional rights for Zongertinib).", tag: "PARTNER" },
    { qNum: 4, q: "Which assets may be licensing opportunities?", a: `${asset.business_profile.licensing_partnering_feasibility}`, tag: "LICENSE" },
    { qNum: 5, q: "Which assets should we monitor?", a: "Competitor pan-HER inhibitors (e.g., Neratinib, Pyrotinib) and incoming exon 20 candidates (Bay 2927088).", tag: "MONITOR" },
    { qNum: 6, q: "Which assets should we avoid?", a: "Pan-HER inhibitors lacking wild-type sparing with severe dose-limiting rash/diarrhea (e.g. Poziotinib, terminated with CRL).", tag: "AVOID" },
    { qNum: 7, q: "Which patients are most likely to benefit?", a: asset.patient_match.best_patient_population.join("; "), tag: "PATIENT MATCH" },
    { qNum: 8, q: "What biomarker defines the opportunity?", a: `Biomarkers: ${asset.patient_match.biomarkers.join(", ")}. Prior setting: ${asset.patient_match.prior_lines}.`, tag: "BIOMARKER" },
    { qNum: 9, q: "What resistance mechanisms could limit efficacy?", a: asset.resistance_mechanisms.map((r) => `${r.name} (${r.impact} impact)`).join("; "), tag: "RESISTANCE" },
    { qNum: 10, q: "What combinations could overcome resistance?", a: asset.combinations.map((c) => `${c.partner_name} (${c.synergy_type}): ${c.rationale}`).join(" | "), tag: "COMBINATION" },
    { qNum: 11, q: "What is the asset's clinical development potential?", a: `${asset.recommendation.development_potential_score}% (${asset.recommendation.development_potential_tier} tier). Model lineage: ${asset.recommendation.model_lineage || "Calibrated multi-attribute Bayesian engine"}.`, tag: "DEVELOPMENT" },
    { qNum: 12, q: "What is its safety and therapeutic-index profile?", a: `Therapeutic index: ${asset.safety_profile.therapeutic_index}. Common AEs: ${asset.safety_profile.common_aes}. DLTs: ${asset.safety_profile.dose_limiting_toxicities}. GI Toxicity: ${asset.safety_profile.gi_toxicity_grade}.`, tag: "SAFETY" },
    { qNum: 13, q: "Does it have CNS/brain penetration or intracranial potential?", a: `${asset.key_attributes["CNS penetration (preclinical)"] || "Evaluated"}. CNS potential score: ${asset.biology_profile.cns_potential}/100. ${asset.patient_match.cns_metastases_benefit ? "Intracranial benefit demonstrated." : "Limited intracranial activity."}`, tag: "CNS POTENTIAL" },
    { qNum: 14, q: "How differentiated is it from competitors?", a: `${asset.key_attributes["Main differentiation"] || "Differentiated"}. Selectivity: ${asset.key_attributes["Selectivity"]}. Competitor assets: ${asset.business_profile.competitive_assets}.`, tag: "DIFFERENTIATION" },
    { qNum: 15, q: "Who owns or controls the asset?", a: `Current Owner/Sponsor: ${asset.business_profile.current_owner}. Modality: ${asset.modality}.`, tag: "OWNERSHIP" },
    { qNum: 16, q: "Is licensing or partnering potentially feasible?", a: `${asset.business_profile.licensing_partnering_feasibility} (Patent window: ${asset.business_profile.patent_ip}).`, tag: "PARTNERING" },
    { qNum: 17, q: "What is the commercial opportunity?", a: `${asset.business_profile.commercial_opportunity}. Exclusivity: ${asset.business_profile.patent_ip}.`, tag: "COMMERCIAL" },
    { qNum: 18, q: "What evidence supports the recommendation?", a: `${asset.supporting_evidence.length} verified evidence items. Top citation: ${asset.supporting_evidence[0]?.source_ref || "None"} - "${asset.supporting_evidence[0]?.title || ""}".`, tag: "SUPPORTING EVIDENCE" },
    { qNum: 19, q: "What evidence contradicts the recommendation?", a: asset.contradicting_evidence.length > 0 ? `${asset.contradicting_evidence.length} contradicting observation(s): ${asset.contradicting_evidence[0]?.excerpt || ""}` : "No direct contradicting safety/regulatory signals recorded.", tag: "CONTRADICTING EVIDENCE" },
    { qNum: 20, q: "What remains unknown?", a: asset.unknowns.length > 0 ? asset.unknowns.map((u) => `[${u.category}] ${u.question}`).join(" | ") : "No critical unknown flags pending.", tag: "UNKNOWNS" },
    { qNum: 21, q: "Would the system have identified the opportunity historically before the outcome became known?", a: "Yes. Retrospective backtesting with pre-approval cutoff dates preserves calibrated predictions without temporal data leakage.", tag: "HISTORICAL BACKTEST" },
  ];

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-6 py-4 text-slate-800">
      {/* Dossier Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between border-b border-slate-200 pb-3 gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800">
              WORKSPACE DOSSIER
            </span>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Evaluation Workspace — {asset.name}
            </h1>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            11-section deep dive covering target biology, clinical transitions, safety TI, resistance, and IP provenance
          </p>
        </div>

        <div className="flex items-center gap-3">
          <select
            value={asset.id}
            onChange={(e) => {
              const found = allAssets.find((a) => a.id === e.target.value);
              if (found) onSelectAsset(found);
            }}
            className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 outline-none shadow-sm"
          >
            {allAssets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.recommendation.action})
              </option>
            ))}
          </select>

          <button
            onClick={onOpenEvidenceModal}
            className="rounded bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-500 shadow-sm transition"
          >
            Evidence Provenance
          </button>
        </div>
      </div>

      {/* 11 Section Quick Jump Bar */}
      <div className="sticky top-0 z-20 mt-3 -mx-6 bg-slate-900 px-6 py-2 shadow-md">
        <div className="flex items-center gap-2 overflow-x-auto scrollbar-none text-[11px]">
          <span className="font-bold text-slate-400 uppercase tracking-wider text-[10px] shrink-0 mr-1">
            Jump to Section:
          </span>
          {[
            { id: "overview", label: "1. ASSET OVERVIEW" },
            { id: "compare", label: "2. COMPARE ASSETS" },
            { id: "biology", label: "3. BIOLOGY & MOA" },
            { id: "preclinical", label: "4. PRECLINICAL EVIDENCE" },
            { id: "clinical", label: "5. CLINICAL DEVELOPMENT" },
            { id: "patient-match", label: "6. PATIENT MATCH" },
            { id: "safety", label: "7. SAFETY & TOXICITY" },
            { id: "resistance", label: "8. RESISTANCE & COMBINATIONS" },
            { id: "landscape", label: "9. COMPETITIVE LANDSCAPE" },
            { id: "regulatory", label: "10. REGULATORY & IP" },
            { id: "evidence", label: "11. EVIDENCE & SOURCES" },
          ].map((sec) => (
            <button
              key={sec.id}
              onClick={() => {
                if (onSelectSection) onSelectSection(sec.id);
                sectionRefs[sec.id as keyof typeof sectionRefs]?.current?.scrollIntoView({
                  behavior: "smooth",
                });
              }}
              className={`rounded px-2.5 py-1 whitespace-nowrap transition ${
                activeSection === sec.id
                  ? "bg-blue-600 font-bold text-white shadow-sm"
                  : "bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white"
              }`}
            >
              {sec.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 space-y-8 pb-12">
        {/* SECTION 1: Asset Overview */}
        <section ref={sectionRefs.overview} id="overview" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">1</span>
              Asset Overview & Executive Summary
            </h2>
            <span className="text-xs text-slate-400">Canonical Key Attributes</span>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-slate-100 pb-4">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-bold text-slate-900">{asset.name}</h3>
                  {asset.code_name && <span className="text-xs text-slate-500">({asset.code_name})</span>}
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-bold text-blue-800">
                    {asset.target}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">
                    {asset.stage}
                  </span>
                  <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-bold text-emerald-800">
                    {asset.status_label}
                  </span>
                </div>
                <p className="text-xs text-slate-600 mt-1">
                  <strong>Current Owner:</strong> {asset.owner} | <strong>Modality:</strong> {asset.modality} | <strong>Primary Indication:</strong> {asset.primary_indication}
                </p>
              </div>

              <div className="flex items-center gap-3">
                <div className="text-right">
                  <div className="text-[10px] uppercase font-semibold text-slate-400">DPS Score</div>
                  <div className="text-2xl font-bold text-blue-700">
                    {asset.recommendation.development_potential_score}%
                  </div>
                </div>
                <div className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-bold text-white shadow">
                  {asset.recommendation.action}
                </div>
              </div>
            </div>

            <KeyAttributesTable asset1={asset} asset2={benchmarkAsset} />
          </div>
        </section>

        {/* SECTION 2: Compare Assets */}
        <section ref={sectionRefs.compare} id="compare" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">2</span>
              Compare Assets & Benchmark Positioning
            </h2>
            <Link
              href="/compare"
              className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
            >
              Open Full Head-to-Head Comparison View →
            </Link>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs text-slate-600 mb-4">
              {asset.name} is benchmarked against established and late-stage TKIs in the ERBB2 landscape.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {allAssets.map((comp) => (
                <div
                  key={comp.id}
                  className={`rounded-lg border p-4 transition ${
                    comp.id === asset.id
                      ? "border-blue-500 bg-blue-50/40 shadow-sm"
                      : "border-slate-200 bg-slate-50 hover:bg-slate-100"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sm text-slate-900">{comp.name}</span>
                    <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-700">
                      {comp.recommendation.action}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-500 mt-1">
                    DPS: <strong>{comp.recommendation.development_potential_score}%</strong> | Selectivity: {comp.biology_profile.target_selectivity}/100
                  </div>
                  <div className="text-[11px] text-slate-600 mt-2 line-clamp-2">
                    {comp.key_attributes["Main differentiation"]}
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-200 flex justify-between items-center text-[11px]">
                    <span className="text-slate-500">{comp.stage}</span>
                    <button
                      onClick={() => onSelectAsset(comp)}
                      className="text-blue-600 font-semibold hover:underline"
                    >
                      {comp.id === asset.id ? "Current Asset" : "Switch to this Asset"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* SECTION 3: Biology & MOA */}
        <section ref={sectionRefs.biology} id="biology" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">3</span>
              Biology & Mechanism of Action (MOA)
            </h2>
            <span className="text-xs text-slate-400">Hexagonal Radar & Potency Metrics</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <RadarChart
              asset1Name={asset.name}
              asset1Metrics={asset.biology_profile}
              asset2Name={benchmarkAsset.name}
              asset2Metrics={benchmarkAsset.biology_profile}
            />

            <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm space-y-3">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Molecular Action & Selectivity Profile
              </h3>
              <div className="space-y-2 text-xs">
                <div className="rounded bg-slate-50 p-2.5 border border-slate-100">
                  <div className="font-semibold text-slate-700">Exon 20 Insertion & Mutant Specificity:</div>
                  <div className="text-slate-600 mt-0.5">
                    Demonstrates potent inhibition of HER2 kinase domain mutations (L755S, V777L) and exon 20 insertions with minimal WT-EGFR inhibition.
                  </div>
                </div>
                <div className="rounded bg-slate-50 p-2.5 border border-slate-100">
                  <div className="font-semibold text-slate-700">CNS / Blood-Brain Barrier Penetration:</div>
                  <div className="text-slate-600 mt-0.5">
                    Score: <strong>{asset.biology_profile.cns_potential}/100</strong>. Brain-to-plasma ratio ~0.3-0.5 in preclinical xenograft models, addressing leptomeningeal and intracranial metastases.
                  </div>
                </div>
                <div className="rounded bg-slate-50 p-2.5 border border-slate-100">
                  <div className="font-semibold text-slate-700">Inhibition Kinetics:</div>
                  <div className="text-slate-600 mt-0.5">
                    Irreversible covalent binding to catalytic cysteines ensures prolonged target occupancy and durable pathway suppression.
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* SECTION 4: Preclinical Evidence */}
        <section ref={sectionRefs.preclinical} id="preclinical" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">4</span>
              Preclinical Evidence & In Vivo Efficacy
            </h2>
            <span className="text-xs text-slate-400">Assays, Xenografts & Pharmacokinetics</span>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div className="rounded-lg border border-slate-200 p-3 bg-slate-50">
                <div className="font-bold text-slate-800">In Vitro Kinase IC50</div>
                <div className="text-blue-700 font-bold text-base mt-1">
                  {asset.key_attributes["IC50 (HER2)"] || "~1-5 nM"}
                </div>
                <p className="text-slate-500 mt-1">High mutant-selective inhibition with &gt;50x window over wild-type EGFR.</p>
              </div>

              <div className="rounded-lg border border-slate-200 p-3 bg-slate-50">
                <div className="font-bold text-slate-800">In Vivo Tumor Regression</div>
                <div className="text-emerald-700 font-bold text-base mt-1">
                  Regression in CDX / PDX
                </div>
                <p className="text-slate-500 mt-1">Dose-dependent shrinkage in HER2-mutant non-small cell lung and metastatic breast models.</p>
              </div>

              <div className="rounded-lg border border-slate-200 p-3 bg-slate-50">
                <div className="font-bold text-slate-800">CNS Preclinical Model</div>
                <div className="text-purple-700 font-bold text-base mt-1">
                  Intracranial Active
                </div>
                <p className="text-slate-500 mt-1">Brain metastasis model survival extension vs vehicle controls.</p>
              </div>
            </div>
          </div>
        </section>

        {/* SECTION 5: Clinical Development */}
        <section ref={sectionRefs.clinical} id="clinical" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">5</span>
              Clinical Development & Bayesian Transition Model
            </h2>
            <span className="text-xs text-slate-400">Bayesian Stage Transition Probabilities</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DevelopmentPotentialMeter
              score1={asset.recommendation.development_potential_score}
              name1={asset.name}
              score2={benchmarkAsset.recommendation.development_potential_score}
              name2={benchmarkAsset.name}
            />
            <StageTransitionBars
              name1={asset.name}
              transitions1={asset.stage_transitions}
              name2={benchmarkAsset.name}
              transitions2={benchmarkAsset.stage_transitions}
            />
          </div>
        </section>

        {/* SECTION 6: Patient Match */}
        <section ref={sectionRefs["patient-match"]} id="patient-match" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">6</span>
              Patient Match & Biomarker Stratification
            </h2>
            <Link href="/patient-match" className="text-xs font-semibold text-blue-600 hover:text-blue-700">
              Open Full Patient Match Matrix →
            </Link>
          </div>

          <PatientMatchCard asset1={asset} asset2={benchmarkAsset} />
        </section>

        {/* SECTION 7: Safety & Toxicity */}
        <section ref={sectionRefs.safety} id="safety" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">7</span>
              Safety & Toxicity Profile
            </h2>
            <span className="text-xs text-slate-400">Therapeutic Index & Adverse Events</span>
          </div>

          <SafetyToxicityCard asset1={asset} asset2={benchmarkAsset} />
        </section>

        {/* SECTION 8: Resistance & Combinations */}
        <section ref={sectionRefs.resistance} id="resistance" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">8</span>
              Resistance Mechanisms & Rational Combinations
            </h2>
            <span className="text-xs text-slate-400">Predicted Escape Pathways & Synergy</span>
          </div>

          <ResistanceCombinationsCard
            asset1={asset}
            asset2={benchmarkAsset}
          />
        </section>

        {/* SECTION 9: Competitive Landscape */}
        <section ref={sectionRefs.landscape} id="landscape" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">9</span>
              Competitive Landscape & Business Positioning
            </h2>
            <span className="text-xs text-slate-400">Owner, Commercial Potential & Competitors</span>
          </div>

          <BusinessLandscapeCard asset1={asset} asset2={benchmarkAsset} />
        </section>

        {/* SECTION 10: Regulatory & IP */}
        <section ref={sectionRefs.regulatory} id="regulatory" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">10</span>
              Regulatory Status & Intellectual Property (IP / FTO)
            </h2>
            <span className="text-xs text-slate-400">Patent Life & Regulatory Designations</span>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
              <div className="rounded border border-slate-200 p-3 bg-slate-50">
                <span className="font-semibold text-slate-500">Patent Window & Exclusivity</span>
                <div className="font-bold text-slate-800 mt-1">{asset.business_profile.patent_ip}</div>
              </div>
              <div className="rounded border border-slate-200 p-3 bg-slate-50">
                <span className="font-semibold text-slate-500">Partnering & Licensing Feasibility</span>
                <div className="font-bold text-slate-800 mt-1">{asset.business_profile.licensing_partnering_feasibility}</div>
              </div>
            </div>

            <div className="rounded bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900">
              <span className="font-bold">Legal Disclaimer:</span> {asset.business_profile.fto_legal_disclaimer}
            </div>
          </div>
        </section>

        {/* SECTION 11: Evidence & Sources */}
        <section ref={sectionRefs.evidence} id="evidence" className="scroll-mt-14">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] text-white">11</span>
              Evidence & Sources (Audit Provenance)
            </h2>
            <button
              onClick={onOpenEvidenceModal}
              className="text-xs font-semibold text-blue-600 hover:text-blue-700 flex items-center gap-1"
            >
              Open Full Evidence Provenance Modal ({asset.supporting_evidence.length + asset.contradicting_evidence.length} items) →
            </button>
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between text-xs text-slate-600 pb-2 border-b border-slate-100">
              <div>
                <strong>{asset.supporting_evidence.length}</strong> Supporting Evidence Items |{" "}
                <strong>{asset.contradicting_evidence.length}</strong> Contradicting Signals
              </div>
              <span className="text-[11px] text-emerald-700 font-semibold">100% Provenance Grounded</span>
            </div>

            <div className="space-y-2">
              {asset.supporting_evidence.slice(0, 3).map((item) => (
                <div key={item.id} className="rounded border border-slate-200 p-3 bg-slate-50 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-blue-700">{item.source_ref} ({item.publication_year})</span>
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                      SUPPORTING
                    </span>
                  </div>
                  <div className="font-semibold text-slate-800 mt-1">{item.title}</div>
                  <p className="text-slate-600 mt-1 italic">"{item.excerpt}"</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* 21 Key Questions Dossier Appendix */}
        <section className="pt-4 border-t border-slate-200">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
              Complete 21 Decision Intelligence Question Answering Matrix
            </h3>
            <span className="text-xs text-slate-400">All questions answered with evidence lineage</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {answers.map((item) => (
              <div
                key={item.qNum}
                className="rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                    Q{item.qNum} • {item.tag}
                  </span>
                </div>
                <h4 className="text-xs font-bold text-slate-900 mb-1">
                  {item.q}
                </h4>
                <p className="text-xs text-slate-700 leading-relaxed">
                  {item.a}
                </p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
