"use client";

import React, { useState } from "react";
import { AssetIntelligence } from "../lib/types";

export interface DiscoverViewProps {
  assets: AssetIntelligence[];
  onSelectAssetForCompare: (asset: AssetIntelligence) => void;
  onNavigateToEvaluate: (asset: AssetIntelligence) => void;
}

export function DiscoverView({
  assets,
  onSelectAssetForCompare,
  onNavigateToEvaluate,
}: DiscoverViewProps) {
  const [selectedTarget, setSelectedTarget] = useState<string>("ALL");
  const [selectedAction, setSelectedAction] = useState<string>("ALL");
  const [search, setSearch] = useState("");

  const filtered = assets.filter((a) => {
    if (selectedTarget !== "ALL" && a.target.toUpperCase() !== selectedTarget) return false;
    if (selectedAction !== "ALL" && a.recommendation.action !== selectedAction) return false;
    if (search) {
      const q = search.toLowerCase();
      const match =
        a.name.toLowerCase().includes(q) ||
        (a.code_name && a.code_name.toLowerCase().includes(q)) ||
        a.owner.toLowerCase().includes(q) ||
        a.primary_indication.toLowerCase().includes(q);
      if (!match) return false;
    }
    return true;
  });

  const getActionBadgeColor = (action: string) => {
    switch (action) {
      case "PURSUE":
        return "bg-emerald-600 text-white";
      case "INVESTIGATE":
        return "bg-blue-600 text-white";
      case "PARTNER":
        return "bg-purple-600 text-white";
      case "LICENSE":
        return "bg-cyan-600 text-white";
      case "MONITOR":
        return "bg-amber-500 text-white";
      case "AVOID":
        return "bg-rose-600 text-white";
      default:
        return "bg-slate-600 text-white";
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-6 py-4 text-slate-800">
      <div className="border-b border-slate-200 pb-3">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">
          Discover Oncology Opportunities
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Multi-attribute filtering across validated kinase targets, stages, and strategic decision actions
        </p>
      </div>

      {/* Filter Bar */}
      <div className="mt-4 flex flex-wrap items-center gap-3 bg-white p-3 rounded-lg border border-slate-200 shadow-sm text-xs">
        <div>
          <label className="block text-[10px] font-semibold text-slate-500 mb-1">
            TARGET
          </label>
          <select
            value={selectedTarget}
            onChange={(e) => setSelectedTarget(e.target.value)}
            className="rounded border border-slate-300 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700 outline-none"
          >
            <option value="ALL">All Targets</option>
            <option value="HER2">HER2 (ERBB2)</option>
            <option value="EGFR">EGFR</option>
            <option value="KRAS">KRAS</option>
            <option value="CDK4/6">CDK4/6</option>
          </select>
        </div>

        <div>
          <label className="block text-[10px] font-semibold text-slate-500 mb-1">
            STRATEGIC ACTION
          </label>
          <select
            value={selectedAction}
            onChange={(e) => setSelectedAction(e.target.value)}
            className="rounded border border-slate-300 bg-slate-50 px-2 py-1 text-xs font-medium text-slate-700 outline-none"
          >
            <option value="ALL">All Actions</option>
            <option value="PURSUE">PURSUE</option>
            <option value="INVESTIGATE">INVESTIGATE</option>
            <option value="PARTNER">PARTNER</option>
            <option value="LICENSE">LICENSE</option>
            <option value="MONITOR">MONITOR</option>
            <option value="AVOID">AVOID</option>
          </select>
        </div>

        <div className="flex-1 min-w-[200px]">
          <label className="block text-[10px] font-semibold text-slate-500 mb-1">
            KEYWORD SEARCH
          </label>
          <input
            type="text"
            placeholder="Search by name, owner, or indication..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full rounded border border-slate-300 bg-slate-50 px-2.5 py-1 text-xs text-slate-800 placeholder-slate-400 outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Asset Grid */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map((asset) => {
          return (
            <div
              key={asset.id}
              className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:shadow-md transition-shadow flex flex-col justify-between"
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-1.5">
                      <h3 className="text-base font-bold text-slate-900">{asset.name}</h3>
                      {asset.code_name && (
                        <span className="text-xs text-slate-500">({asset.code_name})</span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">{asset.owner}</div>
                  </div>
                  <span
                    className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase shadow-sm ${getActionBadgeColor(
                      asset.recommendation.action
                    )}`}
                  >
                    {asset.recommendation.action}
                  </span>
                </div>

                <div className="mt-3 flex items-center gap-2">
                  <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800">
                    {asset.target}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                    {asset.stage}
                  </span>
                  <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-semibold text-purple-800">
                    {asset.modality}
                  </span>
                </div>

                <p className="mt-2 text-xs text-slate-600 line-clamp-2">
                  {asset.primary_indication}
                </p>

                {/* Score indicators */}
                <div className="mt-3 pt-3 border-t border-slate-100 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded bg-slate-50 p-1.5">
                    <div className="text-[10px] text-slate-500">Dev Potential</div>
                    <div className="font-bold text-slate-900">
                      {asset.recommendation.development_potential_score}%
                    </div>
                  </div>
                  <div className="rounded bg-slate-50 p-1.5">
                    <div className="text-[10px] text-slate-500">CNS Potential</div>
                    <div className="font-bold text-blue-600">
                      {asset.biology_profile.cns_potential}
                    </div>
                  </div>
                  <div className="rounded bg-slate-50 p-1.5">
                    <div className="text-[10px] text-slate-500">Safety Score</div>
                    <div className="font-bold text-emerald-600">
                      {asset.safety_profile.safety_score}
                    </div>
                  </div>
                </div>
              </div>

              {/* Action buttons */}
              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between gap-2 text-xs">
                <button
                  onClick={() => onNavigateToEvaluate(asset)}
                  className="rounded border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Evaluate Dossier
                </button>
                <button
                  onClick={() => onSelectAssetForCompare(asset)}
                  className="rounded bg-blue-600 px-3 py-1 font-semibold text-white hover:bg-blue-500"
                >
                  Compare
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
