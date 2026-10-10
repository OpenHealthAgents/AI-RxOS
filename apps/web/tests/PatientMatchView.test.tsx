import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PatientMatchView } from "../src/components/PatientMatchView";

const scenario = {
  query: {},
  best_matched_asset: {},
  ranked_candidates: [
    {
      asset_id: "asset-a",
      asset_name: "Asset A",
      match_score: 72,
      rank: 1,
      population_fit: "Cohort reported by the backend.",
      mechanistic_synergy: "Mechanistic rationale from API.",
      evidence_citations: ["PMID:123"],
    },
  ],
  interpretation: "Backend cohort interpretation.",
  disclaimer: "Population intelligence only.",
  evaluated_at: "2026-10-09T00:00:00Z",
};

const intelligence = {
  status: "AVAILABLE",
  data: {
    primary_population: {
      value: "API population",
      status: "AVAILABLE",
      epistemic_class: "ML_PREDICTION",
      confidence: 0.75,
      supporting_evidence: [{ citation: "PMID:123" }],
      provenance: { source: "population profile" },
      reason: null,
    },
    secondary_population: {
      value: "Secondary API population",
      status: "UNKNOWN",
      epistemic_class: "UNKNOWN",
      confidence: null,
      reason: "No secondary population was established.",
    },
    low_likelihood_population: {
      value: null,
      status: "INSUFFICIENT_EVIDENCE",
      epistemic_class: "UNKNOWN",
      confidence: null,
    },
    biomarker_strategy: {
      value: "API biomarker strategy",
      status: "AVAILABLE",
      epistemic_class: "FACT",
      confidence: 0.6,
    },
    patient_match_score: {
      value: 72,
      status: "AVAILABLE",
      epistemic_class: "DERIVED_FEATURE",
      confidence: 0.75,
    },
    confidence: { value: 0.75, status: "AVAILABLE" },
    evidence: [{ source_reference: "source:456" }],
    unknowns: ["API-reported uncertainty."],
    epistemic_classes: ["FACT", "ML_PREDICTION", "UNKNOWN"],
    ml_component: {
      available: true,
      model_name: "patient-model",
      model_version: "v2",
      feature_version: "f3",
    },
  },
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PatientMatch workspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === "/api/patient-match/scenario") {
          return Promise.resolve(jsonResponse(scenario));
        }
        if (String(input) === "/api/patient-match/intelligence/asset-a") {
          return Promise.resolve(jsonResponse(intelligence));
        }
        return Promise.resolve(new Response("not found", { status: 404 }));
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("sends cohort filters and renders backend populations, confidence, evidence and prediction state", async () => {
    render(<PatientMatchView />);
    fireEvent.change(screen.getByLabelText("Disease / subtype"), {
      target: { value: "Disease subtype X" },
    });
    fireEvent.change(screen.getByLabelText("Mutation"), {
      target: { value: "Mutation X" },
    });
    fireEvent.change(screen.getByLabelText("Biomarker"), {
      target: { value: "Marker X" },
    });
    fireEvent.change(
      screen.getByLabelText("Prior treatment(s), comma-separated"),
      { target: { value: "Drug A, Drug B" } },
    );
    fireEvent.change(screen.getByLabelText("Line of therapy"), {
      target: { value: "2L" },
    });
    fireEvent.change(screen.getByLabelText("Resistance state"), {
      target: { value: "State X" },
    });
    fireEvent.change(screen.getByLabelText("CNS status"), {
      target: { value: "Active" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rank populations" }));

    expect(await screen.findByText("API population")).toBeTruthy();
    expect(
      screen.getByText(
        /fixed benchmark asset set with deterministic keyword rules/i,
      ),
    ).toBeTruthy();
    expect(
      screen.getByText("Backend rule-based benchmark rank #1"),
    ).toBeTruthy();
    expect(screen.getByText(/API heuristic cohort match score:/)).toBeTruthy();
    expect(
      screen.getByText("Primary population state:").parentElement?.textContent,
    ).toContain("PREDICTED (API: ML_PREDICTION)");
    expect(
      screen.getByText("API match score state:").parentElement?.textContent,
    ).toContain("DERIVED (API: DERIVED_FEATURE)");
    expect(screen.getAllByText("75%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("PMID:123").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Primary population provenance:").parentElement
        ?.textContent,
    ).toContain("population profile");
    expect(
      screen.getByText("Model feature version:").parentElement?.textContent,
    ).toContain("f3");
    expect(screen.getByText("source:456")).toBeTruthy();
    expect(
      screen.getByText("Population intelligence state:").parentElement
        ?.textContent,
    ).toContain("AVAILABLE");
    expect(
      screen.getByText("Model state:").parentElement?.textContent,
    ).toContain("AVAILABLE");
    expect(screen.getByText(/patient-model \/ v2/)).toBeTruthy();
    expect(screen.getByText(/Secondary API population/)).toBeTruthy();
    expect(screen.getByText(/INSUFFICIENT_EVIDENCE/)).toBeTruthy();
    expect(screen.getByText(/API biomarker strategy/)).toBeTruthy();
    expect(screen.getByText("API-reported uncertainty.")).toBeTruthy();
    expect(
      screen.getByText(/Not returned by the PatientMatch intelligence API/),
    ).toBeTruthy();
    expect(screen.getByText(/not separate matching inputs/)).toBeTruthy();
    await waitFor(() => {
      const post = vi
        .mocked(fetch)
        .mock.calls.find(
          ([url]) => String(url) === "/api/patient-match/scenario",
        );
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        disease_subtype: "Disease subtype X",
        mutation: "Mutation X",
        biomarker: "Marker X",
        prior_therapy: ["Drug A", "Drug B"],
        line_of_therapy: "2L",
        resistance_state: "State X",
        cns_status: "Active",
      });
    });
  });

  it("does not invent a patient population when the backend returns no candidates", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/patient-match/scenario") {
        return Promise.resolve(
          jsonResponse({ ...scenario, ranked_candidates: [] }),
        );
      }
      return Promise.resolve(new Response("not found", { status: 404 }));
    });
    render(<PatientMatchView />);
    fireEvent.change(screen.getByLabelText("Biomarker"), {
      target: { value: "Marker X" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rank populations" }));

    expect(
      await screen.findByText(
        "No populations were returned by the backend for this cohort.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Asset A")).toBeNull();
  });

  it("does not coerce malformed confidence strings into percentages", async () => {
    const malformedConfidence = {
      ...intelligence,
      data: {
        ...intelligence.data,
        confidence: { value: "0.75", status: "AVAILABLE" },
      },
    };
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/patient-match/scenario")
        return Promise.resolve(jsonResponse(scenario));
      if (String(input) === "/api/patient-match/intelligence/asset-a")
        return Promise.resolve(jsonResponse(malformedConfidence));
      return Promise.resolve(new Response("not found", { status: 404 }));
    });
    render(<PatientMatchView />);
    fireEvent.change(screen.getByLabelText("Biomarker"), {
      target: { value: "Marker X" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rank populations" }));
    await screen.findByText("API population");
    expect(
      screen.getByText("Intelligence confidence:").parentElement?.textContent,
    ).toContain("UNKNOWN");
  });
});
