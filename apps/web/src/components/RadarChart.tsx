"use client";

import React from "react";
import { BiologyProfileMetrics } from "../lib/types";

export interface RadarChartProps {
  asset1Name: string;
  asset1Metrics: BiologyProfileMetrics;
  asset2Name: string;
  asset2Metrics: BiologyProfileMetrics;
}

export function RadarChart({
  asset1Name,
  asset1Metrics,
  asset2Name,
  asset2Metrics,
}: RadarChartProps) {
  // 6 dimensions
  const axes = [
    { key: "target_selectivity", label: "Target\nSelectivity" },
    { key: "potency", label: "Potency" },
    { key: "cns_potential", label: "CNS\nPotential" },
    { key: "biomarker_strategy", label: "Biomarker\nStrategy" },
    { key: "clinical_readiness", label: "Clinical\nReadiness" },
    { key: "safety_ti", label: "Safety/TI" },
  ] as const;

  const size = 260;
  const center = size / 2;
  const radius = 80;
  const totalAxes = axes.length;

  // Compute (x, y) coordinates for an angle and normalized value (0 - 100)
  const getCoordinates = (index: number, value: number) => {
    // Angle in radians, starting at top (-pi/2)
    const angle = (Math.PI * 2 / totalAxes) * index - Math.PI / 2;
    const r = (value / 100) * radius;
    const x = center + r * Math.cos(angle);
    const y = center + r * Math.sin(angle);
    return { x, y };
  };

  // Grid levels (20%, 40%, 60%, 80%, 100%)
  const levels = [20, 40, 60, 80, 100];

  // Polygon points for asset 1
  const points1 = axes
    .map((axis, i) => {
      const val = (asset1Metrics as any)[axis.key] ?? 50;
      const { x, y } = getCoordinates(i, val);
      return `${x},${y}`;
    })
    .join(" ");

  // Polygon points for asset 2
  const points2 = axes
    .map((axis, i) => {
      const val = (asset2Metrics as any)[axis.key] ?? 50;
      const { x, y } = getCoordinates(i, val);
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size} className="overflow-visible">
        {/* Background web grids */}
        {levels.map((level) => {
          const levelPoints = axes
            .map((_, i) => {
              const { x, y } = getCoordinates(i, level);
              return `${x},${y}`;
            })
            .join(" ");
          return (
            <polygon
              key={level}
              points={levelPoints}
              fill="none"
              stroke="#cbd5e1"
              strokeWidth="1"
              strokeDasharray={level === 100 ? "none" : "2,2"}
            />
          );
        })}

        {/* Axis radial spokes */}
        {axes.map((_, i) => {
          const { x, y } = getCoordinates(i, 100);
          return (
            <line
              key={i}
              x1={center}
              y1={center}
              x2={x}
              y2={y}
              stroke="#cbd5e1"
              strokeWidth="1"
            />
          );
        })}

        {/* Asset 1 (Blue) Polygon */}
        <polygon
          points={points1}
          fill="rgba(37, 99, 235, 0.20)"
          stroke="#2563eb"
          strokeWidth="2.5"
        />

        {/* Asset 2 (Orange) Polygon */}
        <polygon
          points={points2}
          fill="rgba(249, 115, 22, 0.18)"
          stroke="#f97316"
          strokeWidth="2.5"
        />

        {/* Asset 1 markers */}
        {axes.map((axis, i) => {
          const val = (asset1Metrics as any)[axis.key] ?? 50;
          const { x, y } = getCoordinates(i, val);
          return (
            <circle
              key={`a1-${i}`}
              cx={x}
              cy={y}
              r="3.5"
              fill="#2563eb"
              stroke="#ffffff"
              strokeWidth="1.5"
            />
          );
        })}

        {/* Asset 2 markers */}
        {axes.map((axis, i) => {
          const val = (asset2Metrics as any)[axis.key] ?? 50;
          const { x, y } = getCoordinates(i, val);
          return (
            <circle
              key={`a2-${i}`}
              cx={x}
              cy={y}
              r="3.5"
              fill="#f97316"
              stroke="#ffffff"
              strokeWidth="1.5"
            />
          );
        })}

        {/* Axis Labels */}
        {axes.map((axis, i) => {
          const { x, y } = getCoordinates(i, 118);
          const lines = axis.label.split("\n");
          return (
            <text
              key={`label-${i}`}
              x={x}
              y={y}
              textAnchor="middle"
              dominantBaseline="central"
              className="fill-slate-600 text-[10px] font-semibold"
            >
              {lines.map((line, lineIdx) => (
                <tspan
                  key={lineIdx}
                  x={x}
                  dy={lineIdx === 0 ? `-${(lines.length - 1) * 5}px` : "11px"}
                >
                  {line}
                </tspan>
              ))}
            </text>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="mt-2 flex items-center justify-center gap-6 text-[11px] font-medium">
        <div className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-6 rounded bg-[#2563eb]" />
          <span className="text-slate-700">{asset1Name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block h-2.5 w-6 rounded bg-[#f97316]" />
          <span className="text-slate-700">{asset2Name}</span>
        </div>
      </div>
    </div>
  );
}
