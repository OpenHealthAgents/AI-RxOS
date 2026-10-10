import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EvaluateView } from "../src/components/EvaluateView";
import { WorkspaceProvider } from "../src/context/WorkspaceContext";
import { navigationMocks } from "./setup";

const asset = {
  id: "asset-a",
  name: "Asset A",
  target: "TARGET-X",
  modality: "SMALL_MOLECULE",
  stage: "PHASE_II",
  primary_indication: "Indication X",
  key_attributes: { selectivity: "UNKNOWN" },
  business_profile: { patent_ip: "UNKNOWN" },
};

function domain(status: string, data: unknown, reason: string | null = null) {
  return {
    asset_id: "asset-a",
    tenant_id: "tenant-context",
    evaluation_cutoff: "2026-10-08",
    status,
    data,
    reason,
  };
}

const evaluation = {
  asset_id: "asset-a",
  tenant_id: "tenant-context",
  evaluation_cutoff: "2026-10-08",
  decision: {
    decision: "INSUFFICIENT_EVIDENCE",
    priority: "P4",
    score: 0,
    confidence: 0,
    supporting_evidence: [],
    contradictory_evidence: [],
    unknowns: ["No supported decision."],
  },
  why: { explanation: "WHY snapshot", unknowns: ["No evidence"] },
  biology: domain("AVAILABLE", {
    biology_validation: {
      value: 0.72,
      status: "AVAILABLE",
      confidence: 0.8,
      epistemic_class: "DERIVED_FEATURE",
      supporting_evidence: [
        {
          source_reference: "PMID:123",
          source_url: "https://example.org/evidence/123",
        },
      ],
      provenance: {
        model_version: "bio-v2",
        feature_version: "bio-feature-v3",
      },
    },
  }),
  clinical: domain("UNKNOWN", null, "Clinical evidence is unavailable."),
  cns: domain("UNKNOWN", null, "CNS evidence is unavailable."),
  patients: domain("UNKNOWN", null),
  safety: domain("INSUFFICIENT_EVIDENCE", null, "Safety evidence is missing."),
  resistance: domain("UNKNOWN", null),
  combinations: domain("UNKNOWN", null),
  competitive: domain("UNAVAILABLE", null),
  licensing: domain("UNKNOWN", null, "Licensing availability is not known."),
  commercial: domain("UNKNOWN", null),
};

const evidence = { status: "UNKNOWN", cutoff: "2026-10-08", evidence: [] };
const history = { as_of: "2026-10-08", evidence: [], milestones: [] };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWorkspace() {
  return render(
    <WorkspaceProvider>
      <EvaluateView />
    </WorkspaceProvider>,
  );
}

