"use client";

import React from "react";
import { AssetIntelligence } from "../lib/types";

export interface PatientMatchCardProps {
  asset1: AssetIntelligence;
  asset2: AssetIntelligence;
}

export function PatientMatchCard({ asset1, asset2 }: PatientMatchCardProps) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-slate-600">👥</span>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
          Patient Match
        </h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
        {/* Left: Asset 1 */}
        <div>
          <div className="font-semibold text-blue-700 mb-1.5">{asset1.name}</div>
          <div className="text-[11px] font-semibold text-slate-700 mb-2">
            Best Patient Population
          </div>
          <ul className="space-y-1.5 text-slate-700">
            {asset1.patient_match.best_patient_population.map((pop, idx) => (
              <li key={idx} className="flex items-start gap-1.5">
                <span className="text-emerald-600 font-bold">✓</span>
                <span>{pop}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Right: Asset 2 */}
        <div className="border-t md:border-t-0 md:border-l border-slate-200 pt-3 md:pt-0 md:pl-4">
          <div className="font-semibold text-amber-700 mb-1.5">{asset2.name}</div>
          <div className="text-[11px] font-semibold text-slate-700 mb-2">
            Best Patient Population
          </div>
          <ul className="space-y-1.5 text-slate-600">
            {asset2.patient_match.best_patient_population.map((pop, idx) => (
              <li key={idx} className="flex items-start gap-1.5">
                <span className="text-slate-500 font-bold">✓</span>
                <span>{pop}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
