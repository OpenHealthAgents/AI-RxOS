"use client";

import React from "react";
import { AssetIntelligence } from "../lib/types";

export interface SafetyToxicityCardProps {
  asset1: AssetIntelligence;
  asset2: AssetIntelligence;
}

export function SafetyToxicityCard({ asset1, asset2 }: SafetyToxicityCardProps) {
  const rows = [
    {
      label: "Common AEs",
      val1: asset1.safety_profile.common_aes,
      val2: asset2.safety_profile.common_aes,
    },
    {
      label: "Dose-limiting toxicities",
      val1: asset1.safety_profile.dose_limiting_toxicities,
      val2: asset2.safety_profile.dose_limiting_toxicities,
    },
    {
      label: "Therapeutic index",
      val1: asset1.safety_profile.therapeutic_index,
      val2: asset2.safety_profile.therapeutic_index,
      highlight1: true,
    },
    {
      label: "Discontinuation rate",
      val1: asset1.safety_profile.discontinuation_rate,
      val2: asset2.safety_profile.discontinuation_rate,
    },
  ];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-slate-600">🛡️</span>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
          Safety & Toxicity Profile
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] font-semibold text-slate-600">
              <th className="py-1.5 px-2 w-1/3">Parameter</th>
              <th className="py-1.5 px-2 w-1/3 text-blue-700">
                {asset1.name} <span className="font-normal text-slate-400 text-[10px]">(preclinical/clinical)</span>
              </th>
              <th className="py-1.5 px-2 w-1/3 text-amber-700">
                {asset2.name} <span className="font-normal text-slate-400 text-[10px]">(clinical)</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50/40"}>
                <td className="py-2 px-2 font-medium text-slate-700">{r.label}</td>
                <td className={`py-2 px-2 ${r.highlight1 ? "text-emerald-700 font-medium" : "text-slate-800"}`}>
                  {r.val1}
                </td>
                <td className="py-2 px-2 text-slate-600">{r.val2}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
