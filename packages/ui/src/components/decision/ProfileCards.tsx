"use client";

import React from "react";
import { cn } from "../../lib/utils";
import {
  AssetIntelligence,
  PatientMatchProfile,
  RecommendedCombination,
  ResistanceMechanism,
  SafetyToxicityProfile,
  StageTransitionProbabilities,
} from "@ai-rxos/types";
import { ScoreGauge, RadarProfile } from "./ScoringComponents";

// ==========================================
// 1. KeyAttributesTable
// ==========================================
export interface KeyAttributesTableProps {
  asset1: AssetIntelligence;
  asset2?: AssetIntelligence;
  className?: string;
}

export function KeyAttributesTable({
  asset1,
  asset2,
  className,
}: KeyAttributesTableProps) {
  const attributeKeys = [
    "Selectivity",
    "IC50 (HER2)",
    "Activity in HER2 mutants",
    "CNS penetration (preclinical)",
    "In vivo efficacy (preclinical)",
    "Main differentiation",
    "Current stage",
    "Key indications",
  ];

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm",
        className
      )}
    >
      <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
          Key Attributes Comparison
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500">
              <th className="py-2.5 px-4 w-1/4">Attribute</th>
              <th className="py-2.5 px-4 text-blue-700 font-extrabold w-[37.5%]">
                {asset1.name}
              </th>
              {asset2 && (
                <th className="py-2.5 px-4 text-amber-700 font-extrabold w-[37.5%]">
                  {asset2.name}
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {attributeKeys.map((attr, idx) => {
              const val1 = asset1.key_attributes[attr] || "—";
              const val2 = asset2 ? asset2.key_attributes[attr] || "—" : null;

              return (
                <tr
                  key={attr}
                  className={cn(
                    "hover:bg-slate-50/60 transition-colors",
                    idx % 2 === 0 ? "bg-white" : "bg-slate-50/30"
                  )}
                >
                  <td className="py-2.5 px-4 font-semibold text-slate-600">
                    {attr}
                  </td>
                  <td className="py-2.5 px-4 text-slate-900 font-medium">
                    {val1}
                  </td>
                  {val2 && (
                    <td className="py-2.5 px-4 text-slate-700">
                      {val2}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ==========================================
// 2. DevelopmentPotentialCard
// ==========================================
export interface DevelopmentPotentialCardProps {
  asset1: AssetIntelligence;
  asset2?: AssetIntelligence;
  className?: string;
}

export function DevelopmentPotentialCard({
  asset1,
  asset2,
  className,
}: DevelopmentPotentialCardProps) {
  const stages = [
    { key: "preclinical_to_ind" as const, label: "Preclinical → IND" },
    { key: "phase_i_to_ii" as const, label: "Phase I → II" },
    { key: "phase_ii_to_iii" as const, label: "Phase II → III" },
    { key: "phase_iii_to_approval" as const, label: "Phase III → Approval" },
  ];

  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-5",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Development Potential & Bayesian Transitions
          </h3>
          <p className="text-[11px] text-slate-500">
            Preclinical → Regulatory Approval probability model
          </p>
        </div>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-mono text-slate-600">
          Model v0.1
        </span>
      </div>

      {/* Gauges Side by Side */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
        <ScoreGauge
          score={asset1.recommendation.development_potential_score}
          name={asset1.name}
          tier={asset1.recommendation.development_potential_tier}
          colorTheme="emerald"
        />

        {asset2 && (
          <ScoreGauge
            score={asset2.recommendation.development_potential_score}
            name={asset2.name}
            tier={asset2.recommendation.development_potential_tier}
            colorTheme="amber"
          />
        )}
      </div>

      {/* Bayesian Stage Transition Bars */}
      <div className="border-t border-slate-100 pt-4 space-y-2.5">
        <div className="flex items-center justify-between text-[11px] font-bold text-slate-500 uppercase tracking-wider">
          <span>Stage Transition</span>
          <div className="flex items-center gap-4">
            <span className="text-blue-700">{asset1.name}</span>
            {asset2 && <span className="text-amber-700">{asset2.name}</span>}
          </div>
        </div>

        {stages.map((st) => {
          const val1 = Math.round((asset1.stage_transitions[st.key] || 0) * 100);
          const val2 = asset2 ? Math.round((asset2.stage_transitions[st.key] || 0) * 100) : null;

          return (
            <div key={st.key} className="space-y-1 text-xs">
              <div className="flex justify-between text-slate-700 font-semibold text-[11px]">
                <span>{st.label}</span>
                <div className="flex gap-4 font-mono font-bold">
                  <span className="text-blue-700">{val1}%</span>
                  {val2 !== null && <span className="text-amber-700">{val2}%</span>}
                </div>
              </div>

              {/* Stacked or parallel bars */}
              <div className="space-y-1">
                <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                    style={{ width: `${val1}%` }}
                  />
                </div>
                {val2 !== null && (
                  <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-amber-500 transition-all duration-500"
                      style={{ width: `${val2}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}

        <p className="pt-2 text-[10px] text-slate-400 italic">
          {asset1.stage_transitions.calibration_note ||
            "Predictions calibrated on historical benchmark trials and validated pharmacology."}
        </p>
      </div>
    </div>
  );
}

// ==========================================
// 3. BiologyProfileCard
// ==========================================
export interface BiologyProfileCardProps {
  asset1: AssetIntelligence;
  asset2?: AssetIntelligence;
  className?: string;
}

export function BiologyProfileCard({
  asset1,
  asset2,
  className,
}: BiologyProfileCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Biology Profile (Multi-Dimensional)
          </h3>
          <p className="text-[11px] text-slate-500">
            Selectivity, potency, CNS penetration & safety index
          </p>
        </div>
      </div>

      <RadarProfile
        asset1Name={asset1.name}
        asset1Metrics={asset1.biology_profile}
        asset2Name={asset2?.name}
        asset2Metrics={asset2?.biology_profile}
        size={270}
      />
    </div>
  );
}

// ==========================================
// 4. PatientMatchCard
// ==========================================
export interface PatientMatchCardProps {
  profile1: PatientMatchProfile;
  name1: string;
  profile2?: PatientMatchProfile;
  name2?: string;
  className?: string;
}

export function PatientMatchCard({
  profile1,
  name1,
  profile2,
  name2,
  className,
}: PatientMatchCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4",
        className
      )}
    >
      <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
        <span className="text-base">👥</span>
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Patient Match & Biomarker Subpopulations
          </h3>
          <p className="text-[11px] text-slate-500">
            Stratified genomic cohorts most likely to benefit
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs">
        {/* Left Column */}
        <div className="space-y-2.5">
          <div className="font-extrabold text-blue-700 text-sm">{name1}</div>
          <div className="font-bold text-slate-700 text-[11px] uppercase tracking-wider">
            Best Patient Population
          </div>
          <ul className="space-y-1.5 text-slate-700">
            {profile1.best_patient_population.map((pop, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-emerald-600 font-bold">✓</span>
                <span>{pop}</span>
              </li>
            ))}
            {profile1.cns_metastases_benefit && (
              <li className="flex items-start gap-2 text-purple-700 font-semibold">
                <span className="text-purple-600 font-bold">✓</span>
                <span>Active CNS / brain metastases benefit demonstrated</span>
              </li>
            )}
          </ul>
          <div className="pt-2 text-[11px] text-slate-500">
            <strong>Key Biomarkers:</strong> {profile1.biomarkers.join(", ")}
          </div>
        </div>

        {/* Right Column */}
        {profile2 && name2 && (
          <div className="space-y-2.5 border-t md:border-t-0 md:border-l border-slate-100 md:pl-5 pt-3 md:pt-0">
            <div className="font-extrabold text-amber-700 text-sm">{name2}</div>
            <div className="font-bold text-slate-700 text-[11px] uppercase tracking-wider">
              Best Patient Population
            </div>
            <ul className="space-y-1.5 text-slate-700">
              {profile2.best_patient_population.map((pop, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-amber-600 font-bold">✓</span>
                  <span>{pop}</span>
                </li>
              ))}
              {profile2.cns_metastases_benefit && (
                <li className="flex items-start gap-2 text-purple-700 font-semibold">
                  <span className="text-purple-600 font-bold">✓</span>
                  <span>Active CNS / brain metastases benefit demonstrated</span>
                </li>
              )}
            </ul>
            <div className="pt-2 text-[11px] text-slate-500">
              <strong>Key Biomarkers:</strong> {profile2.biomarkers.join(", ")}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ==========================================
// 5. SafetyProfileCard
// ==========================================
export interface SafetyProfileCardProps {
  safety1: SafetyToxicityProfile;
  name1: string;
  safety2?: SafetyToxicityProfile;
  name2?: string;
  className?: string;
}

export function SafetyProfileCard({
  safety1,
  name1,
  safety2,
  name2,
  className,
}: SafetyProfileCardProps) {
  const rows = [
    { label: "Common AEs", val1: safety1.common_aes, val2: safety2?.common_aes },
    { label: "Dose-Limiting Toxicities", val1: safety1.dose_limiting_toxicities, val2: safety2?.dose_limiting_toxicities },
    { label: "Therapeutic Index", val1: safety1.therapeutic_index, val2: safety2?.therapeutic_index },
    { label: "GI Toxicity Grade", val1: safety1.gi_toxicity_grade, val2: safety2?.gi_toxicity_grade },
    { label: "Discontinuation Rate", val1: safety1.discontinuation_rate, val2: safety2?.discontinuation_rate },
  ];

  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4",
        className
      )}
    >
      <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
        <span className="text-base">🛡️</span>
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Safety & Toxicity Profile
          </h3>
          <p className="text-[11px] text-slate-500">
            Adverse event rates, therapeutic index & GI tolerability
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase text-slate-500">
              <th className="py-2 px-3 w-1/3">Parameter</th>
              <th className="py-2 px-3 text-blue-700 font-bold">{name1}</th>
              {safety2 && name2 && (
                <th className="py-2 px-3 text-amber-700 font-bold">{name2}</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, idx) => (
              <tr key={r.label} className={idx % 2 === 0 ? "bg-white" : "bg-slate-50/40"}>
                <td className="py-2.5 px-3 font-semibold text-slate-600">{r.label}</td>
                <td className="py-2.5 px-3 font-medium text-slate-900">{r.val1}</td>
                {r.val2 && <td className="py-2.5 px-3 text-slate-700">{r.val2}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ==========================================
// 6. ResistanceCard
// ==========================================
export interface ResistanceCardProps {
  mechanisms: ResistanceMechanism[];
  assetName: string;
  className?: string;
}

export function ResistanceCard({
  mechanisms,
  assetName,
  className,
}: ResistanceCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Predicted Resistance Mechanisms
          </h3>
          <p className="text-[11px] text-slate-500">{assetName}</p>
        </div>
        <span className="rounded bg-rose-50 px-2 py-0.5 text-[10px] font-bold text-rose-800 border border-rose-200">
          Escape Pathways
        </span>
      </div>

      <div className="space-y-2">
        {mechanisms.map((m) => (
          <div
            key={m.name}
            className="rounded-lg border border-slate-200 bg-slate-50/50 p-2.5 text-xs hover:border-slate-300 transition"
          >
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-900">{m.name}</span>
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-bold",
                  m.impact === "High"
                    ? "bg-rose-100 text-rose-800"
                    : m.impact === "Moderate"
                    ? "bg-amber-100 text-amber-800"
                    : "bg-slate-100 text-slate-700"
                )}
              >
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full",
                    m.impact === "High" ? "bg-rose-600" : "bg-amber-600"
                  )}
                />
                {m.impact} Impact
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-600 leading-relaxed font-normal">
              {m.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==========================================
// 7. CombinationCard
// ==========================================
export interface CombinationCardProps {
  combinations: RecommendedCombination[];
  assetName: string;
  className?: string;
}

export function CombinationCard({
  combinations,
  assetName,
  className,
}: CombinationCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Recommended Combinations
          </h3>
          <p className="text-[11px] text-slate-500">{assetName}</p>
        </div>
        <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-800 border border-emerald-200">
          Synergy Strategies
        </span>
      </div>

      <div className="space-y-2">
        {combinations.map((c) => (
          <div
            key={c.partner_name}
            className="rounded-lg border border-slate-200 bg-emerald-50/20 p-2.5 text-xs hover:border-emerald-300 transition"
          >
            <div className="flex items-center justify-between">
              <span className="font-bold text-emerald-950 flex items-center gap-1.5">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-600 text-white text-[9px] font-bold">
                  +
                </span>
                {c.partner_name}
              </span>
              <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[9px] font-bold text-emerald-800">
                {c.synergy_type}
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-600 leading-relaxed">
              {c.rationale}
            </p>
            <div className="mt-1.5 text-[10px] font-semibold text-slate-500 italic">
              Status: {c.clinical_status}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Canonical Aliases matching Design System requirements
export const DevelopmentPotential = DevelopmentPotentialCard;
export type DevelopmentPotentialProps = DevelopmentPotentialCardProps;

export const BiologyProfile = BiologyProfileCard;
export type BiologyProfileProps = BiologyProfileCardProps;

export const PatientMatch = PatientMatchCard;
export type PatientMatchProps = PatientMatchCardProps;

export const SafetyProfile = SafetyProfileCard;
export type SafetyProfileProps = SafetyProfileCardProps;

export const ResistanceProfile = ResistanceCard;
export type ResistanceProfileProps = ResistanceCardProps;
export const ResistanceProfileCard = ResistanceCard;

