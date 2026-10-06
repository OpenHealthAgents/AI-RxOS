"use client";

import React from "react";

export interface DevelopmentPotentialMeterProps {
  score1: number;
  name1: string;
  score2: number;
  name2: string;
}

export function DevelopmentPotentialMeter({
  score1,
  name1,
  score2,
  name2,
}: DevelopmentPotentialMeterProps) {
  const renderCircle = (score: number, name: string, isGreen: boolean) => {
    const size = 110;
    const strokeWidth = 9;
    const center = size / 2;
    const radius = center - strokeWidth;
    const circumference = 2 * Math.PI * radius;
    const strokeDashoffset = circumference - (score / 100) * circumference;

    const strokeColor = isGreen
      ? score >= 80
        ? "#047857"
        : "#059669"
      : score >= 50
      ? "#eab308"
      : "#ea580c";

    return (
      <div className="flex flex-col items-center">
        <div className="relative">
          <svg width={size} height={size} className="-rotate-90 transform">
            <circle
              cx={center}
              cy={center}
              r={radius}
              stroke="#e2e8f0"
              strokeWidth={strokeWidth}
              fill="none"
            />
            <circle
              cx={center}
              cy={center}
              r={radius}
              stroke={strokeColor}
              strokeWidth={strokeWidth}
              fill="none"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-all duration-700 ease-out"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-2xl font-bold tracking-tight text-slate-800">
              {score}%
            </span>
          </div>
        </div>
        <span className="mt-2 text-xs font-semibold text-slate-800">{name}</span>
      </div>
    );
  };

  return (
    <div className="flex flex-col items-center justify-between h-full">
      <div className="flex items-center justify-center gap-10 py-2">
        {renderCircle(score1, name1, true)}
        {renderCircle(score2, name2, false)}
      </div>

      {/* Legend */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-3 text-[10px] text-slate-600">
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-red-600" /> Very Low
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-orange-500" /> Low
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-amber-400" /> Moderate
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-emerald-500" /> High
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-emerald-800" /> Very High
        </span>
      </div>
    </div>
  );
}
