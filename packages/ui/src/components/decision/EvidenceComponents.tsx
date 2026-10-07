"use client";

import React, { useState } from "react";
import { cn } from "../../lib/utils";
import {
  EvidenceItem,
  UnknownFactor,
  ContradictionRecord,
  ContradictoryClaim,
} from "@ai-rxos/types";
import { EvidenceBadge, SourceCitation } from "./BadgesAndBanners";

// ==========================================
// 1. EvidenceCard
// ==========================================
export interface EvidenceCardProps {
  item: EvidenceItem;
  className?: string;
}

export function EvidenceCard({ item, className }: EvidenceCardProps) {
  const isSupporting = item.polarity === "SUPPORTING";

  return (
    <div
      className={cn(
        "rounded-lg border p-3.5 transition bg-white shadow-xs",
        isSupporting ? "border-slate-200 hover:border-blue-300" : "border-rose-200 bg-rose-50/20 hover:border-rose-300",
        className
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <SourceCitation
            citation={item.citation}
            sourceRef={item.source_ref}
            year={item.publication_year}
            url={item.url}
          />

          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600 uppercase">
            {item.source_type.replace("_", " ")}
          </span>

          <EvidenceBadge
            state={isSupporting ? "positive" : "negative"}
            customText={item.polarity}
          />

          {item.is_verified ? (
            <EvidenceBadge state="verified_fact" customText="Verified" />
          ) : (
            <EvidenceBadge state="ai_inference" customText="Unverified / Draft" />
          )}
        </div>

        <span className="text-[10px] font-mono text-slate-400 shrink-0">
          as-of {item.as_of_date}
        </span>
      </div>

      <h5 className="text-xs font-bold text-slate-900 mt-2 leading-snug">
        {item.title}
      </h5>

      <p className="mt-1.5 rounded bg-slate-50 p-2 text-xs text-slate-700 italic border border-slate-100 leading-relaxed font-normal">
        "{item.excerpt}"
      </p>

      <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between">
        <span>Citation: {item.citation}</span>
        {item.url && (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 font-semibold hover:underline"
          >
            Open Source Record →
          </a>
        )}
      </div>
    </div>
  );
}

// ==========================================
// 2. ContradictionCard & ContradictoryEvidence
// ==========================================
export interface ContradictionCardProps {
  record: ContradictionRecord;
  className?: string;
}

export function ContradictionCard({ record, className }: ContradictionCardProps) {
  const formatPolarity = (polarity: string) => {
    switch (polarity.toUpperCase()) {
      case "SUPPORTING":
        return { label: "SUPPORTING", color: "bg-emerald-100 text-emerald-800 border-emerald-300" };
      case "CONTRADICTORY":
      case "CONTRADICTING":
        return { label: "CONTRADICTORY", color: "bg-rose-100 text-rose-800 border-rose-300" };
      case "NEUTRAL":
        return { label: "NEUTRAL", color: "bg-slate-100 text-slate-700 border-slate-300" };
      case "UNKNOWN":
      default:
        return { label: "UNKNOWN", color: "bg-amber-100 text-amber-800 border-amber-300" };
    }
  };

  const polA = formatPolarity(record.claim_a.polarity);
  const polB = formatPolarity(record.claim_b.polarity);

  return (
    <div
      className={cn(
        "rounded-xl border border-rose-200 bg-white p-4 shadow-xs transition hover:shadow-sm space-y-3.5",
        className
      )}
    >
      {/* Header Topic & Deltas */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-rose-100 pb-2.5">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-rose-600 text-[10px] text-white font-bold">
            ⚡
          </span>
          <div>
            <h4 className="text-xs font-bold text-slate-900 leading-tight">
              {record.topic}
            </h4>
            <span className="text-[10px] text-slate-500 font-mono">
              Param: {record.parameter_name} • {record.category.replace(/_/g, " ")}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="rounded bg-rose-50 border border-rose-200 px-2 py-0.5 text-[10px] font-semibold text-rose-700">
            Δ Quality: {record.quality_delta} pts
          </span>
          <span className="rounded bg-slate-100 border border-slate-200 px-2 py-0.5 text-[10px] font-semibold text-slate-700 font-mono">
            Δ Conf: {record.confidence_delta}
          </span>
          <span className="rounded bg-purple-50 border border-purple-200 px-2 py-0.5 text-[10px] font-bold text-purple-700 uppercase">
            {record.status.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {/* Side-by-Side Claims Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {/* Claim A */}
        <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Claim A
            </span>
            <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-bold border", polA.color)}>
              {polA.label}
            </span>
          </div>

          <p className="text-xs font-medium text-slate-800 leading-relaxed">
            "{record.claim_a.claim_text}"
          </p>

          <div className="space-y-1 text-[10px] text-slate-600 border-t border-slate-200 pt-2 font-sans">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">Source:</span>
              <span className="font-mono text-blue-700 font-bold truncate max-w-[180px]">
                {record.claim_a.source.source_id} ({record.claim_a.date})
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">Design:</span>
              <span className="capitalize">{record.claim_a.study_design.replace(/_/g, " ")}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">Quality / Confidence:</span>
              <span>
                {record.claim_a.quality.quality_score}/100 • {(record.claim_a.confidence.score * 100).toFixed(0)}%
              </span>
            </div>
            {record.claim_a.numeric_measurement && (
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-700">Observed:</span>
                <span className="font-mono font-bold text-slate-800">{record.claim_a.numeric_measurement}</span>
              </div>
            )}
          </div>
        </div>

        {/* Claim B */}
        <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Claim B
            </span>
            <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-bold border", polB.color)}>
              {polB.label}
            </span>
          </div>

          <p className="text-xs font-medium text-slate-800 leading-relaxed">
            "{record.claim_b.claim_text}"
          </p>

          <div className="space-y-1 text-[10px] text-slate-600 border-t border-slate-200 pt-2 font-sans">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">Source:</span>
              <span className="font-mono text-blue-700 font-bold truncate max-w-[180px]">
                {record.claim_b.source.source_id} ({record.claim_b.date})
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">Design:</span>
              <span className="capitalize">{record.claim_b.study_design.replace(/_/g, " ")}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-700">Quality / Confidence:</span>
              <span>
                {record.claim_b.quality.quality_score}/100 • {(record.claim_b.confidence.score * 100).toFixed(0)}%
              </span>
            </div>
            {record.claim_b.numeric_measurement && (
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-700">Observed:</span>
                <span className="font-mono font-bold text-slate-800">{record.claim_b.numeric_measurement}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Possible Explanation */}
      <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-2.5 text-xs text-amber-900 leading-relaxed">
        <span className="font-bold text-amber-800 flex items-center gap-1 mb-0.5">
          💡 Possible Methodological / Biological Explanation:
        </span>
        <p className="text-[11px] font-medium text-amber-950">
          {record.possible_explanation}
        </p>
      </div>

      {/* Epistemic Guardrail Notice & Recommendation */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 rounded-lg bg-slate-100 p-2 text-[10px] text-slate-600">
        <span className="font-medium">
          🛡️ <span className="font-semibold text-slate-800">Zero Silent Selection:</span> Neither claim suppressed. {record.resolution_recommendation}
        </span>
      </div>
    </div>
  );
}

export interface ContradictoryEvidenceProps {
  items?: EvidenceItem[];
  records?: ContradictionRecord[];
  title?: string;
  className?: string;
}

export function ContradictoryEvidence({
  items = [],
  records = [],
  title = "Contradictory Evidence & Epistemic Disagreements",
  className,
}: ContradictoryEvidenceProps) {
  const hasRecords = records && records.length > 0;
  const hasItems = items && items.length > 0;

  if (!hasRecords && !hasItems) {
    return (
      <div className={cn("rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500", className)}>
        <span className="font-semibold text-slate-700">No Contradicting Signals:</span> No active scientific disputes or contradicting findings recorded for this asset.
      </div>
    );
  }

  const count = (records?.length || 0) + (items?.length || 0);

  return (
    <div className={cn("rounded-xl border border-rose-300 bg-rose-50/30 p-4 shadow-sm space-y-3.5", className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-rose-600 text-[10px] text-white font-bold">
            ⚠️
          </span>
          <h4 className="text-xs font-bold uppercase tracking-wider text-rose-900">
            {title} ({count})
          </h4>
        </div>
        <span className="rounded bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-800 uppercase tracking-wider">
          Epistemic Integrity Active
        </span>
      </div>

      <p className="text-xs text-rose-800 font-medium">
        If two credible sources disagree, AI-RxOS never silently selects one. Both Claim A and Claim B are preserved
        with study designs, quality scores, confidence levels, and mechanistic explanations.
      </p>

      {/* Render Contradiction Records if present */}
      {hasRecords && (
        <div className="space-y-3">
          {records.map((rec) => (
            <ContradictionCard key={rec.id} record={rec} />
          ))}
        </div>
      )}

      {/* Render Legacy items if present */}
      {hasItems && (
        <div className="space-y-2.5">
          {items.map((item) => (
            <EvidenceCard key={item.id} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

// ==========================================
// 3. UnknownEvidence
// ==========================================
export interface UnknownEvidenceProps {
  unknowns: UnknownFactor[];
  title?: string;
  className?: string;
}

export function UnknownEvidence({
  unknowns,
  title = "Explicit Knowledge Gaps & Translational Unknowns",
  className,
}: UnknownEvidenceProps) {
  if (!unknowns || unknowns.length === 0) {
    return (
      <div className={cn("rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500", className)}>
        No critical unknown flags currently pending for this asset.
      </div>
    );
  }

  return (
    <div className={cn("rounded-lg border border-purple-200 bg-purple-50/30 p-4 shadow-sm", className)}>
      <div className="flex items-center gap-2 mb-2">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-purple-600 text-[10px] text-white font-bold">
          ?
        </span>
        <h4 className="text-xs font-bold uppercase tracking-wider text-purple-900">
          {title} ({unknowns.length})
        </h4>
      </div>
      <p className="text-xs text-purple-800 mb-3 font-medium">
        Identified scientific unknowns requiring translational de-risking or dedicated confirmatory trials.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {unknowns.map((u) => (
          <div key={u.id} className="rounded-lg border border-purple-200 bg-white p-3.5 shadow-2xs">
            <div className="flex items-center justify-between mb-1.5">
              <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-bold text-purple-800">
                {u.category}
              </span>
              <EvidenceBadge state="unknown" customText="Gap Identified" />
            </div>

            <h5 className="text-xs font-bold text-slate-900 mb-1">
              {u.question}
            </h5>

            <div className="text-[11px] text-slate-600 mb-2">
              <span className="font-semibold text-slate-700">Current Evidence Gap:</span> {u.current_gap}
            </div>

            <div className="rounded bg-slate-50 p-2 text-[11px] text-slate-700 border border-slate-100">
              <span className="font-bold text-blue-700">Suggested Study / Assay:</span> {u.suggested_study}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ==========================================
// 4. EvidenceTimeline
// ==========================================
export interface EvidenceTimelineEvent {
  id: string;
  date: string;
  title: string;
  sourceRef: string;
  polarity: "SUPPORTING" | "CONTRADICTING";
  description: string;
}

export interface EvidenceTimelineProps {
  events: EvidenceTimelineEvent[];
  className?: string;
}

export function EvidenceTimeline({ events, className }: EvidenceTimelineProps) {
  return (
    <div className={cn("relative border-l-2 border-slate-200 pl-4 space-y-4 my-2", className)}>
      {events.map((ev) => {
        const isSupporting = ev.polarity === "SUPPORTING";
        return (
          <div key={ev.id} className="relative group">
            <span
              className={cn(
                "absolute -left-[21px] top-1 h-3 w-3 rounded-full border-2 border-white",
                isSupporting ? "bg-emerald-600" : "bg-rose-600"
              )}
            />
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono font-bold text-slate-500">{ev.date}</span>
              <span className="font-mono text-xs font-bold text-blue-700">{ev.sourceRef}</span>
              <EvidenceBadge state={isSupporting ? "positive" : "negative"} customText={ev.polarity} />
            </div>
            <h5 className="text-xs font-bold text-slate-900 mt-0.5">{ev.title}</h5>
            <p className="text-xs text-slate-600 mt-0.5">{ev.description}</p>
          </div>
        );
      })}
    </div>
  );
}

// ==========================================
// 5. EvidenceDrawer
// ==========================================
export interface EvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  supportingEvidence: EvidenceItem[];
  contradictingEvidence: EvidenceItem[];
  unknowns?: UnknownFactor[];
  className?: string;
}

export function EvidenceDrawer({
  isOpen,
  onClose,
  title,
  supportingEvidence,
  contradictingEvidence,
  unknowns = [],
  className,
}: EvidenceDrawerProps) {
  const [filterPolarity, setFilterPolarity] = useState<"ALL" | "SUPPORTING" | "CONTRADICTING">("ALL");

  if (!isOpen) return null;

  const totalCount = supportingEvidence.length + contradictingEvidence.length;
  const filteredList =
    filterPolarity === "SUPPORTING"
      ? supportingEvidence
      : filterPolarity === "CONTRADICTING"
      ? contradictingEvidence
      : [...supportingEvidence, ...contradictingEvidence];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-end bg-slate-900/60 backdrop-blur-sm p-0">
      <div
        className={cn(
          "flex h-full w-full max-w-2xl flex-col bg-white shadow-2xl border-l border-slate-200 overflow-hidden",
          className
        )}
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-900 px-6 py-4 text-white">
          <div>
            <h3 className="text-base font-bold tracking-tight text-white">{title}</h3>
            <p className="text-xs text-slate-400">
              {totalCount} Verified Provenance Records • Zero Leakage Audit Guarantee
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition"
          >
            ✕
          </button>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-6 py-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
            Filter:
          </span>
          <button
            onClick={() => setFilterPolarity("ALL")}
            className={cn(
              "rounded px-2.5 py-1 text-xs font-semibold transition",
              filterPolarity === "ALL" ? "bg-slate-800 text-white" : "bg-white text-slate-600 border border-slate-200"
            )}
          >
            All ({totalCount})
          </button>
          <button
            onClick={() => setFilterPolarity("SUPPORTING")}
            className={cn(
              "rounded px-2.5 py-1 text-xs font-semibold transition",
              filterPolarity === "SUPPORTING" ? "bg-emerald-600 text-white" : "bg-white text-emerald-800 border border-emerald-200"
            )}
          >
            Supporting ({supportingEvidence.length})
          </button>
          <button
            onClick={() => setFilterPolarity("CONTRADICTING")}
            className={cn(
              "rounded px-2.5 py-1 text-xs font-semibold transition",
              filterPolarity === "CONTRADICTING" ? "bg-rose-600 text-white" : "bg-white text-rose-800 border border-rose-200"
            )}
          >
            Contradicting ({contradictingEvidence.length})
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {unknowns.length > 0 && (
            <UnknownEvidence unknowns={unknowns} />
          )}

          {contradictingEvidence.length > 0 && filterPolarity !== "SUPPORTING" && (
            <ContradictoryEvidence items={contradictingEvidence} />
          )}

          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">
              Provenance Citation Registry ({filteredList.length})
            </h4>
            <div className="space-y-2.5">
              {filteredList.map((item) => (
                <EvidenceCard key={item.id} item={item} />
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-3">
          <span className="text-xs text-slate-500">
            Export format: BibTeX, CSL-JSON, PDF Provenance Dossier
          </span>
          <button
            onClick={onClose}
            className="rounded bg-slate-800 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-700 shadow-sm"
          >
            Close Drawer
          </button>
        </div>
      </div>
    </div>
  );
}
