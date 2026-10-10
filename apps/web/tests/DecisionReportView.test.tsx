import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildDecisionReportMarkdown,
  DecisionReportView,
} from "../src/components/DecisionReportView";

const titles = [
  "Executive Summary",
  "Asset Overview",
  "Biology",
  "Preclinical",
  "Clinical",
  "CNS",
  "Patient Match",
  "Safety",
  "Resistance",
  "Combination",
  "Competition",
  "Regulatory",
  "IP",
  "Licensing",
  "Commercial",
  "Recommendation",
  "WHY",
  "Contradictory Evidence",
  "Unknowns",
  "Next Actions",
];

const sectionIds = [
  "executive_summary",
  "asset_overview",
  "biology",
  "preclinical",
  "clinical",
  "cns",
  "patient_match",
  "safety",
  "resistance",
  "combination",
  "competition",
  "regulatory",
  "ip",
  "licensing",
  "commercial",
  "recommendation",
  "why",
  "contradictory_evidence",
  "unknowns",
  "next_actions",
];

const citation = {
  evidence_id: "internal-evidence-1",
  source_reference: "PMID:54321",
  source_type: "literature",
  title: "Report source",
  citation: "Journal reference",
  url: "https://example.org/report-source",
  excerpt: "Report source excerpt.",
  polarity: "SUPPORTING",
};

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Decision Report workspace", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders all report sections, unknown states, provenance and citations", async () => {
    const sections = titles.map((title, index) => ({
      section_id: sectionIds[index],
      title,
      status: title === "Preclinical" ? "UNKNOWN" : "AVAILABLE",
      source_data:
        title === "Preclinical" ? null : { returned_by: "existing API" },
      claims: [],
      evidence_ids: title === "Biology" ? [citation.evidence_id] : [],
      unknowns:
        title === "Preclinical" ? ["No distinct preclinical profile."] : [],
      contradictory_evidence_ids: [],
    }));
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === "/api/assets") {
          return Promise.resolve(
            jsonResponse({ assets: [{ id: "asset-a", name: "Asset A" }] }),
          );
        }
        return Promise.resolve(
          jsonResponse({
            asset_id: "asset-a",
            asset_name: "Asset A",
            tenant_id: "trusted-tenant",
            evaluation_cutoff: "2026-10-09",
            sections,
            citations: [citation],
          }),
        );
      }),
    );

    render(<DecisionReportView />);
    fireEvent.change(await screen.findByLabelText("Canonical asset"), {
      target: { value: "asset-a" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Load current report" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Executive Summary" }),
    ).toBeTruthy();
    for (const title of titles.slice(1)) {
      expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    }
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
    expect(screen.getByText(/No distinct preclinical profile/)).toBeTruthy();
    expect(screen.getAllByText(/PMID:54321/).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Download Markdown" }),
    ).toBeTruthy();
  }, 15000);

  it("preserves epistemic classes, unknowns, and citation references in Markdown", () => {
    const output = buildDecisionReportMarkdown({
      asset_id: "asset-a",
      asset_name: "Asset A",
      tenant_id: null,
      evaluation_cutoff: "2026-10-09",
      citations: [citation],
      sections: [
        {
          section_id: "executive_summary",
          title: "Executive Summary",
          status: "AVAILABLE",
          source_data: { decision: "PURSUE" },
          claims: [
            {
              classification: "INFERENCE",
              statement: "This is an existing engine output.",
              evidence_ids: [citation.evidence_id],
            },
          ],
          evidence_ids: [citation.evidence_id],
          unknowns: ["A material value is unknown."],
          contradictory_evidence_ids: [],
        },
      ],
    });

    expect(output).toContain(
      "**INFERENCE:** This is an existing engine output.",
    );
    expect(output).toContain(`[${citation.evidence_id}]`);
    expect(output).toContain("A material value is unknown.");
    expect(output).toContain("PMID:54321");
  });
});
