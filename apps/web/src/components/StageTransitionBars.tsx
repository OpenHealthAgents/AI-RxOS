"use client";

import React from "react";
import { StageTransitionProbabilities } from "../lib/types";

export interface StageTransitionBarsProps {
  name1: string;
  transitions1: StageTransitionProbabilities;
  name2: string;
  transitions2: StageTransitionProbabilities;
}

export function StageTransitionBars({
  name1,
  transitions1,
  name2,
  transitions2,
}: StageTransitionBarsProps) {
  const stages = [
    {
      label: "Preclinical → IND",
      val1: Math.round(transitions1.preclinical_to_ind * 100),
      val2: Math.round(transitions2.preclinical_to_ind * 100),
    },
    {
      label: "Phase I → II",
      val1: Math.round(transitions1.phase_i_to_ii * 100),
      val2: Math.round(transitions2.phase_i_to_ii * 100),
    },
    {
      label: "Phase II → III",
      val1: Math.round(transitions1.phase_ii_to_iii * 100),
      val2: Math.round(transitions2.phase_ii_to_iii * 100),
    },
    {
      label: "Phase III → Approval",
      val1: Math.round(transitions1.phase_iii_to_approval * 100),
      val2: Math.round(transitions2.phase_iii_to_approval * 100),
    },
  ];

  const getBarColor = (val: number) => {
    if (val >= 85) return "bg-emerald-500";
    if (val >= 70) return "bg-emerald-400";
    if (val >= 55) return "bg-amber-400";
    if (val >= 40) return "bg-orange-400";
    return "bg-rose-400";
  };

  return (
    <div className="flex flex-col justify-between h-full">
      {/* Column Headers */}
      <div className="grid grid-cols-2 gap-4 pb-2 border-b border-slate-200 text-xs font-semibold">
        <div className="text-emerald-700">{name1}</div>
        <div className="text-amber-700">{name2} (historical)</div>
      </div>

      <div className="space-y-3 py-2">
        {stages.map((stage, idx) => (
          <div key={idx} className="grid grid-cols-2 gap-4">
            {/* Asset 1 Bar */}
            <div>
              <div className="flex justify-between text-[11px] font-medium text-slate-700 mb-0.5">
                <span>{stage.label}</span>
                <span className="font-semibold text-slate-800">{stage.val1}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-full rounded-full ${getBarColor(stage.val1)} transition-all duration-500`}
                  style={{ width: `${stage.val1}%` }}
                />
              </div>
            </div>

            {/* Asset 2 Bar */}
            <div>
              <div className="flex justify-between text-[11px] font-medium text-slate-700 mb-0.5">
                <span>{stage.label}</span>
                <span className="font-semibold text-slate-800">{stage.val2}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-full rounded-full ${getBarColor(stage.val2)} transition-all duration-500`}
                  style={{ width: `${stage.val2}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="mt-2 text-[10px] italic text-slate-500 leading-tight">
        Note: {name1} predictions based on current and historical data. {name2} probabilities reflect retrospective model performance using pre-approval historical data.
      </p>
    </div>
  );
}
