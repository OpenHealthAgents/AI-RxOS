"use client";

import React from "react";
import { cn } from "../../lib/utils";
import {
  DevelopmentStage,
  ScientificEvidenceState,
  ScientificPriority,
  StrategicAction,
} from "@ai-rxos/types";

// ==========================================
// 1. AssetStatusBadge
// ==========================================
export interface AssetStatusBadgeProps {
  status: "Investigational" | "Approved" | "Preclinical" | "Terminated" | string;
  className?: string;
}

export function AssetStatusBadge({ status, className }: AssetStatusBadgeProps) {
  const getStyles = () => {
    switch (status.toLowerCase()) {
      case "approved":
        return "border-emerald-300 bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200/50";
      case "investigational":
        return "border-blue-300 bg-blue-50 text-blue-800 ring-1 ring-blue-200/50";
      case "preclinical":
        return "border-purple-300 bg-purple-50 text-purple-800 ring-1 ring-purple-200/50";
      case "terminated":
        return "border-rose-300 bg-rose-50 text-rose-800 ring-1 ring-rose-200/50";
      default:
        return "border-slate-300 bg-slate-100 text-slate-800";
    }
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-[11px] font-semibold tracking-wide border transition-colors",
        getStyles(),
        className
      )}
    >
      {status}
    </span>
  );
}

// ==========================================
// 2. DecisionBadge
// ==========================================
export interface DecisionBadgeProps {
  action: StrategicAction;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function DecisionBadge({ action, size = "md", className }: DecisionBadgeProps) {
  const getStyles = () => {
    switch (action) {
      case "PURSUE":
        return "bg-emerald-600 text-white shadow-sm ring-1 ring-emerald-700/30";
      case "INVESTIGATE":
        return "bg-blue-600 text-white shadow-sm ring-1 ring-blue-700/30";
      case "PARTNER":
        return "bg-indigo-600 text-white shadow-sm ring-1 ring-indigo-700/30";
      case "LICENSE":
        return "bg-cyan-600 text-white shadow-sm ring-1 ring-cyan-700/30";
      case "MONITOR":
        return "bg-amber-500 text-white shadow-sm ring-1 ring-amber-600/30";
      case "AVOID":
        return "bg-rose-600 text-white shadow-sm ring-1 ring-rose-700/30";
      default:
        return "bg-slate-700 text-white";
    }
  };

  const getSize = () => {
    switch (size) {
      case "sm":
        return "px-2 py-0.5 text-[10px] font-bold";
      case "lg":
        return "px-4 py-1.5 text-sm font-extrabold tracking-wider";
      case "md":
      default:
        return "px-3 py-1 text-xs font-bold tracking-wide";
    }
  };

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center rounded-md font-sans uppercase",
        getStyles(),
        getSize(),
        className
      )}
    >
      {action}
    </span>
  );
}

// ==========================================
// 3. DecisionBanner
// ==========================================
export interface DecisionBannerProps {
  action: StrategicAction;
  title?: string;
  rationale: string;
  theme?: "green" | "amber" | "blue" | "rose";
  className?: string;
}

