import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchCopilotView } from "../src/components/ResearchCopilotView";

const citation = {
  evidence_id: "internal-evidence-1",
  source_reference: "PMID:12345",
  source_type: "literature",
  title: "Internal evidence title",
  citation: "Journal citation",
  url: "https://example.org/source",
  excerpt: "Stored source excerpt.",
  polarity: "SUPPORTING",
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Research Copilot workspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/api/assets") {
          return Promise.resolve(
            jsonResponse({
              assets: [{ id: "canonical-asset", name: "Asset A" }],
            }),
          );
        }
        return Promise.resolve(
          jsonResponse({
            asset_id: "canonical-asset",
            evaluation_cutoff: "2026-10-09",
            question: "What is known?",
            summary: "One sourced summary.",
            summary_classification: "FACT",
            summary_evidence_ids: [citation.evidence_id],
            claims: [
              {
                classification: "FACT",
                statement: "A source supports this result.",
                evidence_ids: [citation.evidence_id],
              },
              {
                classification: "UNKNOWN",
                statement:
                  "The context does not establish the remaining question.",
                evidence_ids: [],
              },
            ],
            citations: [citation],
            unknowns: ["A material item remains unknown."],
            contradictions: [],
          }),
        );
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the classified answer and citations returned by the API", async () => {
    render(<ResearchCopilotView />);
    fireEvent.change(await screen.findByLabelText("Canonical asset"), {
      target: { value: "canonical-asset" },
    });
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "What is known?" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Ask with internal evidence" }),
    );

    expect(await screen.findByText("One sourced summary.")).toBeTruthy();
    expect(screen.getAllByText("FACT").length).toBeGreaterThan(0);
    expect(screen.getByText("UNKNOWN")).toBeTruthy();
    expect(screen.getAllByText(/PMID:12345/).length).toBeGreaterThan(0);
    expect(screen.getByText("A material item remains unknown.")).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.map(([url]) => String(url))).toContain(
      "/api/research/copilot",
    );
  });

  it("shows provider errors instead of a simulated answer", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/assets") {
        return Promise.resolve(
          jsonResponse({
            assets: [{ id: "canonical-asset", name: "Asset A" }],
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(
          { detail: "Research Copilot provider is not configured." },
          503,
        ),
      );
    });
    render(<ResearchCopilotView />);
    fireEvent.change(await screen.findByLabelText("Canonical asset"), {
      target: { value: "canonical-asset" },
    });
    fireEvent.change(screen.getByLabelText("Research question"), {
      target: { value: "What is known?" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Ask with internal evidence" }),
    );

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Research Copilot provider is not configured.",
    );
    expect(screen.queryByRole("heading", { name: "Answer" })).toBeNull();
  });
});
