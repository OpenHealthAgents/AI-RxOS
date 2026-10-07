"use client";

import React from "react";
import { useRouter, usePathname } from "next/navigation";

export interface SidebarProps {
  activeSection: string;
  onSelectSection: (section: string) => void;
  onOpenEvidenceModal: () => void;
}

export function Sidebar({
  activeSection,
  onSelectSection,
  onOpenEvidenceModal,
}: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();

  const navItems = [
    { id: "overview", label: "ASSET OVERVIEW", icon: "squares" },
    { id: "compare", label: "COMPARE ASSETS", icon: "columns" },
    { id: "biology", label: "BIOLOGY & MOA", icon: "dna" },
    { id: "preclinical", label: "PRECLINICAL EVIDENCE", icon: "beaker" },
    { id: "clinical", label: "CLINICAL DEVELOPMENT", icon: "activity" },
    { id: "patient-match", label: "PATIENT MATCH", icon: "users" },
    { id: "safety", label: "SAFETY & TOXICITY", icon: "shield" },
    { id: "resistance", label: "RESISTANCE & COMBINATIONS", icon: "refresh" },
    { id: "landscape", label: "COMPETITIVE LANDSCAPE", icon: "chart" },
    { id: "regulatory", label: "REGULATORY & IP", icon: "document" },
    { id: "evidence", label: "EVIDENCE & SOURCES", icon: "book" },
  ];

  const handleItemClick = (id: string) => {
    if (id === "evidence") {
      if (pathname !== "/evaluate") {
        router.push("/evaluate?section=evidence");
      }
      onSelectSection("evidence");
      onOpenEvidenceModal();
      return;
    }

    if (pathname !== "/evaluate") {
      router.push(`/evaluate?section=${id}`);
    }
    onSelectSection(id);
  };

  const renderIcon = (type: string) => {
    switch (type) {
      case "squares":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        );
      case "columns":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
          </svg>
        );
      case "dna":
      case "beaker":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
        );
      case "activity":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        );
      case "users":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        );
      case "shield":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        );
      case "refresh":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        );
      case "chart":
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
          </svg>
        );
      case "document":
      case "book":
      default:
        return (
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        );
    }
  };

  return (
    <aside className="w-56 shrink-0 border-r border-slate-200 bg-white py-4 shadow-sm flex flex-col justify-between">
      <div>
        <div className="px-3 pb-2 mb-2 border-b border-slate-100">
          <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Evaluation Workspace
          </div>
          <div className="text-[11px] font-semibold text-slate-700">
            11-Section Dossier
          </div>
        </div>

        <div className="space-y-0.5 px-3">
          {navItems.map((item) => {
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleItemClick(item.id)}
                className={`flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-left text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-blue-50 font-semibold text-blue-700 ring-1 ring-blue-200"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <span className={isActive ? "text-blue-600" : "text-slate-400"}>
                  {renderIcon(item.icon)}
                </span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Provenance Audit Tag */}
      <div className="px-4 pt-3 border-t border-slate-100 text-[10px] text-slate-400">
        <div>NeoZenome Engine v2.4</div>
        <div className="text-slate-500 font-medium">Zero-Leakage Temporal Audit</div>
      </div>
    </aside>
  );
}