export function DecisionBanner({
  action,
  title,
  rationale,
  theme,
  className,
}: DecisionBannerProps) {
  const defaultTheme = () => {
    if (theme) return theme;
    switch (action) {
      case "PURSUE":
        return "green";
      case "MONITOR":
      case "INVESTIGATE":
        return "amber";
      case "AVOID":
        return "rose";
      case "PARTNER":
      case "LICENSE":
      default:
        return "blue";
    }
  };

  const selectedTheme = defaultTheme();

  const getThemeStyles = () => {
    switch (selectedTheme) {
      case "green":
        return {
          container: "bg-[#059669] text-white border-emerald-600 shadow-sm",
          iconBg: "bg-white text-emerald-700",
          icon: (
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
            </svg>
          ),
          defaultTitle: "High-Priority Asset — PURSUE",
        };
      case "amber":
        return {
          container: "bg-[#d97706] text-white border-amber-600 shadow-sm",
          iconBg: "bg-white text-amber-700",
          icon: (
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          ),
          defaultTitle: "Established Asset — NICHE USE",
        };
      case "rose":
        return {
          container: "bg-[#e11d48] text-white border-rose-600 shadow-sm",
          iconBg: "bg-white text-rose-700",
          icon: (
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          ),
          defaultTitle: "High Risk Asset — AVOID",
        };
      case "blue":
      default:
        return {
          container: "bg-[#2563eb] text-white border-blue-600 shadow-sm",
          iconBg: "bg-white text-blue-700",
          icon: (
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ),
          defaultTitle: `Strategic Opportunity — ${action}`,
        };
    }
  };

  const config = getThemeStyles();

  return (
    <div
      className={cn(
        "flex items-center gap-3.5 rounded-lg p-3.5 border transition-all",
        config.container,
        className
      )}
    >
      <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-inner", config.iconBg)}>
        {config.icon}
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="text-sm font-bold tracking-tight text-white leading-tight">
          {title || config.defaultTitle}
        </h4>
        <p className="text-xs text-white/95 font-medium mt-0.5 leading-snug line-clamp-2">
          {rationale}
        </p>
      </div>
    </div>
  );
}

// ==========================================
// 4. PriorityIndicator
// ==========================================
export interface PriorityIndicatorProps {
  priority: ScientificPriority;
  label?: string;
  className?: string;
}

export function PriorityIndicator({ priority, label, className }: PriorityIndicatorProps) {
  const getDotColor = () => {
    switch (priority) {
      case "critical":
        return "bg-rose-600 animate-pulse";
      case "high":
        return "bg-rose-500";
      case "moderate":
        return "bg-amber-500";
      case "low":
        return "bg-emerald-500";
      case "monitoring":
      default:
        return "bg-slate-400";
    }
  };

  const getBadgeStyle = () => {
    switch (priority) {
      case "critical":
        return "text-rose-700 bg-rose-50 border-rose-200";
      case "high":
        return "text-rose-700 bg-rose-50 border-rose-200";
      case "moderate":
        return "text-amber-800 bg-amber-50 border-amber-200";
      case "low":
        return "text-emerald-800 bg-emerald-50 border-emerald-200";
      case "monitoring":
      default:
        return "text-slate-700 bg-slate-50 border-slate-200";
    }
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider",
        getBadgeStyle(),
        className
      )}
    >
      <span className={cn("h-2 w-2 rounded-full shrink-0", getDotColor())} />
      <span>{label || priority}</span>
    </span>
  );
}

// ==========================================
// 5. Visual States & EvidenceBadge
// ==========================================
export type VisualState =
  | "VERIFIED"
  | "INFERRED"
  | "PREDICTED"
  | "HYPOTHESIS"
  | "UNKNOWN"
  | "CONFLICTING"
  | "INSUFFICIENT_EVIDENCE";

export type ScientificEvidenceOrVisualState =
  | VisualState
  | ScientificEvidenceState
  | "verified_fact"
  | "ai_inference"
  | "ml_prediction"
  | "hypothesis"
  | "unknown"
  | "conflicting_evidence"
  | "insufficient_evidence"
  | "positive"
  | "negative"
  | "neutral"
  | string;

export interface VisualStateConfig {
  icon: string;
  label: string;
  classes: string;
}

