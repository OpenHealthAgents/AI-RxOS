import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BacktestView } from "../src/components/BacktestView";

const response = {
  cutoff: "2020-01-01",
  evaluation_window_end: "2021-01-01",
  outcome_type: "trial_readout",
  candidates: [
    {
      asset_id: "asset-a",
      asset_name: "Asset A",
      prediction: {
        status: "AVAILABLE",
        prediction_type: "MODEL_PREDICTED",
        predicted_value: 0.8,
        predicted_class: 1,
        confidence: 0.91,
        prediction_cutoff: "2020-01-01",
        model_name: "response-model",
        model_version: "v2",
        feature_version: "f3",
        feature_lineage: [
          {
            feature_name: "x",
            observation_date: "2019-12-20",
            evidence_references: ["known-ref"],
          },
        ],
        provenance: { snapshot: "point-in-time" },
      },
      observed_outcomes: [
        {
          status: "AVAILABLE",
          epistemic_class: "OBSERVED",
          headline: "Later outcome",
          event_date: "2020-06-01",
          publicly_known_date: "2020-06-10",
          source: "Later source",
          evidence_references: ["later-ref"],
        },
      ],
      prediction_outcome: {
        status: "COMPARABLE",
        outcome_value: 1,
        outcome_observed_date: "2020-06-01",
        outcome_evidence_references: ["later-ref"],
        reason: "Comparable outcome",
      },
      sensitivity_analysis: {
        status: "AVAILABLE",
        analysis_type: "HYPOTHETICAL_THRESHOLD_SENSITIVITY",
        decision_threshold: 0.5,
        hypothetical_class: 1,
        differs_from_stored_class: false,
        interpretation: "Sensitivity only.",
      },
    },
  ],
  metrics: {
    label_status: "INSUFFICIENT_LABELS",
    label_count: 1,
    minimum_required_labels: 5,
    metrics: [
      {
        metric: "precision",
        status: "INSUFFICIENT_LABELS",
        value: null,
        sample_count: 1,
      },
    ],
  },
  ranking: {
    status: "INSUFFICIENT_HISTORY",
    ranked_assets: [],
    top_k: 5,
    reason: "Insufficient history.",
  },
  enrichment: {
    status: "INSUFFICIENT_DATA",
    enrichment: null,
    reason: "Insufficient labels.",
  },
  calibration: {
    status: "INSUFFICIENT_LABELS",
    sample_count: 1,
    brier_score: null,
  },
  counterfactual_status: "HYPOTHETICAL_SENSITIVITY_ONLY",
  unknowns: ["Insufficient historical labels."],
  limitations: ["Outcome labels are sparse."],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Backtest workspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === "/api/assets")
          return Promise.resolve(
            jsonResponse({ assets: [{ id: "asset-a", name: "Asset A" }] }),
          );
        if (String(input) === "/api/backtest")
          return Promise.resolve(jsonResponse(response));
        return Promise.resolve(new Response("not found", { status: 404 }));
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("submits the cutoff and separates cutoff knowledge from later outcomes and hypothetical sensitivity", async () => {
    render(<BacktestView />);
    expect(
      screen.getByText(/fixture-backed asset catalog and seeded temporal/),
    ).toBeTruthy();
    await screen.findByLabelText(/Asset A/);
    fireEvent.change(screen.getByLabelText("Prediction cutoff"), {
      target: { value: "2020-01-01" },
    });
    fireEvent.change(screen.getByLabelText("Model name (optional)"), {
      target: { value: "response-model" },
    });
    fireEvent.change(screen.getByLabelText("Model version (optional)"), {
      target: { value: "v2" },
    });
    fireEvent.change(screen.getByLabelText("Outcome type (optional)"), {
      target: { value: "trial_readout" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run backtest" }));

    expect(await screen.findByText("KNOWN AT CUTOFF")).toBeTruthy();
    expect(screen.getByText("LEARNED LATER")).toBeTruthy();
    expect(
      screen.getByText("Outcome type:").parentElement?.textContent,
    ).toContain("trial_readout");
    expect(
      screen.getByText("HYPOTHETICAL — SENSITIVITY ANALYSIS"),
    ).toBeTruthy();
    expect(screen.getByText("0.8")).toBeTruthy();
    expect(screen.getByText("Later outcome")).toBeTruthy();
    expect(screen.getAllByText("INSUFFICIENT_LABELS").length).toBeGreaterThan(
      0,
    );
    expect(screen.getByText("NOT RETURNED BY API")).toBeTruthy();
    await waitFor(() => {
      const post = vi
        .mocked(fetch)
        .mock.calls.find(([url]) => String(url) === "/api/backtest");
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
        asset_ids: ["asset-a"],
        cutoff: "2020-01-01",
        outcome_type: "trial_readout",
        model_name: "response-model",
        model_version: "v2",
        top_k: 5,
        decision_threshold: 0.5,
      });
    });
  });

  it("does not coerce malformed API confidence strings into percentages", async () => {
    const candidate = response.candidates[0];
    if (!candidate) throw new Error("Expected a backtest candidate fixture.");
    const malformedConfidence = {
      ...response,
      candidates: [
        {
          ...candidate,
          prediction: {
            ...candidate.prediction,
            confidence: "0.91",
          },
        },
      ],
    };
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/assets")
        return Promise.resolve(
          jsonResponse({ assets: [{ id: "asset-a", name: "Asset A" }] }),
        );
      return Promise.resolve(jsonResponse(malformedConfidence));
    });
    render(<BacktestView />);
    await screen.findByLabelText(/Asset A/);
    fireEvent.change(screen.getByLabelText("Prediction cutoff"), {
      target: { value: "2020-01-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run backtest" }));
    await screen.findByText("KNOWN AT CUTOFF");
    expect(
      screen.getByText("Confidence:").parentElement?.textContent,
    ).toContain("UNKNOWN");
  });

  it("surfaces API failures", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/assets")
        return Promise.resolve(
          jsonResponse({ assets: [{ id: "asset-a", name: "Asset A" }] }),
        );
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "Backtest unavailable." }), {
          status: 503,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
    render(<BacktestView />);
    await screen.findByLabelText(/Asset A/);
    fireEvent.change(screen.getByLabelText("Prediction cutoff"), {
      target: { value: "2020-01-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run backtest" }));
    expect(await screen.findByText("Backtest unavailable.")).toBeTruthy();
  });
});
