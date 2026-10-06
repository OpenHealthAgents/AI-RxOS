"use client";

import React from "react";
import { AssetIntelligence } from "../lib/types";

export interface BusinessLandscapeCardProps {
  asset1: AssetIntelligence;
  asset2: AssetIntelligence;
}

export function BusinessLandscapeCard({
  asset1,
  asset2,
}: BusinessLandscapeCardProps) {
  const rows = [
    {
      label: "Current owner",
      val1: asset1.business_profile.current_owner,
      val2: asset2.business_profile.current_owner,
    },
    {
      label: "Patent/IP",
      val1: asset1.business_profile.patent_ip,
      val2: asset2.business_profile.patent_ip,
    },
    {
      label: "Commercial opportunity",
      val1: asset1.business_profile.commercial_opportunity,
      val2: asset2.business_profile.commercial_opportunity,
    },
    {
      label: "Competitive assets",
      val1: asset1.business_profile.competitive_assets,
      val2: asset2.business_profile.competitive_assets,
    },
  ];

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-slate-600">📊</span>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
          Business & Competitive Landscape
        </h3>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 text-[11px] font-semibold text-slate-600">
              <th className="py-1.5 px-2 w-1/3">Parameter</th>
              <th className="py-1.5 px-2 w-1/3 text-blue-700">{asset1.name}</th>
              <th className="py-1.5 px-2 w-1/3 text-amber-700">{asset2.name}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-slate-50/40"}>
                <td className="py-2 px-2 font-medium text-slate-700">{r.label}</td>
                <td className="py-2 px-2 text-slate-800">{r.val1}</td>
                <td className="py-2 px-2 text-slate-600">{r.val2}</td>
              </tr>
            ))}
            {/* Recommended action row */}
            <tr className="bg-slate-50/80 font-medium">
              <td className="py-2.5 px-2 font-semibold text-slate-800">
                Recommended action
              </td>
              <td className="py-2.5 px-2">
                <span className="inline-flex items-center rounded-md bg-emerald-600 px-2.5 py-0.5 text-xs font-bold text-white shadow-sm">
                  {asset1.recommendation.action}
                </span>
              </td>
              <td className="py-2.5 px-2">
                <span className="inline-flex items-center rounded-md bg-amber-500 px-2.5 py-0.5 text-xs font-bold text-white shadow-sm">
                  {asset2.recommendation.action}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-[10px] text-slate-400 italic">
        * {asset1.business_profile.fto_legal_disclaimer}
      </div>
    </div>
  );
}
