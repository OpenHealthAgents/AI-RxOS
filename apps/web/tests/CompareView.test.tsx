import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CompareView } from "../src/components/CompareView";

const assets = [
  { id: "asset-a", name: "Asset A", target: "TARGET-A", stage: "PHASE_I" },
  { id: "asset-b", name: "Asset B", target: "TARGET-B", stage: "PHASE_II" },
  { id: "asset-c", name: "Asset C", target: "TARGET-C", stage: "PHASE_III" },
];

const response = {
  evaluation_cutoff: "2026-10-09",
  asset_ids: ["asset-a", "asset-b", "asset-c"],
  dimensions: [
    {
      dimension: "cns",
      comparison_metric: "measured_cns_activity",
      normalized_comparison: [
        {
          asset_id: "asset-a",
          metrics: [
            {
              metric: "measured_cns_activity",
              status: "AVAILABLE",
              raw_value: "Observed activity",
              confidence: 0.8,
              epistemic_class: "FACT",
              supporting_evidence: [{ citation: "PMID:123" }],
              provenance: { source: "API" },
              source_output: {},
              unknowns: [],
              rationale: "Evidence attached.",
            },
          ],
        },
        {
          asset_id: "asset-b",
          metrics: [
            {
              metric: "measured_cns_activity",
              status: "UNKNOWN",
              raw_value: null,
              confidence: null,
              epistemic_class: "UNKNOWN",
              supporting_evidence: [],
              provenance: {},
              source_output: {},
              unknowns: ["No measured CNS evidence."],
              rationale: null,
            },
          ],
        },
        {
          asset_id: "asset-c",
          metrics: [
            {
              metric: "measured_cns_activity",
              status: "INSUFFICIENT_EVIDENCE",
              raw_value: null,
              confidence: null,
              epistemic_class: "UNKNOWN",
              supporting_evidence: [],
              provenance: {},
              source_output: {},
              unknowns: ["Insufficient evidence."],
              rationale: null,
            },
          ],
        },
      ],
      winner_asset_id: null,
      winner_status: "NOT_COMPARABLE",
      confidence: null,
      supporting_evidence: [],
      contradictory_evidence: [],
      unknowns: ["Evidence is asymmetric."],
      explanation: "The backend does not identify a winner.",
      differentiator: null,
    },
  ],
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Compare workspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        if (String(input) === "/api/assets") {
          return Promise.resolve(jsonResponse({ assets }));
        }
        if (String(input) === "/api/compare") {
          return Promise.resolve(jsonResponse(response));
        }
        return Promise.resolve(new Response("not found", { status: 404 }));
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("compares two assets and preserves evidence asymmetry, unknowns and backend outcomes", async () => {
    render(<CompareView />);
    await screen.findByText("Asset A · TARGET-A · PHASE_I");
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    expect(
      await screen.findByText("The backend does not identify a winner."),
    ).toBeTruthy();
    expect(screen.getByText(/Backend outcome:/).textContent).toContain(
      "NOT COMPARABLE",
    );
    expect(screen.getByText("Observed activity")).toBeTruthy();
    const evidenceMetadata = screen.getByText(
      "Evidence metadata and provenance",
    );
    expect(evidenceMetadata.parentElement?.textContent).toContain("citation");
    expect(
      screen.getAllByText("Evidence & provenance")[0]?.parentElement
        ?.textContent,
    ).toContain('"source":"API"');
    expect(screen.getByText("No measured CNS evidence.")).toBeTruthy();
    expect(screen.getByText("PMID:123")).toBeTruthy();
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(0);
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(
          ([url, init]) =>
            String(url) === "/api/compare" &&
            JSON.parse(String(init?.body)).asset_ids.length === 2,
        ),
    ).toBe(true);
  });

  it("supports multiple assets and client-side dimension selection", async () => {
    render(<CompareView />);
    await screen.findByText("Asset A · TARGET-A · PHASE_I");
    fireEvent.click(screen.getByLabelText(/Asset C/));
    fireEvent.click(screen.getByLabelText("biology"));
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));

    await screen.findByText("The backend does not identify a winner.");
    await waitFor(() => {
      const post = vi
        .mocked(fetch)
        .mock.calls.find(([url]) => String(url) === "/api/compare");
      expect(JSON.parse(String(post?.[1]?.body)).asset_ids).toEqual([
        "asset-a",
        "asset-b",
        "asset-c",
      ]);
    });
    expect(screen.getByRole("heading", { name: "cns" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "biology" })).toBeNull();
  });

  it("preselects only the requested canonical asset from Opportunities", async () => {
    render(<CompareView initialAssetId="asset-b" />);

    await screen.findByText("Asset B · TARGET-B · PHASE_II");
    expect(screen.getByText("Selected: 1")).toBeTruthy();
    expect((screen.getByLabelText(/Asset B/) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((screen.getByLabelText(/Asset A/) as HTMLInputElement).checked).toBe(
      false,
    );
    expect((screen.getByLabelText(/Asset C/) as HTMLInputElement).checked).toBe(
      false,
    );
    expect(
      (screen.getByRole("button", { name: "Compare" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);

    fireEvent.click(screen.getByLabelText(/Asset A/));
    expect(screen.getByText("Selected: 2")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Compare" }) as HTMLButtonElement)
        .disabled,
    ).toBe(false);
  });

  it("retains two-asset canonical query preselection", async () => {
    render(<CompareView initialAssetId="asset-a" initialAsset2Id="asset-c" />);

    await screen.findByText("Asset A · TARGET-A · PHASE_I");
    expect(screen.getByText("Selected: 2")).toBeTruthy();
    expect((screen.getByLabelText(/Asset A/) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((screen.getByLabelText(/Asset C/) as HTMLInputElement).checked).toBe(
      true,
    );
  });
});
