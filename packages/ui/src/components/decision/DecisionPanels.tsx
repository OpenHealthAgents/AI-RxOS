"use client";

import React, { useState } from "react";
import { cn } from "../../lib/utils";
import {
  AssetIntelligence,
  DecisionRecommendation,
  HistoricalBacktestResult,
  ScientificMilestone,
  StrategicAction,
} from "@ai-rxos/types";
import { DecisionBadge, DecisionBanner, EvidenceBadge } from "./BadgesAndBanners";
import { ScoreGauge } from "./ScoringComponents";

// ==========================================
// 1. RecommendationPanel
// ==========================================
export interface RecommendationPanelProps {
  recommendation: DecisionRecommendation;
  assetName: string;
  supportingDrivers: string[];
  contraindications?: string[];
  onOpenEvidenceModal?: () => void;
  onOpenSignOffModal?: () => void;
  className?: string;
}

export function RecommendationPanel({
  recommendation,
  assetName,
  supportingDrivers,
  contraindications = [],
  onOpenEvidenceModal,
  onOpenSignOffModal,
  className,
}: RecommendationPanelProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Strategic Decision Recommendation
          </span>
          <h3 className="text-base font-bold text-slate-900 mt-0.5">
            {assetName} — Decision Intelligence Dossier
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <DecisionBadge action={recommendation.action} size="lg" />
        </div>
      </div>

      <DecisionBanner
        action={recommendation.action}
        title={`Recommended Action: ${recommendation.action}`}
        rationale={recommendation.rationale}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs pt-1">
        {/* Supporting Drivers */}
        <div className="rounded-lg border border-emerald-100 bg-emerald-50/20 p-3.5 space-y-2">
          <h4 className="font-bold text-emerald-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-600" />
            Key Supporting Analytical Drivers
          </h4>
          <ul className="space-y-1.5 text-slate-700">
            {supportingDrivers.map((driver, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="text-emerald-600 font-bold">✓</span>
                <span>{driver}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Caveats / Contraindications */}
        <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-3.5 space-y-2">
          <h4 className="font-bold text-slate-800 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            Critical Caveats & Safety Boundaries
          </h4>
          {contraindications.length > 0 ? (
            <ul className="space-y-1.5 text-slate-700">
              {contraindications.map((caveat, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-amber-600 font-bold">⚠️</span>
                  <span>{caveat}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-slate-500 text-[11px] italic">
              No critical toxicological contraindications or dose-limiting barriers reported.
            </p>
          )}
        </div>
      </div>

      {/* Action Footer */}
      <div className="flex flex-wrap items-center justify-between border-t border-slate-100 pt-3 gap-3">
        <div className="text-[11px] text-slate-500">
          Model Lineage: <strong>{recommendation.model_lineage || "Calibrated Multi-Attribute Engine"}</strong> (DPS: {recommendation.development_potential_score}%, {recommendation.confidence}% confidence)
        </div>

        <div className="flex items-center gap-2">
          {onOpenEvidenceModal && (
            <button
              onClick={onOpenEvidenceModal}
              className="rounded border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
            >
              Inspect Evidence Trail
            </button>
          )}
          {onOpenSignOffModal && (
            <button
              onClick={onOpenSignOffModal}
              className="rounded bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 shadow-sm transition"
            >
              Sign Off / Ratify
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ==========================================
// 2. WhyPanel (Analytical Factor Attribution Waterfall)
// ==========================================
export interface FactorAttributionItem {
  name: string;
  impactPts: number; // positive or negative
  category: "biology" | "cns" | "patient" | "safety" | "stage" | "commercial";
  rationale: string;
}

export interface WhyPanelProps {
  assetName: string;
  factors: FactorAttributionItem[];
  finalScore: number;
  className?: string;
}

export function WhyPanel({
  assetName,
  factors,
  finalScore,
  className,
}: WhyPanelProps) {
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
            Why This Recommendation? (Factor Attribution)
          </h3>
          <p className="text-[11px] text-slate-500">
            Decomposed scoring contributors for {assetName}
          </p>
        </div>
        <div className="text-right">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Net Score
          </span>
          <div className="text-xl font-black text-blue-700">{finalScore}%</div>
        </div>
      </div>

      <div className="space-y-2.5">
        {factors.map((f, i) => {
          const isPositive = f.impactPts >= 0;

          return (
            <div
              key={i}
              className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50/50 p-2.5 text-xs transition hover:bg-white hover:border-slate-300"
            >
              <div className="flex-1 pr-4">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-slate-900">{f.name}</span>
                  <span className="rounded bg-slate-200 px-1.5 py-0.2 text-[9px] font-semibold text-slate-700 uppercase">
                    {f.category}
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-slate-600 leading-snug">{f.rationale}</p>
              </div>

              <div
                className={cn(
                  "font-mono font-bold text-sm shrink-0 px-2 py-0.5 rounded",
                  isPositive ? "text-emerald-700 bg-emerald-100/60" : "text-rose-700 bg-rose-100/60"
                )}
              >
                {isPositive ? `+${f.impactPts}` : f.impactPts} pts
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ==========================================
// 3. OpportunityCard
// ==========================================
export interface OpportunityCardProps {
  asset: AssetIntelligence;
  onSelectCompare?: (asset: AssetIntelligence) => void;
  onNavigateEvaluate?: (asset: AssetIntelligence) => void;
  className?: string;
}

export function OpportunityCard({
  asset,
  onSelectCompare,
  onNavigateEvaluate,
  className,
}: OpportunityCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-blue-400 hover:shadow-md transition-all flex flex-col justify-between",
        className
      )}
    >
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-base font-bold text-slate-900">{asset.name}</h4>
              <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-bold text-blue-800">
                {asset.target}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              {asset.owner} • {asset.stage}
            </p>
          </div>

          <DecisionBadge action={asset.recommendation.action} size="sm" />
        </div>

        <div className="mt-3 flex items-center gap-4 border-y border-slate-100 py-3">
          <ScoreGauge
            score={asset.recommendation.development_potential_score}
            name="DPS Score"
            showLegend={false}
          />
          <div className="flex-1 text-xs space-y-1">
            <div className="text-slate-600">
              <strong>Modality:</strong> {asset.modality}
            </div>
            <div className="text-slate-600 truncate">
              <strong>Indication:</strong> {asset.primary_indication}
            </div>
            <div className="text-slate-600 line-clamp-2">
              <strong>Edge:</strong> {asset.key_attributes["Main differentiation"]}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between pt-1">
        <span className="text-[11px] text-slate-400 font-medium">
          Confidence: {asset.recommendation.confidence}%
        </span>

        <div className="flex items-center gap-2">
          {onSelectCompare && (
            <button
              onClick={() => onSelectCompare(asset)}
              className="rounded border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
            >
              Compare
            </button>
          )}
          {onNavigateEvaluate && (
            <button
              onClick={() => onNavigateEvaluate(asset)}
              className="rounded bg-blue-600 px-3 py-1 text-xs font-semibold text-white hover:bg-blue-500 shadow-sm transition"
            >
              Evaluate Dossier →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ==========================================
// 4. AssetComparisonMatrix
// ==========================================
export interface AssetComparisonMatrixProps {
  assets: AssetIntelligence[];
  onSelectAsset?: (asset: AssetIntelligence) => void;
  className?: string;
}

export function AssetComparisonMatrix({
  assets,
  onSelectAsset,
  className,
}: AssetComparisonMatrixProps) {
  const dimensions = [
    { label: "Modality", getter: (a: AssetIntelligence) => a.modality },
    { label: "Target / Gene", getter: (a: AssetIntelligence) => a.target },
    { label: "Clinical Stage", getter: (a: AssetIntelligence) => a.stage },
    { label: "DPS Potential", getter: (a: AssetIntelligence) => `${a.recommendation.development_potential_score}%` },
    { label: "Target Selectivity", getter: (a: AssetIntelligence) => `${a.biology_profile.target_selectivity}/100` },
    { label: "CNS Penetration", getter: (a: AssetIntelligence) => `${a.biology_profile.cns_potential}/100` },
    { label: "Safety Score", getter: (a: AssetIntelligence) => `${a.safety_profile.safety_score}/100` },
    { label: "Common AEs", getter: (a: AssetIntelligence) => a.safety_profile.common_aes },
    { label: "Strategic Action", getter: (a: AssetIntelligence) => a.recommendation.action },
  ];

  return (
    <div className={cn("overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm", className)}>
      <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
          Multidimensional Asset Comparison Matrix ({assets.length} Assets)
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase tracking-wider text-slate-500">
              <th className="py-2.5 px-4 w-44">Scientific Dimension</th>
              {assets.map((asset) => (
                <th key={asset.id} className="py-2.5 px-4 font-bold text-slate-900">
                  <div className="flex items-center gap-1.5">
                    <span>{asset.name}</span>
                    {onSelectAsset && (
                      <button
                        onClick={() => onSelectAsset(asset)}
                        className="text-[10px] text-blue-600 hover:underline font-normal"
                      >
                        (focus)
                      </button>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {dimensions.map((dim, idx) => (
              <tr key={dim.label} className={idx % 2 === 0 ? "bg-white" : "bg-slate-50/30"}>
                <td className="py-2.5 px-4 font-semibold text-slate-600">{dim.label}</td>
                {assets.map((asset) => {
                  const val = dim.getter(asset);
                  const isAction = dim.label === "Strategic Action";

                  return (
                    <td key={asset.id} className="py-2.5 px-4 font-medium">
                      {isAction ? (
                        <DecisionBadge action={val as StrategicAction} size="sm" />
                      ) : (
                        <span>{val}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ==========================================
// 5. FilterPanel
// ==========================================
export interface FilterPanelProps {
  selectedTarget: string;
  onSelectTarget: (t: string) => void;
  selectedAction: string;
  onSelectAction: (a: string) => void;
  cnsRequired: boolean;
  onToggleCns: (req: boolean) => void;
  className?: string;
}

export function FilterPanel({
  selectedTarget,
  onSelectTarget,
  selectedAction,
  onSelectAction,
  cnsRequired,
  onToggleCns,
  className,
}: FilterPanelProps) {
  const targets = ["ALL", "HER2", "EGFR", "KRAS", "pan-HER"];
  const actions: (StrategicAction | "ALL")[] = [
    "ALL",
    "PURSUE",
    "INVESTIGATE",
    "PARTNER",
    "LICENSE",
    "MONITOR",
    "AVOID",
  ];

  return (
    <div className={cn("rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-4", className)}>
      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
        Scientific Filter Matrix
      </h4>

      {/* Target Class */}
      <div>
        <label className="block text-[11px] font-semibold text-slate-600 mb-1.5">
          Biological Target Class
        </label>
        <div className="flex flex-wrap gap-1.5">
          {targets.map((t) => (
            <button
              key={t}
              onClick={() => onSelectTarget(t)}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-semibold transition",
                selectedTarget === t
                  ? "bg-blue-600 text-white shadow-xs"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* Strategic Recommendation */}
      <div>
        <label className="block text-[11px] font-semibold text-slate-600 mb-1.5">
          Recommendation Triage
        </label>
        <div className="flex flex-wrap gap-1.5">
          {actions.map((act) => (
            <button
              key={act}
              onClick={() => onSelectAction(act)}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-semibold transition",
                selectedAction === act
                  ? "bg-slate-800 text-white shadow-xs"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              )}
            >
              {act}
            </button>
          ))}
        </div>
      </div>

      {/* CNS Brain Penetration Toggle */}
      <div className="border-t border-slate-100 pt-3">
        <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-700">
          <input
            type="checkbox"
            checked={cnsRequired}
            onChange={(e) => onToggleCns(e.target.checked)}
            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
          />
          <span>Filter: Active CNS / Brain Penetration Required</span>
        </label>
      </div>
    </div>
  );
}

// ==========================================
// 6. SearchResultCard
// ==========================================
export interface SearchResultCardProps {
  title: string;
  canonicalId: string;
  target: string;
  company: string;
  stage: string;
  matchScore: number;
  onSelect: () => void;
  className?: string;
}

export function SearchResultCard({
  title,
  canonicalId,
  target,
  company,
  stage,
  matchScore,
  onSelect,
  className,
}: SearchResultCardProps) {
  return (
    <div
      onClick={onSelect}
      className={cn(
        "rounded-lg border border-slate-200 bg-white p-3 shadow-xs hover:border-blue-400 hover:bg-blue-50/20 cursor-pointer transition flex items-center justify-between gap-4",
        className
      )}
    >
      <div>
        <div className="flex items-center gap-2">
          <h4 className="text-xs font-bold text-slate-900">{title}</h4>
          <span className="font-mono text-[10px] text-slate-400">({canonicalId})</span>
          <span className="rounded bg-blue-100 px-1.5 py-0.2 text-[9px] font-bold text-blue-800">
            {target}
          </span>
        </div>
        <p className="text-[11px] text-slate-500 mt-0.5">
          Owner: {company} • Stage: {stage}
        </p>
      </div>

      <div className="text-right shrink-0">
        <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
          {matchScore}% match
        </span>
      </div>
    </div>
  );
}

// ==========================================
// 7. Timeline (Clinical Milestones)
// ==========================================
export interface TimelineProps {
  milestones: ScientificMilestone[];
  className?: string;
}

export function Timeline({ milestones, className }: TimelineProps) {
  return (
    <div className={cn("relative border-l-2 border-slate-200 pl-4 space-y-4 my-2", className)}>
      {milestones.map((m) => (
        <div key={m.id} className="relative group">
          <span
            className={cn(
              "absolute -left-[21px] top-1 h-3 w-3 rounded-full border-2 border-white",
              m.status === "completed"
                ? "bg-blue-600"
                : m.status === "in_progress"
                ? "bg-amber-500 animate-pulse"
                : "bg-slate-300"
            )}
          />
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono font-bold text-slate-500">{m.date}</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.2 text-[9px] font-semibold text-slate-600 uppercase">
              {m.category}
            </span>
          </div>
          <h5 className="text-xs font-bold text-slate-900 mt-0.5">{m.title}</h5>
          {m.description && <p className="text-xs text-slate-600 mt-0.5">{m.description}</p>}
        </div>
      ))}
    </div>
  );
}

// ==========================================
// 8. BacktestTimeline
// ==========================================
export interface BacktestTimelineProps {
  result: HistoricalBacktestResult;
  className?: string;
}

export function BacktestTimeline({ result, className }: BacktestTimelineProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3.5",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Zero-Leakage Retrospective Simulation
          </span>
          <h4 className="text-sm font-bold text-slate-900 mt-0.5">
            {result.asset_name} • Cutoff Date: {result.cutoff_date}
          </h4>
        </div>

        <span
          className={cn(
            "rounded px-2 py-0.5 text-xs font-bold",
            result.anti_leakage_audit_passed
              ? "bg-emerald-100 text-emerald-800"
              : "bg-rose-100 text-rose-800"
          )}
        >
          {result.anti_leakage_audit_passed ? "✓ Zero Leakage Audit Passed" : "Leakage Flagged"}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
        <div className="rounded border border-slate-200 p-2.5 bg-slate-50">
          <span className="text-slate-500 font-semibold text-[10px] uppercase">
            Eligible Pre-Cutoff Evidence
          </span>
          <div className="text-lg font-bold text-blue-700 mt-0.5">
            {result.evidence_items_eligible} items
          </div>
        </div>

        <div className="rounded border border-slate-200 p-2.5 bg-slate-50">
          <span className="text-slate-500 font-semibold text-[10px] uppercase">
            Suppressed Future Evidence
          </span>
          <div className="text-lg font-bold text-slate-700 mt-0.5">
            {result.evidence_items_suppressed_future} items
          </div>
        </div>

        <div className="rounded border border-slate-200 p-2.5 bg-slate-50">
          <span className="text-slate-500 font-semibold text-[10px] uppercase">
            Predicted Action at Cutoff
          </span>
          <div className="mt-1">
            <DecisionBadge action={result.predicted_action_at_cutoff} size="sm" />
          </div>
        </div>

        <div className="rounded border border-slate-200 p-2.5 bg-slate-50">
          <span className="text-slate-500 font-semibold text-[10px] uppercase">
            Accuracy Classification
          </span>
          <div className="text-xs font-bold text-emerald-700 mt-1">
            {result.prediction_accuracy}
          </div>
        </div>
      </div>

      <div className="rounded bg-slate-50 p-3 border border-slate-100 text-xs text-slate-700 leading-relaxed">
        <strong>Ground Truth Eventual Outcome:</strong> {result.ground_truth_eventual_outcome}
        <div className="mt-1 text-slate-600">
          <strong>Historical Rationale:</strong> {result.historical_recommendation_rationale}
        </div>
      </div>
    </div>
  );
}