export function getVisualStateConfig(state: ScientificEvidenceOrVisualState): VisualStateConfig {
  const normalized = String(state).trim().toUpperCase();

  switch (normalized) {
    case "VERIFIED":
    case "VERIFIED_FACT":
      return {
        icon: "★",
        label: "Verified Fact",
        classes: "bg-emerald-50 text-emerald-800 border-emerald-300 ring-1 ring-emerald-200/50 font-bold",
      };
    case "INFERRED":
    case "AI_INFERENCE":
      return {
        icon: "⚡",
        label: "AI Inference",
        classes: "bg-indigo-50 text-indigo-800 border-indigo-300 ring-1 ring-indigo-200/50",
      };
    case "PREDICTED":
    case "ML_PREDICTION":
      return {
        icon: "🔮",
        label: "ML Prediction",
        classes: "bg-purple-50 text-purple-800 border-purple-300 ring-1 ring-purple-200/50 font-semibold",
      };
    case "HYPOTHESIS":
      return {
        icon: "💡",
        label: "Hypothesis",
        classes: "bg-sky-50 text-sky-800 border-sky-300 ring-1 ring-sky-200/50 font-semibold",
      };
    case "UNKNOWN":
      return {
        icon: "?",
        label: "Unknown / Gap",
        classes: "bg-slate-100 text-slate-700 border-slate-300 ring-1 ring-slate-200/50 font-medium",
      };
    case "CONFLICTING":
    case "CONFLICTING_EVIDENCE":
    case "CONTRADICTORY":
    case "CONTRADICTING":
      return {
        icon: "⇄",
        label: "Contradictory Evidence",
        classes: "bg-rose-50 text-rose-800 border-rose-300 ring-1 ring-rose-200/50 font-bold",
      };
    case "INSUFFICIENT_EVIDENCE":
      return {
        icon: "!",
        label: "Insufficient Evidence",
        classes: "bg-amber-50 text-amber-800 border-amber-300 border-dashed ring-1 ring-amber-200/40 font-semibold",
      };
    case "SUPPORTING":
    case "POSITIVE":
      return {
        icon: "✓",
        label: "Supporting Evidence",
        classes: "bg-emerald-50 text-emerald-800 border-emerald-300 ring-1 ring-emerald-200/50 font-semibold",
      };
    case "NEGATIVE":
      return {
        icon: "✕",
        label: "Negative Finding",
        classes: "bg-rose-50 text-rose-800 border-rose-300 ring-1 ring-rose-200/50",
      };
    case "NEUTRAL":
      return {
        icon: "•",
        label: "Neutral Observation",
        classes: "bg-slate-100 text-slate-700 border-slate-300",
      };
    default:
      return {
        icon: "•",
        label: String(state),
        classes: "bg-slate-100 text-slate-700 border-slate-300",
      };
  }
}

export interface VisualStateBadgeProps {
  state: VisualState;
  customText?: string;
  showIcon?: boolean;
  className?: string;
}

export function VisualStateBadge({
  state,
  customText,
  showIcon = true,
  className,
}: VisualStateBadgeProps) {
  const config = getVisualStateConfig(state);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] tracking-wide transition-colors",
        config.classes,
        className
      )}
    >
      {showIcon && <span className="text-[10px] font-bold">{config.icon}</span>}
      <span>{customText || config.label}</span>
    </span>
  );
}

export interface EvidenceBadgeProps {
  state: ScientificEvidenceOrVisualState;
  customText?: string;
  className?: string;
}

export function EvidenceBadge({ state, customText, className }: EvidenceBadgeProps) {
  const config = getVisualStateConfig(state);

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-semibold tracking-wide",
        config.classes,
        className
      )}
    >
      <span className="text-[10px] font-bold">{config.icon}</span>
      <span>{customText || config.label}</span>
    </span>
  );
}

// ==========================================
// 6. ClinicalStage & ClinicalStageIndicator
// ==========================================
export interface ClinicalStageIndicatorProps {
  stage: DevelopmentStage | string;
  className?: string;
}

