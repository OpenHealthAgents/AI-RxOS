"use client";

import React from "react";
import { AssetIntelligence } from "../lib/types";

export interface ResistanceCombinationsCardProps {
  asset1: AssetIntelligence;
  asset2: AssetIntelligence;
}

export function ResistanceCombinationsCard({
  asset1,
  asset2,
}: ResistanceCombinationsCardProps) {
  const renderDot = (impact: string) => {
    if (impact === "High") {
      return (
        <span className="inline-flex items-center gap-1 text-[10px] font-medium text-rose-700">
          <span className="h-2 w-2 rounded-full bg-rose-600" /> High
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-700">
        <span className="h-2 w-2 rounded-full bg-amber-500" /> Moderate
      </span>
    );
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-800">
        Resistance & Combination Insights
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
        {/* Left: Asset 1 (Zongertinib) */}
        <div className="space-y-4">
          <div className="font-semibold text-blue-700 border-b border-slate-100 pb-1">
            {asset1.name}
          </div>

          <div>
            <div className="text-[11px] font-semibold text-slate-700 mb-2">
              Predicted Resistance Mechanisms
            </div>
            <div className="space-y-1.5">
              {asset1.resistance_mechanisms.map((mech, idx) => (
                <div key={idx} className="flex items-center justify-between">
                  <span className="text-slate-700 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                    {mech.name}
                  </span>
                  {renderDot(mech.impact)}
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-slate-700 mb-2">
              Recommended Combinations
            </div>
            <div className="space-y-2">
              {asset1.combinations.map((combo, idx) => (
                <div key={idx} className="rounded bg-emerald-50/60 p-2 border border-emerald-100">
                  <div className="font-semibold text-emerald-800 flex items-center gap-1.5">
                    <svg className="h-3.5 w-3.5 text-emerald-600 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    {combo.partner_name}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-600 pl-5">
                    {combo.rationale}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Asset 2 (Neratinib) */}
        <div className="space-y-4 border-t md:border-t-0 md:border-l border-slate-200 pt-4 md:pt-0 md:pl-6">
          <div className="font-semibold text-amber-700 border-b border-slate-100 pb-1">
            {asset2.name}
          </div>

          <div>
            <div className="text-[11px] font-semibold text-slate-700 mb-2">
              Known Resistance Mechanisms
            </div>
            <div className="space-y-1.5">
              {asset2.resistance_mechanisms.map((mech, idx) => (
                <div key={idx} className="flex items-center justify-between">
                  <span className="text-slate-700 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                    {mech.name}
                  </span>
                  {renderDot(mech.impact)}
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-semibold text-slate-700 mb-2">
              Clinical Combination Experience
            </div>
            <div className="space-y-2">
              {asset2.combinations.map((combo, idx) => (
                <div key={idx} className="rounded bg-slate-50 p-2 border border-slate-200">
                  <div className="font-semibold text-slate-800 flex items-center gap-1.5">
                    <span className="text-xs">📋</span>
                    {combo.partner_name}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-600 pl-5">
                    {combo.clinical_status}: {combo.rationale}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
