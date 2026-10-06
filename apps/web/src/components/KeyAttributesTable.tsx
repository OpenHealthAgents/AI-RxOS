"use client";

import React from "react";
import { AssetIntelligence } from "../lib/types";

export interface KeyAttributesTableProps {
  asset1: AssetIntelligence;
  asset2: AssetIntelligence;
}

export function KeyAttributesTable({ asset1, asset2 }: KeyAttributesTableProps) {
  const attributeKeys = [
    "Selectivity",
    "IC50 (HER2)",
    "Activity in HER2 mutants",
    "CNS penetration (preclinical)",
    "In vivo efficacy (preclinical)",
    "Main differentiation",
    "Current stage",
    "Key indications",
  ];

  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
          Key Attributes
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold text-slate-600">
              <th className="py-2 px-3 w-1/4">Attribute</th>
              <th className="py-2 px-3 w-3/8 text-blue-700">{asset1.name}</th>
              <th className="py-2 px-3 w-3/8 text-amber-700">{asset2.name}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {attributeKeys.map((key, idx) => {
              const val1 = asset1.key_attributes[key] ?? "-";
              const val2 = asset2.key_attributes[key] ?? "-";
              return (
                <tr
                  key={key}
                  className={idx % 2 === 0 ? "bg-white" : "bg-slate-50/50"}
                >
                  <td className="py-2 px-3 font-medium text-slate-700">{key}</td>
                  <td className="py-2 px-3 text-slate-800 font-normal">{val1}</td>
                  <td className="py-2 px-3 text-slate-600 font-normal">{val2}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
