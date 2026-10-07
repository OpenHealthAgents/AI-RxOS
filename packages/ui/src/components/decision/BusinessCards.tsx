"use client";

import React from "react";
import { cn } from "../../lib/utils";
import { BusinessCompetitiveProfile, StrategicAction } from "@ai-rxos/types";
import { DecisionBadge } from "./BadgesAndBanners";

// ==========================================
// 1. CompetitiveLandscapeCard
// ==========================================
export interface CompetitiveLandscapeCardProps {
  business1: BusinessCompetitiveProfile;
  name1: string;
  action1: StrategicAction;
  business2?: BusinessCompetitiveProfile;
  name2?: string;
  action2?: StrategicAction;
  className?: string;
}

export function CompetitiveLandscapeCard({
  business1,
  name1,
  action1,
  business2,
  name2,
  action2,
  className,
}: CompetitiveLandscapeCardProps) {
  const rows = [
    { label: "Current Owner", val1: business1.current_owner, val2: business2?.current_owner },
    { label: "Patent / IP Exclusivity", val1: business1.patent_ip, val2: business2?.patent_ip },
    { label: "Commercial Opportunity", val1: business1.commercial_opportunity, val2: business2?.commercial_opportunity },
    { label: "Competitive Assets", val1: business1.competitive_assets, val2: business2?.competitive_assets },
    { label: "Licensing / Partnering Feasibility", val1: business1.licensing_partnering_feasibility, val2: business2?.licensing_partnering_feasibility },
  ];

  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4",
        className
      )}
    >
      <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
        <span className="text-base">💼</span>
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Business & Competitive Landscape
          </h3>
          <p className="text-[11px] text-slate-500">
            Intellectual property horizons, ownership, and commercial positioning
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-bold uppercase text-slate-500">
              <th className="py-2.5 px-3 w-1/4">Parameter</th>
              <th className="py-2.5 px-3 text-blue-700 font-bold w-[37.5%]">{name1}</th>
              {business2 && name2 && (
                <th className="py-2.5 px-3 text-amber-700 font-bold w-[37.5%]">{name2}</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((r, idx) => (
              <tr key={r.label} className={idx % 2 === 0 ? "bg-white" : "bg-slate-50/40"}>
                <td className="py-2.5 px-3 font-semibold text-slate-600">{r.label}</td>
                <td className="py-2.5 px-3 font-medium text-slate-900">{r.val1}</td>
                {r.val2 && <td className="py-2.5 px-3 text-slate-700">{r.val2}</td>}
              </tr>
            ))}
            {/* Recommended Action Row */}
            <tr className="bg-slate-50 font-bold">
              <td className="py-2.5 px-3 uppercase tracking-wider text-slate-600">
                Recommended Action
              </td>
              <td className="py-2.5 px-3">
                <DecisionBadge action={action1} size="sm" />
              </td>
              {action2 && (
                <td className="py-2.5 px-3">
                  <DecisionBadge action={action2} size="sm" />
                </td>
              )}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="rounded bg-amber-50 border border-amber-200 p-2 text-[10px] text-amber-900 leading-relaxed">
        <strong>FTO Legal Notice:</strong> {business1.fto_legal_disclaimer}
      </div>
    </div>
  );
}

// ==========================================
// 2. LicensingCard
// ==========================================
export interface LicensingCardProps {
  assetName: string;
  feasibility: string;
  patentWindow: string;
  rightsOwner: string;
  territoryAvailability?: string;
  dealPrecedents?: string;
  className?: string;
}

export function LicensingCard({
  assetName,
  feasibility,
  patentWindow,
  rightsOwner,
  territoryAvailability = "Regional ex-US / ex-EU rights potentially negotiable",
  dealPrecedents,
  className,
}: LicensingCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Licensing & Partnering Feasibility
          </h3>
          <p className="text-[11px] text-slate-500">{assetName}</p>
        </div>
        <span className="rounded bg-cyan-50 px-2 py-0.5 text-[10px] font-bold text-cyan-800 border border-cyan-200">
          BD & In-Licensing
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
        <div className="rounded-lg border border-slate-200 p-3 bg-slate-50/50">
          <span className="font-semibold text-slate-500">Current Rights Holder:</span>
          <div className="font-bold text-slate-900 mt-0.5">{rightsOwner}</div>
        </div>

        <div className="rounded-lg border border-slate-200 p-3 bg-slate-50/50">
          <span className="font-semibold text-slate-500">Patent Exclusivity Horizon:</span>
          <div className="font-bold text-slate-900 mt-0.5">{patentWindow}</div>
        </div>
      </div>

      <div className="rounded-lg border border-cyan-100 bg-cyan-50/30 p-3 text-xs">
        <span className="font-bold text-cyan-900">Partnering Assessment:</span>
        <p className="mt-1 text-slate-700 leading-relaxed">{feasibility}</p>
      </div>

      <div className="text-[11px] text-slate-600 space-y-1">
        <div>
          <strong>Territory Structure:</strong> {territoryAvailability}
        </div>
        {dealPrecedents && (
          <div>
            <strong>Comparable Deals:</strong> {dealPrecedents}
          </div>
        )}
      </div>
    </div>
  );
}

// ==========================================
// 3. CommercialOpportunityCard
// ==========================================
export interface CommercialOpportunityCardProps {
  assetName: string;
  opportunitySummary: string;
  targetIndication: string;
  peakSalesEst?: string;
  targetPatientPop?: string;
  differentiationEdge: string;
  className?: string;
}

export function CommercialOpportunityCard({
  assetName,
  opportunitySummary,
  targetIndication,
  peakSalesEst = "$1.5B - $3.0B Global Peak Sales",
  targetPatientPop = "~15,000 - 25,000 addressable metastatic patients/year",
  differentiationEdge,
  className,
}: CommercialOpportunityCardProps) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-3.5",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
            Commercial Opportunity & Market Size
          </h3>
          <p className="text-[11px] text-slate-500">{assetName}</p>
        </div>
        <span className="rounded bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-800 border border-emerald-200">
          Market Intelligence
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
        <div className="rounded-lg border border-slate-200 p-3 bg-slate-50">
          <span className="font-semibold text-slate-500">Estimated Global Peak Sales</span>
          <div className="text-base font-black text-emerald-700 mt-0.5">
            {peakSalesEst}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-3 bg-slate-50">
          <span className="font-semibold text-slate-500">Addressable Annual Patients</span>
          <div className="text-base font-black text-slate-900 mt-0.5">
            {targetPatientPop}
          </div>
        </div>
      </div>

      <div className="text-xs space-y-2">
        <div>
          <span className="font-semibold text-slate-500">Target Indication Setting:</span>
          <div className="font-bold text-slate-800 mt-0.5">{targetIndication}</div>
        </div>

        <div className="rounded bg-slate-50 p-2.5 border border-slate-100">
          <span className="font-bold text-slate-800">Commercial Differentiation Edge:</span>
          <p className="mt-0.5 text-slate-700 leading-relaxed">{differentiationEdge}</p>
        </div>

        <p className="text-[11px] text-slate-600 leading-relaxed">
          {opportunitySummary}
        </p>
      </div>
    </div>
  );
}

// Canonical Aliases matching Design System requirements
export const CompetitiveLandscape = CompetitiveLandscapeCard;
export type CompetitiveLandscapeProps = CompetitiveLandscapeCardProps;

export const LicensingProfile = LicensingCard;
export type LicensingProfileProps = LicensingCardProps;
export const LicensingProfileCard = LicensingCard;

export const CommercialOpportunity = CommercialOpportunityCard;
export type CommercialOpportunityProps = CommercialOpportunityCardProps;