describe("Evaluate workspace", () => {
  beforeEach(() => {
    navigationMocks.search = "";
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/api/assets") {
          return Promise.resolve(
            jsonResponse({ tenant_id: "tenant-context", assets: [asset] }),
          );
        }
        if (path === "/api/assets/asset-a") {
          return Promise.resolve(
            jsonResponse({
              asset_id: "asset-a",
              tenant_id: "tenant-context",
              asset,
            }),
          );
        }
        if (path === "/api/assets/asset-a/evaluate") {
          return Promise.resolve(jsonResponse(evaluation));
        }
        if (path === "/api/assets/asset-a/evidence") {
          return Promise.resolve(jsonResponse(evidence));
        }
        if (path === "/api/assets/asset-a/history") {
          return Promise.resolve(jsonResponse(history));
        }
        if (path === "/api/assets/asset-a/why") {
          return Promise.resolve(
            jsonResponse({
              asset_id: "asset-a",
              evaluation_cutoff: "2026-10-08",
              decision: "INSUFFICIENT_EVIDENCE",
              explanation: "WHY from the existing engine.",
              supporting_evidence: ["PMID:123"],
              contradictory_evidence: [],
              unknowns: ["No clinical evidence."],
              ml_contributors: [
                { model_version: "bio-v2", feature_version: "bio-feature-v3" },
              ],
              assumptions: [],
              evidence_gaps: ["Clinical evidence unavailable."],
              what_would_change_recommendation: [
                "Provide dated clinical evidence.",
              ],
              trace: [],
            }),
          );
        }
        return Promise.resolve(
          jsonResponse({ detail: "Unexpected route" }, 404),
        );
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("loads the canonical asset and evaluates using the Core API response", async () => {
    renderWorkspace();
    fireEvent.change(screen.getByLabelText("Canonical asset"), {
      target: { value: "asset-a" },
    });
    expect(
      await screen.findByRole("heading", { name: "Asset A" }),
    ).toBeTruthy();
    expect(screen.getByText("INSUFFICIENT_EVIDENCE")).toBeTruthy();
    expect(screen.getByText("Priority: P4")).toBeTruthy();
    expect(screen.getByText("Confidence: 0%")).toBeTruthy();
    expect(screen.getByText("TARGET-X")).toBeTruthy();
    expect(screen.getByText("Clinical evidence is unavailable.")).toBeTruthy();
    expect(screen.getByText("Safety evidence is missing.")).toBeTruthy();
    expect(
      screen.getByRole("link", {
        name: "https://example.org/evidence/123",
      }),
    ).toBeTruthy();
    fireEvent.click(screen.getByText("Model and evidence provenance"));
    expect(screen.getByText("bio-v2")).toBeTruthy();
    expect(screen.getAllByText("bio-feature-v3").length).toBeGreaterThan(0);

    for (const section of [
      "Development Potential",
      "Biology Profile",
      "Key Attributes",
      "Preclinical Evidence",
      "Clinical Development",
      "CNS",
      "Patient Match",
      "Safety",
      "Resistance",
      "Combinations",
      "Competitive Landscape",
      "Regulatory / IP",
      "Licensing",
      "Commercial Opportunity",
      "Evidence & Provenance",
      "Temporal history",
    ]) {
      expect(screen.getByRole("heading", { name: section })).toBeTruthy();
    }
    const requests = vi.mocked(fetch).mock.calls;
    expect(requests.map(([url]) => String(url))).toContain(
      "/api/assets/asset-a/evaluate",
    );
    expect(
      requests.every(([, init]) => init?.credentials === "same-origin"),
    ).toBe(true);
    expect(requests.every(([url]) => !String(url).includes("tenant_id="))).toBe(
      true,
    );
  });

  it("opens the existing WHY API and displays evidence, unknowns and model lineage", async () => {
    renderWorkspace();
    await screen.findByRole("heading", { name: "Asset A" });
    fireEvent.click(
      screen.getByRole("button", { name: "WHY this recommendation?" }),
    );
    expect(
      await screen.findByText("WHY from the existing engine."),
    ).toBeTruthy();
    expect(screen.getByText("Clinical evidence unavailable.")).toBeTruthy();
    expect(screen.getAllByText("bio-feature-v3").length).toBeGreaterThan(0);
  });

  it("labels historical cutoff and forwards it to the data APIs", async () => {
    navigationMocks.search = "asset=asset-a&cutoff=2020-01-01";
    renderWorkspace();
    await waitFor(() => {
      expect(
        vi
          .mocked(fetch)
          .mock.calls.some(([url]) =>
            String(url).includes(
              "/api/assets/asset-a/evaluate?cutoff=2020-01-01",
            ),
          ),
      ).toBe(true);
    });
    expect(
      screen.getByText("Historical evaluation cutoff: 2020-01-01"),
    ).toBeTruthy();
  });

  it("surfaces asset/evaluation API errors rather than using fixture fallbacks", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      if (String(input) === "/api/assets") {
        return Promise.resolve(
          jsonResponse({ assets: [asset], tenant_id: null }),
        );
      }
      if (String(input) === "/api/assets/asset-a") {
        return Promise.resolve(
          jsonResponse({ asset_id: "asset-a", tenant_id: null, asset }),
        );
      }
      return Promise.resolve(
        jsonResponse({ detail: "Asset evaluation denied." }, 403),
      );
    });
    renderWorkspace();
    expect(await screen.findByText(/Asset evaluation denied\./)).toBeTruthy();
  });

  it("preserves available domains and marks a missing domain explicitly unknown", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/assets")
        return Promise.resolve(jsonResponse({ assets: [asset] }));
      if (path === "/api/assets/asset-a")
        return Promise.resolve(jsonResponse({ asset_id: "asset-a", asset }));
      if (path === "/api/assets/asset-a/evaluate") {
        const { cns: _missingCns, ...partialEvaluation } = evaluation;
        return Promise.resolve(jsonResponse(partialEvaluation));
      }
      if (path === "/api/assets/asset-a/evidence")
        return Promise.resolve(jsonResponse(evidence));
      if (path === "/api/assets/asset-a/history")
        return Promise.resolve(jsonResponse(history));
      return Promise.resolve(jsonResponse({ detail: "Unexpected route" }, 404));
    });
    renderWorkspace();
    expect(
      await screen.findByText(
        "cns domain was not returned by the evaluation API.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("0.72")).toBeTruthy();
  });

  it("reports a malformed successful evaluation payload", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/assets")
        return Promise.resolve(jsonResponse({ assets: [asset] }));
      if (path === "/api/assets/asset-a")
        return Promise.resolve(jsonResponse({ asset_id: "asset-a", asset }));
      return Promise.resolve(jsonResponse({ status: "AVAILABLE" }));
    });
    renderWorkspace();
    expect(
      await screen.findByText(
        "The evaluation API returned an invalid response.",
      ),
    ).toBeTruthy();
  });
});
