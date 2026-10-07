"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

export interface HeaderProps {
  activeTab?: string;
  onTabChange?: (tab: string) => void;
  searchQuery?: string;
  onSearchChange?: (q: string) => void;
}

export function Header({
  activeTab,
  onTabChange,
  searchQuery = "",
  onSearchChange,
}: HeaderProps) {
  const pathname = usePathname();

  const tabs = [
    { id: "discover", label: "DISCOVER", href: "/discover" },
    { id: "evaluate", label: "EVALUATE", href: "/evaluate" },
    { id: "patient-match", label: "PATIENT MATCH", href: "/patient-match" },
    { id: "compare", label: "COMPARE", href: "/compare" },
    { id: "backtest", label: "BACKTEST", href: "/backtest" },
    { id: "opportunities", label: "OPPORTUNITIES", href: "/opportunities" },
  ];

  const getIsActive = (tabId: string, tabHref: string) => {
    if (activeTab) return activeTab === tabId;
    if (pathname === tabHref) return true;
    if (tabId === "discover" && (pathname === "/" || pathname === "")) return true;
    return false;
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800 bg-[#0c1322] px-6 py-2.5 text-white shadow-md">
      <div className="flex items-center justify-between gap-6">
        {/* Brand */}
        <Link href="/discover" className="flex items-center gap-3 group">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 font-bold text-white shadow-inner group-hover:bg-blue-500 transition">
            <span className="text-lg">N</span>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold tracking-tight text-white">NeoZenome</span>
            </div>
            <div className="text-[11px] font-medium tracking-wide text-slate-400">
              AI-Powered Oncology Asset Intelligence
            </div>
          </div>
        </Link>

        {/* Workflow Tabs */}
        <nav className="flex items-center space-x-1">
          {tabs.map((tab) => {
            const isActive = getIsActive(tab.id, tab.href);
            return (
              <Link
                key={tab.id}
                href={tab.href}
                onClick={() => {
                  if (onTabChange) onTabChange(tab.id);
                }}
                className={`rounded-md px-3.5 py-1.5 text-sm font-medium transition-all ${
                  isActive
                    ? "bg-blue-600 text-white shadow"
                    : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>

        {/* Search & Profile */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-slate-400">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
            </div>
            <input
              type="text"
              placeholder="Search drug, target, or indication..."
              value={searchQuery}
              onChange={(e) => onSearchChange && onSearchChange(e.target.value)}
              className="w-64 rounded-md border border-slate-700 bg-slate-900/90 py-1.5 pl-9 pr-3 text-xs text-slate-100 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div
            title="Dr. S. Kalyan - Principal Translational Oncologist"
            className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full bg-blue-700 text-xs font-semibold text-white ring-2 ring-blue-400/40 hover:bg-blue-600"
          >
            SK
          </div>
        </div>
      </div>
    </header>
  );
}