export function ClinicalStageIndicator({ stage, className }: ClinicalStageIndicatorProps) {
  const stages: DevelopmentStage[] = [
    "Preclinical",
    "Phase I",
    "Phase II",
    "Phase III",
    "Approved",
  ];

  const currentIdx = stages.findIndex((s) => s.toLowerCase() === stage.toLowerCase());

  return (
    <div className={cn("flex items-center gap-1 text-[10px]", className)}>
      {stages.map((st, idx) => {
        const isPassed = currentIdx !== -1 && idx < currentIdx;
        const isCurrent = currentIdx !== -1 && idx === currentIdx;

        return (
          <React.Fragment key={st}>
            <div
              className={cn(
                "flex items-center gap-1 rounded px-1.5 py-0.5 font-semibold transition-colors",
                isCurrent
                  ? "bg-blue-600 text-white shadow-xs"
                  : isPassed
                  ? "bg-slate-200 text-slate-700"
                  : "bg-slate-100 text-slate-400"
              )}
            >
              <span>{st}</span>
            </div>
            {idx < stages.length - 1 && (
              <span className={cn("text-xs", isPassed ? "text-blue-500 font-bold" : "text-slate-300")}>
                ›
              </span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

export interface ClinicalStageProps {
  stage: DevelopmentStage | string;
  variant?: "stepper" | "badge";
  className?: string;
}

export function ClinicalStage({
  stage,
  variant = "stepper",
  className,
}: ClinicalStageProps) {
  if (variant === "badge") {
    return (
      <span
        className={cn(
          "inline-flex items-center rounded-md bg-blue-50 px-2 py-0.5 text-xs font-bold text-blue-700 ring-1 ring-blue-700/10",
          className
        )}
      >
        {stage}
      </span>
    );
  }
  return <ClinicalStageIndicator stage={stage} className={className} />;
}

// ==========================================
// 7. ConfidenceIndicator
// ==========================================
export interface ConfidenceIndicatorProps {
  confidence: number; // 0 to 100
  interval?: [number, number];
  sampleSize?: number;
  modelLineage?: string;
  className?: string;
}

export function ConfidenceIndicator({
  confidence,
  interval,
  sampleSize,
  modelLineage,
  className,
}: ConfidenceIndicatorProps) {
  const getConfidenceLevel = (val: number) => {
    if (val >= 85) return { label: "High Confidence", color: "text-emerald-700 bg-emerald-50 border-emerald-200" };
    if (val >= 65) return { label: "Moderate Confidence", color: "text-blue-700 bg-blue-50 border-blue-200" };
    if (val >= 50) return { label: "Emerging / Tentative", color: "text-amber-700 bg-amber-50 border-amber-200" };
    return { label: "Low Confidence / High Uncertainty", color: "text-rose-700 bg-rose-50 border-rose-200" };
  };

  const level = getConfidenceLevel(confidence);

  return (
    <div className={cn("inline-flex items-center gap-2 rounded-md border p-1.5 text-xs", level.color, className)}>
      <div className="font-bold text-sm leading-none">{confidence}%</div>
      <div className="flex flex-col">
        <span className="font-semibold text-[10px] uppercase tracking-wider">{level.label}</span>
        <div className="flex items-center gap-1.5 text-[9px] text-slate-500 font-medium">
          {interval && <span>CI: [{interval[0]}%, {interval[1]}%]</span>}
          {sampleSize && <span>• n={sampleSize.toLocaleString()}</span>}
          {modelLineage && <span className="italic">• {modelLineage}</span>}
        </div>
      </div>
    </div>
  );
}

// ==========================================
// 8. SourceCitation
// ==========================================
export interface SourceCitationProps {
  citation: string;
  sourceRef: string;
  year?: number;
  url?: string | null;
  className?: string;
}

export function SourceCitation({
  citation,
  sourceRef,
  year,
  url,
  className,
}: SourceCitationProps) {
  const content = (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-700 hover:border-blue-400 hover:bg-blue-50/80 hover:text-blue-800 transition-colors cursor-pointer",
        className
      )}
      title={citation}
    >
      <span className="font-mono font-bold text-blue-700">{sourceRef}</span>
      {year && <span className="text-slate-400 text-[10px]">({year})</span>}
      <svg className="h-3 w-3 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
      </svg>
    </span>
  );

  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer">
        {content}
      </a>
    );
  }

  return content;
}
