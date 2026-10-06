"use client";

import React from "react";
import { cn } from "../../lib/utils";
import { BiologyProfileMetrics } from "@ai-rxos/types";

// ==========================================
// 1. ScoreGauge
// ==========================================
export interface ScoreGaugeProps {
  score: number; // 0 to 100
  name: string;
  subtitle?: string;
  tier?: "Very Low" | "Low" | "Moderate" | "High" | "Very High";
  colorTheme?: "emerald" | "amber" | "rose" | "blue";
  showLegend?: boolean;
  className?: string;
}

export function ScoreGauge({
  score,
  name,
  subtitle,
  tier,
  colorTheme = "emerald",
  showLegend = true,
  className,
}: ScoreGaugeProps) {
  const size = 110;
  const strokeWidth = 9;
  const center = size / 2;
  const radius = center - strokeWidth;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (Math.min(Math.max(score, 0), 100) / 100) * circumference;

  const getColorConfig = () => {
    switch (colorTheme) {
      case "amber":
        return {
          stroke: "#f59e0b",
          text: "text-amber-800",
          track: "#fef3c7",
        };
      case "rose":
        return {
          stroke: "#f43f5e",
          text: "text-rose-800",
          track: "#ffe4e6",
        };
      case "blue":
        return {
          stroke: "#2563eb",
          text: "text-blue-800",
          track: "#dbeafe",
        };
      case "emerald":
      default:
        return {
          stroke: "#059669",
          text: "text-emerald-800",
          track: "#d1fae5",
        };
    }
  };

  const config = getColorConfig();

  const getTierFromScore = (s: number): string => {
    if (s >= 80) return "Very High";
    if (s >= 60) return "High";
    if (s >= 40) return "Moderate";
    if (s >= 20) return "Low";
    return "Very Low";
  };

  const displayTier = tier || getTierFromScore(score);

  return (
    <div className={cn("flex flex-col items-center text-center", className)}>
      <div className="relative">
        <svg width={size} height={size} className="rotate-[-90deg]">
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="transparent"
            stroke={config.track}
            strokeWidth={strokeWidth}
          />
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="transparent"
            stroke={config.stroke}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className="transition-all duration-700 ease-out"
          />
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn("text-2xl font-black tracking-tight", config.text)}>
            {score}%
          </span>
          {displayTier && (
            <span className="text-[9px] font-bold uppercase tracking-wider text-slate-500">
              {displayTier}
            </span>
          )}
        </div>
      </div>

      <div className="mt-2">
        <h4 className="text-xs font-bold text-slate-900">{name}</h4>
        {subtitle && <p className="text-[10px] text-slate-500">{subtitle}</p>}
      </div>

      {showLegend && (
        <div className="mt-3 flex items-center justify-center gap-2 text-[9px] text-slate-500 font-medium">
          <span className="inline-flex items-center gap-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-rose-500" /> Very Low
          </span>
          <span className="inline-flex items-center gap-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> Low
          </span>
          <span className="inline-flex items-center gap-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-yellow-400" /> Moderate
          </span>
          <span className="inline-flex items-center gap-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> High
          </span>
          <span className="inline-flex items-center gap-0.5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-600" /> Very High
          </span>
        </div>
      )}
    </div>
  );
}

// ==========================================
// 2. ScoreCard
// ==========================================
export interface ScoreCardProps {
  title: string;
  score: number;
  maxScore?: number;
  benchmarkScore?: number;
  benchmarkName?: string;
  category?: string;
  confidenceInterval?: [number, number];
  modelLineage?: string;
  uncertaintyRationale?: string;
  className?: string;
}

export function ScoreCard({
  title,
  score,
  maxScore = 100,
  benchmarkScore,
  benchmarkName,
  category,
  confidenceInterval,
  modelLineage,
  uncertaintyRationale,
  className,
}: ScoreCardProps) {
  const percentage = Math.round((score / maxScore) * 100);
  const delta = benchmarkScore !== undefined ? score - benchmarkScore : null;

  return (
    <div
      className={cn(
        "rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300",
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
          {category || "Scientific Metric"}
        </span>
        {confidenceInterval && (
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-medium text-slate-600">
            95% CI: [{confidenceInterval[0]} - {confidenceInterval[1]}]
          </span>
        )}
      </div>

      <h4 className="text-xs font-bold text-slate-800 mt-1">{title}</h4>

      <div className="mt-2.5 flex items-baseline justify-between">
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-black text-slate-900">{score}</span>
          <span className="text-xs text-slate-400">/{maxScore}</span>
        </div>

        {delta !== null && (
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[10px] font-bold",
              delta > 0
                ? "bg-emerald-100 text-emerald-800"
                : delta < 0
                ? "bg-rose-100 text-rose-800"
                : "bg-slate-100 text-slate-600"
            )}
          >
            {delta > 0 ? `+${delta}` : delta} vs {benchmarkName || "Benchmark"}
          </span>
        )}
      </div>

      {/* Progress bar */}
      <div className="mt-2.5 h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all duration-500",
            percentage >= 75
              ? "bg-emerald-500"
              : percentage >= 50
              ? "bg-blue-500"
              : percentage >= 30
              ? "bg-amber-500"
              : "bg-rose-500"
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>

      {(modelLineage || uncertaintyRationale) && (
        <div className="mt-2.5 pt-2 border-t border-slate-100 text-[10px] text-slate-500 flex flex-col gap-0.5">
          {modelLineage && <span className="font-medium italic">Lineage: {modelLineage}</span>}
          {uncertaintyRationale && (
            <span className="text-amber-700">⚠️ {uncertaintyRationale}</span>
          )}
        </div>
      )}
    </div>
  );
}

