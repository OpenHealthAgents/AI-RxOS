"use client";

import React from "react";
import { cn } from "../../lib/utils";
import { AssetIntelligence } from "@ai-rxos/types";
import { AssetStatusBadge } from "./BadgesAndBanners";

export interface AssetHeaderProps {
  asset: AssetIntelligence;
  themeColor?: "blue" | "orange" | "purple" | "emerald";
  className?: string;
  onSelectAction?: () => void;
}

export function AssetHeader({
  asset,
  themeColor = "blue",
  className,
  onSelectAction,
}: AssetHeaderProps) {
  const getIconStyles = () => {
    switch (themeColor) {
      case "orange":
        return {
          bg: "bg-amber-500",
          ring: "ring-amber-200",
          iconChar: "N",
        };
      case "purple":
        return {
          bg: "bg-purple-600",
          ring: "ring-purple-200",
          iconChar: "T",
        };
      case "emerald":
        return {
          bg: "bg-emerald-600",
          ring: "ring-emerald-200",
          iconChar: "P",
        };
      case "blue":
      default:
        return {
          bg: "bg-blue-600",
          ring: "ring-blue-200",
          iconChar: "Z",
        };
    }
  };

  const icon = getIconStyles();

  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all",
        className
      )}
    >
      {/* Top Asset Title & Tags */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3.5">
          <div
            className={cn(
              "flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-white font-bold text-lg shadow-inner ring-2",
              icon.bg,
              icon.ring
            )}
          >
            {icon.iconChar}
          </div>

          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-xl font-bold tracking-tight text-slate-900">
                {asset.name}
                {asset.code_name && (
                  <span className="ml-1 text-slate-500 font-normal text-base">
                    ({asset.code_name})
                  </span>
                )}
              </h2>

              <AssetStatusBadge status={asset.status_label} />

              <span className="rounded bg-blue-100 px-2 py-0.5 text-[11px] font-bold text-blue-800 ring-1 ring-blue-200/50">
                {asset.target}
              </span>
            </div>

            <p className="text-xs font-semibold text-slate-600 mt-0.5">
              {asset.key_attributes["Main differentiation"] || asset.modality}
            </p>
          </div>
        </div>

        {onSelectAction && (
          <button
            onClick={onSelectAction}
            className="rounded border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700 transition"
          >
            Switch Asset
          </button>
        )}
      </div>

      {/* 4-Column Metadata Grid matching Product Vision */}
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 border-t border-slate-100 pt-3.5 text-xs">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Company / Originator
          </span>
          <div className="font-semibold text-slate-800 truncate mt-0.5">
            {asset.owner}
          </div>
        </div>

        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Modality
          </span>
          <div className="font-semibold text-slate-800 truncate mt-0.5">
            {asset.modality}
          </div>
        </div>

        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Development Stage
          </span>
          <div className="font-semibold text-slate-800 truncate mt-0.5">
            {asset.stage}
          </div>
        </div>

        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Primary Indication
          </span>
          <div className="font-semibold text-slate-800 truncate mt-0.5" title={asset.primary_indication}>
            {asset.primary_indication}
          </div>
        </div>
      </div>
    </div>
  );
}
