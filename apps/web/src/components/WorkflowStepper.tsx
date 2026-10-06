"use client";

import React from "react";
import { useWorkspace, WORKFLOW_STEPS, WorkflowStepId } from "../context/WorkspaceContext";

export function WorkflowStepper() {
  const {
    currentWorkflowStep,
    setCurrentWorkflowStep,
    setIsEvidenceModalOpen,
    setIsResolutionModalOpen,
    setIsHumanDecisionModalOpen,
  } = useWorkspace();

  const handleStepClick = (stepId: WorkflowStepId) => {
    setCurrentWorkflowStep(stepId);
    if (stepId === "canonical-resolution") {
      setIsResolutionModalOpen(true);
    } else if (stepId === "evidence-inspection") {
      setIsEvidenceModalOpen(true);
    } else if (stepId === "human-decision") {
      setIsHumanDecisionModalOpen(true);
    }
  };

  const getStepStatus = (index: number) => {
    const currentIndex = WORKFLOW_STEPS.findIndex((s) => s.id === currentWorkflowStep);
    if (index < currentIndex) return "completed";
    if (index === currentIndex) return "active";
    return "pending";
  };

  return (
    <div className="w-full border-b border-slate-200 bg-white px-6 py-2 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        {/* Stepper Title & Subtitle */}
        <div className="hidden xl:flex flex-col shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] font-bold uppercase tracking-wider text-slate-700">
              Evidence-Grounded Decision Pipeline
            </span>
          </div>
          <span className="text-[10px] text-slate-400">
            End-to-end provenance & human oversight
          </span>
        </div>

        {/* Stepper Pipeline */}
        <div className="flex flex-1 items-center justify-between overflow-x-auto py-1 scrollbar-none">
          {WORKFLOW_STEPS.map((step, idx) => {
            const status = getStepStatus(idx);
            const isSelected = currentWorkflowStep === step.id;

            return (
              <React.Fragment key={step.id}>
                {/* Step Item */}
                <button
                  type="button"
                  onClick={() => handleStepClick(step.id)}
                  title={`${step.number}. ${step.label} — ${step.description}`}
                  className={`group flex items-center gap-1.5 rounded-full px-2.5 py-1 text-left transition-all ${
                    isSelected
                      ? "bg-blue-600 text-white shadow-sm ring-2 ring-blue-300"
                      : status === "completed"
                      ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      : "bg-slate-50 text-slate-400 hover:bg-slate-100"
                  }`}
                >
                  <span
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${
                      isSelected
                        ? "bg-white text-blue-700"
                        : status === "completed"
                        ? "bg-emerald-600 text-white"
                        : "bg-slate-300 text-slate-700"
                    }`}
                  >
                    {status === "completed" ? "✓" : step.number}
                  </span>
                  <span
                    className={`text-[11px] font-semibold whitespace-nowrap ${
                      isSelected
                        ? "text-white"
                        : status === "completed"
                        ? "text-slate-700 group-hover:text-slate-900"
                        : "text-slate-500"
                    }`}
                  >
                    {step.shortLabel}
                  </span>
                </button>

                {/* Pipeline Arrow Connector */}
                {idx < WORKFLOW_STEPS.length - 1 && (
                  <span
                    className={`mx-1 text-[11px] font-light ${
                      status === "completed" ? "text-emerald-500 font-medium" : "text-slate-300"
                    }`}
                  >
                    →
                  </span>
                )}
              </React.Fragment>
            );
          })}
        </div>

        {/* Quick Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setIsResolutionModalOpen(true)}
            className="flex items-center gap-1 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-medium text-slate-600 hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700 transition"
          >
            <svg className="h-3.5 w-3.5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <span>Resolve Asset</span>
          </button>

          <button
            onClick={() => setIsHumanDecisionModalOpen(true)}
            className="flex items-center gap-1 rounded bg-slate-800 px-2.5 py-1 text-[11px] font-semibold text-white hover:bg-slate-700 shadow-sm transition"
          >
            <svg className="h-3.5 w-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>Human Sign-Off</span>
          </button>
        </div>
      </div>
    </div>
  );
}