// ==========================================
// 3. RadarProfile (6-Dimensional Spider Chart)
// ==========================================
export interface RadarProfileProps {
  asset1Name: string;
  asset1Metrics: BiologyProfileMetrics;
  asset2Name?: string;
  asset2Metrics?: BiologyProfileMetrics;
  size?: number;
  className?: string;
}

export function RadarProfile({
  asset1Name,
  asset1Metrics,
  asset2Name,
  asset2Metrics,
  size = 280,
  className,
}: RadarProfileProps) {
  const axes = [
    { key: "target_selectivity" as const, label: "Target Selectivity" },
    { key: "potency" as const, label: "Potency" },
    { key: "cns_potential" as const, label: "CNS Potential" },
    { key: "biomarker_strategy" as const, label: "Biomarker Strategy" },
    { key: "clinical_readiness" as const, label: "Clinical Readiness" },
    { key: "safety_ti" as const, label: "Safety / TI" },
  ];

  const center = size / 2;
  const radius = center - 45;
  const numAxes = axes.length;

  const getCoordinates = (index: number, value: number) => {
    const angle = (Math.PI * 2 / numAxes) * index - Math.PI / 2;
    const r = (value / 100) * radius;
    const x = center + r * Math.cos(angle);
    const y = center + r * Math.sin(angle);
    return { x, y };
  };

  const getPolygonPoints = (metrics: BiologyProfileMetrics) => {
    return axes
      .map((axis, i) => {
        const val = metrics[axis.key] || 0;
        const coords = getCoordinates(i, val);
        return `${coords.x},${coords.y}`;
      })
      .join(" ");
  };

  const gridLevels = [20, 40, 60, 80, 100];

  return (
    <div className={cn("flex flex-col items-center justify-center p-2", className)}>
      <svg width={size} height={size} className="overflow-visible">
        {/* Background Web Polygons */}
        {gridLevels.map((level) => {
          const points = axes
            .map((_, i) => {
              const coords = getCoordinates(i, level);
              return `${coords.x},${coords.y}`;
            })
            .join(" ");
          return (
            <polygon
              key={level}
              points={points}
              fill="none"
              stroke="#e2e8f0"
              strokeWidth="1"
              strokeDasharray={level === 100 ? "none" : "2,2"}
            />
          );
        })}

        {/* Axis Lines & Labels */}
        {axes.map((axis, i) => {
          const edgeCoords = getCoordinates(i, 100);
          const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
          const labelDist = radius + 18;
          const lx = center + labelDist * Math.cos(angle);
          const ly = center + labelDist * Math.sin(angle);

          return (
            <g key={axis.key}>
              <line
                x1={center}
                y1={center}
                x2={edgeCoords.x}
                y2={edgeCoords.y}
                stroke="#cbd5e1"
                strokeWidth="1"
              />
              <text
                x={lx}
                y={ly}
                textAnchor="middle"
                dominantBaseline="central"
                className="fill-slate-600 text-[10px] font-semibold tracking-tight select-none"
              >
                {axis.label}
              </text>
            </g>
          );
        })}

        {/* Asset 2 Polygon (Orange / Benchmark) */}
        {asset2Metrics && (
          <polygon
            points={getPolygonPoints(asset2Metrics)}
            fill="rgba(245, 158, 11, 0.25)"
            stroke="#f59e0b"
            strokeWidth="2"
            strokeDasharray="4,2"
          />
        )}

        {/* Asset 1 Polygon (Blue / Primary Target) */}
        <polygon
          points={getPolygonPoints(asset1Metrics)}
          fill="rgba(37, 99, 235, 0.3)"
          stroke="#2563eb"
          strokeWidth="2.5"
        />

        {/* Points on Primary Asset */}
        {axes.map((axis, i) => {
          const coords = getCoordinates(i, asset1Metrics[axis.key] || 0);
          return (
            <circle
              key={axis.key}
              cx={coords.x}
              cy={coords.y}
              r="3.5"
              fill="#2563eb"
              stroke="#ffffff"
              strokeWidth="1.5"
            />
          );
        })}
      </svg>

      {/* Legend */}
      <div className="mt-2 flex items-center justify-center gap-4 text-xs font-semibold">
        <span className="flex items-center gap-1.5 text-blue-700">
          <span className="h-2.5 w-2.5 rounded-full bg-blue-600" />
          {asset1Name}
        </span>
        {asset2Name && (
          <span className="flex items-center gap-1.5 text-amber-700">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
            {asset2Name}
          </span>
        )}
      </div>
    </div>
  );
}
