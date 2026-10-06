"use client";

import React from "react";
import { AssetIntelligence } from "../lib/types";

export interface OpportunitiesViewProps {
  assets: AssetIntelligence[];
  onSelectAssetForCompare: (asset: AssetIntelligence) => void;
  onNavigateToEvaluate: (asset: AssetIntelligence) => void;
}

export function OpportunitiesView({
  assets,
  onSelectAssetForCompare,
  onNavigateToEvaluate,
}: OpportunitiesViewProps) {
  const categories = [
    {
      action: "PURSUE",
      title: "Pursue (High Priority)",
      color: "emerald",
      badgeClass: "bg-emerald-600 text-white",
      borderClass: "border-emerald-200 bg-emerald-50/20",
      description: "High development potential, favorable safety margin, and clear biomarker-defined patient population.",
    },
    {
      action: "INVESTIGATE",
      title: "Investigate (Active Exploration)",
      color: "blue",
      badgeClass: "bg-blue-600 text-white",
      borderClass: "border-blue-200 bg-blue-50/20",
      description: "Compelling biological rationale; early clinical proof of concept or safety expansion ongoing.",
    },
    {
      action: "PARTNER",
      title: "Partner / Co-Develop",
      color: "purple",
      badgeClass: "bg-purple-600 text-white",
      borderClass: "border-purple-200 bg-purple-50/20",
      description: "High clinical utility with established commercial sponsor; candidate for combination trials or regional rights.",
    },
    {
      action: "LICENSE",
      title: "Licensing Opportunities",
      color: "cyan",
      badgeClass: "bg-cyan-600 text-white",
      borderClass: "border-cyan-200 bg-cyan-50/20",
      description: "Viable asset available for in-licensing, asset spin-out, or secondary indication expansion.",
    },
    {
      action: "MONITOR",
      title: "Monitor (Niche / Watchlist)",
      color: "amber",
      badgeClass: "bg-amber-500 text-white",
      borderClass: "border-amber-200 bg-amber-50/20",
      description: "Established or competing asset with narrower therapeutic index, generic erosion risk, or crowding.",
    },
    {
      action: "AVOID",
      title: "Avoid (High Liability)",
      color: "rose",
      badgeClass: "bg-rose-600 text-white",
      borderClass: "border-rose-200 bg-rose-50/20",
      description: "Severe off-target toxicities, failed regulatory review, or lack of competitive differentiation.",
    },
  ];

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-6 py-4 text-slate-800">
      <div className="border-b border-slate-200 pb-3">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">
          Strategic Opportunity Action Pipeline
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Categorized biopharma portfolio recommendations across 6 actionable decision tiers
        </p>
      </div>

      <div className="mt-4 space-y-6">
        {categories.map((cat) => {
          const matchingAssets = assets.filter((a) => a.recommendation.action === cat.action);
          return (
            <div
              key={cat.action}
              className={`rounded-lg border ${cat.borderClass} p-4 shadow-sm bg-white`}
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-2 mb-3">
                <div className="flex items-center gap-2">
                  <span className={`rounded px-2.5 py-0.5 text-xs font-bold uppercase ${cat.badgeClass}`}>
                    {cat.action}
                  </span>
                  <h2 className="text-sm font-bold text-slate-900">{cat.title}</h2>
                  <span className="text-xs text-slate-500 font-medium">
                    ({matchingAssets.length} {matchingAssets.length === 1 ? "asset" : "assets"})
                  </span>
                </div>
                <p className="text-xs text-slate-500">{cat.description}</p>
              </div>

              {matchingAssets.length === 0 ? (
                <div className="py-4 text-center text-xs text-slate-400 italic">
                  No assets currently assigned to this decision tier.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {matchingAssets.map((asset) => (
                    <div
                      key={asset.id}
                      className="rounded border border-slate-200 bg-white p-3 shadow-xs hover:border-slate-300 transition-colors flex flex-col justify-between"
                    >
                      <div>
                        <div className="flex items-start justify-between">
                          <div>
                            <h3 className="text-xs font-bold text-slate-900">
                              {asset.name}
                            </h3>
                            <div className="text-[11px] text-slate-500">
                              {asset.owner}
                            </div>
                          </div>
                          <span className="font-bold text-xs text-slate-800">
                            {asset.recommendation.development_potential_score}%
                          </span>
                        </div>

                        <div className="mt-2 flex items-center gap-1.5 text-[10px]">
                          <span className="rounded bg-blue-100 px-1.5 py-0.2 text-blue-800 font-bold">
                            {asset.target}
                          </span>
                          <span className="rounded bg-slate-100 px-1.5 py-0.2 text-slate-700">
                            {asset.stage}
                          </span>
                          <span className="rounded bg-emerald-100 px-1.5 py-0.2 text-emerald-800">
                            CNS {asset.biology_profile.cns_potential}
                          </span>
                        </div>

                        <p className="mt-2 text-[11px] text-slate-600 line-clamp-2">
                          {asset.recommendation.rationale}
                        </p>
                      </div>

                      <div className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
                        <button
                          onClick={() => onNavigateToEvaluate(asset)}
                          className="text-blue-600 hover:underline font-medium"
                        >
                          Evaluate Dossier
                        </button>
                        <button
                          onClick={() => onSelectAssetForCompare(asset)}
                          className="rounded bg-slate-100 px-2 py-0.5 text-slate-700 font-semibold hover:bg-slate-200"
                        >
                          Compare
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
