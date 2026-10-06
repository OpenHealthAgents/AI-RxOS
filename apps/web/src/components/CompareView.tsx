"use client";

import React, { useState } from "react";
import { AssetIntelligence } from "../lib/types";
import {
  AssetHeader,
  DecisionBanner,
  ScoreGauge,
  RadarProfile,
  KeyAttributesTable,
  ResistanceCard,
  CombinationCard,
  SafetyProfileCard,
  PatientMatchCard,
  CompetitiveLandscapeCard,
} from "@ai-rxos/ui";
import { StageTransitionBars } from "./StageTransitionBars";
import { ExportModal } from "./ExportModal";

export interface CompareViewProps {
  asset1: AssetIntelligence;
  asset2: AssetIntelligence;
  allAssets: AssetIntelligence[];
  onSelectAsset1: (asset: AssetIntelligence) => void;
  onSelectAsset2: (asset: AssetIntelligence) => void;
  onOpenEvidenceModal: () => void;
}

export function CompareView({
  asset1,
  asset2,
  allAssets,
  onSelectAsset1,
  onSelectAsset2,
  onOpenEvidenceModal,
}: CompareViewProps) {
  const [target, setTarget] = useState("HER2");
  const [indication, setIndication] = useState("Breast Cancer");
  const [setting, setSetting] = useState("Metastatic");
  const [isExportOpen, setIsExportOpen] = useState(false);

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-6 py-4 text-slate-800">
      {/* Top Breadcrumb & Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-3 border-b border-slate-200">
        <div>
          <div className="text-[11px] font-medium text-slate-500">
            Compare Assets &gt; <span className="text-blue-600 font-semibold">{target} Target</span> &gt; {asset1.name} vs {asset2.name}
          </div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900 mt-0.5">
            {asset1.name} vs {asset2.name}{" "}
            <span className="text-sm font-normal text-slate-500">
              {target} Tyrosine Kinase Inhibitors (TKIs)
            </span>
          </h1>
        </div>

        {/* Dropdown Filters & Export */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <div className="flex items-center gap-1.5 bg-white border border-slate-300 rounded px-2.5 py-1 shadow-2xs">
            <span className="text-slate-400 font-medium">Target</span>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="bg-transparent font-semibold text-slate-700 outline-none cursor-pointer"
            >
              <option value="HER2">HER2</option>
              <option value="EGFR">EGFR</option>
              <option value="KRAS">KRAS</option>
              <option value="CDK4/6">CDK4/6</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-white border border-slate-300 rounded px-2.5 py-1 shadow-2xs">
            <span className="text-slate-400 font-medium">Indication</span>
            <select
              value={indication}
              onChange={(e) => setIndication(e.target.value)}
              className="bg-transparent font-semibold text-slate-700 outline-none cursor-pointer"
            >
              <option value="Breast Cancer">Breast Cancer</option>
              <option value="NSCLC">NSCLC</option>
              <option value="Colorectal">Colorectal</option>
              <option value="Gastric">Gastric</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 bg-white border border-slate-300 rounded px-2.5 py-1 shadow-2xs">
            <span className="text-slate-400 font-medium">Setting</span>
            <select
              value={setting}
              onChange={(e) => setSetting(e.target.value)}
              className="bg-transparent font-semibold text-slate-700 outline-none cursor-pointer"
            >
              <option value="Metastatic">Metastatic</option>
              <option value="Extended Adjuvant">Extended Adjuvant</option>
              <option value="Adjuvant">Adjuvant</option>
              <option value="Neoadjuvant">Neoadjuvant</option>
            </select>
          </div>

          <button
            onClick={() => setIsExportOpen(true)}
            className="flex items-center gap-1.5 rounded border border-blue-600 bg-white px-3 py-1 font-semibold text-blue-700 hover:bg-blue-50 transition-colors shadow-sm"
          >
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Export Comparison
          </button>
        </div>
      </div>

      {/* Asset Overview Cards with Selectors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        {/* Left: Asset 1 (Zongertinib) */}
        <div className="space-y-3">
          <div className="relative">
            <AssetHeader asset={asset1} themeColor="blue" />
            <div className="absolute top-4 right-4">
              <select
                value={asset1.id}
                onChange={(e) => {
                  const found = allAssets.find((a) => a.id === e.target.value);
                  if (found) onSelectAsset1(found);
                }}
                className="text-[11px] rounded border border-slate-200 bg-slate-50 py-1 px-1.5 text-slate-700 font-medium outline-none cursor-pointer hover:bg-white"
              >
                {allAssets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Decision Banner Asset 1 */}
          <DecisionBanner
            action={asset1.recommendation.action}
            title={asset1.recommendation.badge_text}
            rationale={asset1.recommendation.rationale}
            theme={asset1.recommendation.action === "PURSUE" ? "green" : "blue"}
          />
        </div>

        {/* Right: Asset 2 (Neratinib) */}
        <div className="space-y-3">
          <div className="relative">
            <AssetHeader asset={asset2} themeColor="orange" />
            <div className="absolute top-4 right-4">
              <select
                value={asset2.id}
                onChange={(e) => {
                  const found = allAssets.find((a) => a.id === e.target.value);
                  if (found) onSelectAsset2(found);
                }}
                className="text-[11px] rounded border border-slate-200 bg-slate-50 py-1 px-1.5 text-slate-700 font-medium outline-none cursor-pointer hover:bg-white"
              >
                {allAssets.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Decision Banner Asset 2 */}
          <DecisionBanner
            action={asset2.recommendation.action}
            title={asset2.recommendation.badge_text}
            rationale={asset2.recommendation.rationale}
            theme={asset2.recommendation.action === "AVOID" ? "rose" : "amber"}
          />
        </div>
      </div>

      {/* Middle Row: Gauges, Radar, Transitions */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
        {/* Development Potential Meter */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col justify-between">
          <div>
            <div className="border-b border-slate-100 pb-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
                Development Potential
              </h3>
              <p className="text-[11px] text-slate-400">Preclinical → Approval likelihood</p>
            </div>

            <div className="flex items-center justify-around py-4">
              <ScoreGauge
                score={asset1.recommendation.development_potential_score}
                name={asset1.name}
                tier={asset1.recommendation.development_potential_tier}
                colorTheme="emerald"
                showLegend={false}
              />
              <ScoreGauge
                score={asset2.recommendation.development_potential_score}
                name={asset2.name}
                tier={asset2.recommendation.development_potential_tier}
                colorTheme="amber"
                showLegend={false}
              />
            </div>
          </div>

          <div className="flex items-center justify-center gap-2 pt-2 border-t border-slate-100 text-[9px] text-slate-500 font-medium">
            <span className="inline-flex items-center gap-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-rose-500" /> Very Low
            </span>
            <span className="inline-flex items-center gap-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" /> Low
            </span>
            <span className="inline-flex items-center gap-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-yellow-400" /> Moderate
            </span>
            <span className="inline-flex items-center gap-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> High
            </span>
            <span className="inline-flex items-center gap-0.5">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-600" /> Very High
            </span>
          </div>
        </div>

        {/* Multi-Dimensional Biology Radar Profile */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col justify-between">
          <div className="border-b border-slate-100 pb-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-800">
              Biology Profile (Multi-Dimensional)
            </h3>
            <p className="text-[11px] text-slate-400">6-axis pharmacological properties</p>
          </div>

          <div className="flex items-center justify-center py-1">
            <RadarProfile
              asset1Name={asset1.name}
              asset1Metrics={asset1.biology_profile}
              asset2Name={asset2.name}
              asset2Metrics={asset2.biology_profile}
              size={240}
            />
          </div>

          <div className="text-[10px] text-center text-slate-400">
            Selectivity, potency & CNS barrier penetration
          </div>
        </div>

        {/* Bayesian Stage Transitions */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm flex flex-col justify-between">
          <StageTransitionBars
            name1={asset1.name}
            transitions1={asset1.stage_transitions}
            name2={asset2.name}
            transitions2={asset2.stage_transitions}
          />
        </div>
      </div>

      {/* Row: Key Attributes Table & Resistance/Combinations Card */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        {/* Key Attributes Comparison Table */}
        <KeyAttributesTable asset1={asset1} asset2={asset2} />

        {/* Resistance & Combinations Split Cards */}
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <ResistanceCard
              mechanisms={asset1.resistance_mechanisms}
              assetName={asset1.name}
            />
            <ResistanceCard
              mechanisms={asset2.resistance_mechanisms}
              assetName={asset2.name}
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <CombinationCard
              combinations={asset1.combinations}
              assetName={asset1.name}
            />
            <CombinationCard
              combinations={asset2.combinations}
              assetName={asset2.name}
            />
          </div>
        </div>
      </div>

      {/* Bottom Row: Safety, Patient Match, Business Landscape */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4 pb-8">
        <SafetyProfileCard
          safety1={asset1.safety_profile}
          name1={asset1.name}
          safety2={asset2.safety_profile}
          name2={asset2.name}
        />

        <PatientMatchCard
          profile1={asset1.patient_match}
          name1={asset1.name}
          profile2={asset2.patient_match}
          name2={asset2.name}
        />

        <CompetitiveLandscapeCard
          business1={asset1.business_profile}
          name1={asset1.name}
          action1={asset1.recommendation.action}
          business2={asset2.business_profile}
          name2={asset2.name}
          action2={asset2.recommendation.action}
        />
      </div>

      {/* Export Modal */}
      <ExportModal
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        asset1={asset1}
        asset2={asset2}
        target={target}
        indication={indication}
        setting={setting}
      />
    </div>
  );
}
