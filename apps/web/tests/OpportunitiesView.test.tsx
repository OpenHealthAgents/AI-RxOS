import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OpportunitiesView } from "../src/components/OpportunitiesView";

const assets = [
  { id: "pursue-asset", name: "Pursue Asset", target: "T1", stage: "PHASE_I" },
  {
    id: "partner-asset",
    name: "Partner Asset",
    target: "T2",
    stage: "PHASE_II",
  },
  {
    id: "license-asset",
    name: "License Asset",
    target: "T3",
    stage: "PHASE_III",
  },
  {
    id: "monitor-asset",
    name: "Monitor Asset",
    target: "T4",
    stage: "PHASE_I",
  },
  { id: "avoid-asset", name: "Avoid Asset", target: "T5", stage: "PHASE_II" },
  {
    id: "academic-asset",
    name: "Academic Asset",
    target: "T6",
    stage: "UNKNOWN",
  },
  {
    id: "unknown-asset",
    name: "Unknown Asset",
    target: "T7",
    stage: "UNKNOWN",
  },
];

function evaluation(
  decision: string,
  overrides: Record<string, unknown> = {},
  assetId = "pursue-asset",
) {
  return {
    asset_id: assetId,
    evaluation_cutoff: "2026-10-10",
    decision: {
      decision,
      priority: "P2",
      score: 71.5,
      confidence: 0.81,
      supporting_evidence: ["decision evidence"],
      contradictory_evidence: ["decision contradiction"],
      unknowns: ["decision uncertainty"],
      policy_name: "policy-v1",
      policy_version: "1.0",
      model_versions: { decision: "decision-model-2" },
      feature_versions: { biology: "biology-features-3" },
    },
    why: {
      explanation: "API WHY explanation.",
      supporting_evidence: ["PMID:123"],
      contradictory_evidence: ["PMID:456"],
      unknowns: ["Clinical evidence is unknown."],
      evidence_gaps: ["Dated clinical evidence is missing."],
    },
    licensing: {
      status: "UNKNOWN",
      data: {
        current_owner: "Profile Owner",
        originator: "Originator University",
        developer: null,
        academic_origin: null,
        partner: null,
        licensing_status: "UNKNOWN",
        licensing_status_verified: false,
        licensing_verification_source: null,
        licensing_status_rationale: "Availability has not been verified.",
      },
    },
    action_intelligence: {
      recommended_actions: [
        {
          action: "run experiment",
          priority: "P1",
          rationale: "First backend-ranked action.",
          decision_value: 0.9,
          urgency: 0.8,
          effort: 0.6,
          uncertainty_reduction: 0.65,
          supporting_evidence: ["PMID:123"],
          unknowns: ["Clinical evidence is unknown."],
          lineage: { decision: "PURSUE" },
        },
        {
          action: "contact owner",
          priority: "P2",
          rationale: "Second backend-ranked action.",
          decision_value: 0.7,
          urgency: 0.6,
          effort: 0.3,
          uncertainty_reduction: 0.45,
          supporting_evidence: [],
          unknowns: [],
          lineage: { decision: "PURSUE" },
        },
      ],
    },
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderView(
  onNavigateToCompare = vi.fn(),
  onNavigateToEvaluate = vi.fn(),
) {
  render(
    <OpportunitiesView
      onNavigateToCompare={onNavigateToCompare}
      onNavigateToEvaluate={onNavigateToEvaluate}
    />,
  );
  return { onNavigateToCompare, onNavigateToEvaluate };
}

describe("Opportunities workspace", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const path = String(input);
        if (path === "/api/assets") {
          return Promise.resolve(jsonResponse({ assets: [assets[0]] }));
        }
        if (path === "/api/assets/pursue-asset/evaluate") {
          return Promise.resolve(jsonResponse(evaluation("PURSUE")));
        }
        return Promise.resolve(jsonResponse({ detail: "Not found" }, 404));
      }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("maps only supported backend decisions and reports unsupported categories honestly", async () => {
    const decisions: Record<string, string> = {
      "pursue-asset": "PURSUE",
      "partner-asset": "PARTNER",
      "license-asset": "LICENSE",
      "monitor-asset": "MONITOR",
      "avoid-asset": "AVOID",
      "academic-asset": "INSUFFICIENT_EVIDENCE",
      "unknown-asset": "FUTURE_DECISION",
    };
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/assets") {
        return Promise.resolve(jsonResponse({ assets }));
      }
      const assetId = path.split("/")[3] ?? "";
      const academicOrigin =
        assetId === "academic-asset" ? "Originating University" : null;
      return Promise.resolve(
        jsonResponse(
          evaluation(
            decisions[assetId] ?? "INSUFFICIENT_EVIDENCE",
            {
              licensing: {
                status: "AVAILABLE",
                data: { academic_origin: academicOrigin },
              },
            },
            assetId,
          ),
        ),
      );
    });

    renderView();

    expect(
      await screen.findByRole("heading", { name: "Pursue Asset" }),
    ).toBeTruthy();
    for (const category of [
      "Pursue",
      "Partner",
      "License",
      "Academic",
      "Emerging Threat",
      "Monitor",
      "Avoided",
      "Unclassified",
    ]) {
      expect(
        screen.getByRole("button", { name: new RegExp(`^${category}`) }),
      ).toBeTruthy();
    }

    expect(screen.getByText("PURSUE")).toBeTruthy();
    expect(screen.getByText("PARTNER")).toBeTruthy();
    expect(screen.getByText("LICENSE")).toBeTruthy();
    expect(screen.getByText("MONITOR")).toBeTruthy();
    expect(screen.getByText("AVOID")).toBeTruthy();
    expect(screen.getByText("INSUFFICIENT_EVIDENCE")).toBeTruthy();
    expect(screen.getByText("FUTURE_DECISION")).toBeTruthy();
    expect(screen.getByText("Academic Asset")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^License / }));
    expect(screen.getByRole("heading", { name: "License Asset" })).toBeTruthy();
    expect(screen.queryByText(/VERIFIED_AVAILABLE/)).toBeNull();
    fireEvent.click(
      screen.getByText(
        "Evidence, provenance, ownership, licensing, and unknowns",
      ),
    );
    expect(
      screen.getByText(/Licensing profile response state: AVAILABLE/),
    ).toBeTruthy();
    expect(
      screen.getByText(/Profile-reported licensing status: UNKNOWN/),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /A LICENSE decision does not establish licensing availability/i,
      ),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Emerging Threat / }));
    expect(
      screen.getByText("No matching opportunities in the returned catalog."),
    ).toBeTruthy();
  });

  it("preserves API decision, uncertainty, provenance, ranked action, and canonical navigation", async () => {
    const { onNavigateToCompare, onNavigateToEvaluate } = renderView();
    expect(
      await screen.findByRole("heading", { name: "Pursue Asset" }),
    ).toBeTruthy();
    expect(screen.getByText("71.5 / 100 (API scale)")).toBeTruthy();
    expect(screen.getByText("81% (API confidence)")).toBeTruthy();
    expect(screen.getByText("API WHY explanation.")).toBeTruthy();
    expect(
      screen.getByText(/Time-sensitive trigger: NOT RETURNED/),
    ).toBeTruthy();
    expect(screen.getByText("First backend-ranked action.")).toBeTruthy();
    expect(screen.queryByText("Second backend-ranked action.")).toBeNull();
    expect(screen.getByText("0.9")).toBeTruthy();
    expect(screen.getByText("0.8")).toBeTruthy();
    expect(
      screen.getByText(/Suggested action only; no task has been created/),
    ).toBeTruthy();

    const opportunityCard = screen
      .getByRole("heading", { name: "Pursue Asset" })
      .closest("article");
    expect(opportunityCard).not.toBeNull();
    fireEvent.click(
      within(opportunityCard as HTMLElement).getByText(
        "Evidence, provenance, ownership, licensing, and unknowns",
      ),
    );
    expect(screen.getAllByText("PMID:123").length).toBeGreaterThan(0);
    expect(screen.getByText("PMID:456")).toBeTruthy();
    expect(
      screen.getAllByText("Clinical evidence is unknown.").length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/decision-model-2/)).toBeTruthy();
    expect(screen.getByText(/biology-features-3/)).toBeTruthy();
    expect(screen.getByText(/Profile-reported current owner/)).toBeTruthy();
    expect(screen.getByText("Sponsor")).toBeTruthy();
    expect(
      screen.getByText(/UNKNOWN \/ NOT RETURNED BY CURRENT ASSET API/),
    ).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Open Evaluate" }));
    fireEvent.click(screen.getByRole("button", { name: "Compare this asset" }));
    expect(onNavigateToEvaluate).toHaveBeenCalledWith("pursue-asset");
    expect(onNavigateToCompare).toHaveBeenCalledWith("pursue-asset");
  });

  it("requires both the verified licensing state and its verification source", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/assets") {
        return Promise.resolve(
          jsonResponse({
            assets: [
              { ...assets[0], id: "verified-asset", name: "Verified Asset" },
            ],
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(
          evaluation(
            "LICENSE",
            {
              licensing: {
                status: "AVAILABLE",
                data: {
                  licensing_status: "VERIFIED_AVAILABLE",
                  licensing_status_verified: true,
                  licensing_verification_source: "API registry record",
                },
              },
            },
            "verified-asset",
          ),
        ),
      );
    });

    renderView();
    const card = (
      await screen.findByRole("heading", { name: "Verified Asset" })
    ).closest("article");
    expect(card).not.toBeNull();
    fireEvent.click(
      within(card as HTMLElement).getByText(
        "Evidence, provenance, ownership, licensing, and unknowns",
      ),
    );
    expect(
      within(card as HTMLElement).getByText(
        /Profile-reported licensing status: VERIFIED_AVAILABLE — API registry record/,
      ),
    ).toBeTruthy();

    cleanup();
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/assets") {
        return Promise.resolve(
          jsonResponse({
            assets: [
              {
                ...assets[0],
                id: "unverified-asset",
                name: "Unverified Asset",
              },
            ],
          }),
        );
      }
      return Promise.resolve(
        jsonResponse(
          evaluation(
            "LICENSE",
            {
              licensing: {
                status: "AVAILABLE",
                data: {
                  licensing_status: "VERIFIED_AVAILABLE",
                  licensing_status_verified: false,
                  licensing_verification_source: "Unverified source string",
                },
              },
            },
            "unverified-asset",
          ),
        ),
      );
    });

    renderView();
    const unverifiedCard = (
      await screen.findByRole("heading", { name: "Unverified Asset" })
    ).closest("article");
    expect(unverifiedCard).not.toBeNull();
    fireEvent.click(
      within(unverifiedCard as HTMLElement).getByText(
        "Evidence, provenance, ownership, licensing, and unknowns",
      ),
    );
    expect(
      within(unverifiedCard as HTMLElement).getByText(
        /without a complete verification assertion; availability not asserted/,
      ),
    ).toBeTruthy();
  });

  it("does not display an evaluation returned for a different canonical asset", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/assets") {
        return Promise.resolve(jsonResponse({ assets: [assets[0]] }));
      }
      return Promise.resolve(
        jsonResponse(evaluation("PURSUE", {}, "other-id")),
      );
    });

    renderView();

    const card = (
      await screen.findByRole("heading", { name: "Pursue Asset" })
    ).closest("article");
    expect(card).not.toBeNull();
    expect(
      within(card as HTMLElement).getByText(
        /Decision and WHY data are unavailable for this asset/,
      ),
    ).toBeTruthy();
    expect(within(card as HTMLElement).queryByText("PURSUE")).toBeNull();
  });

  it("shows unknown decision values and missing ranked actions without fallback conclusions", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
      const path = String(input);
      if (path === "/api/assets") {
        return Promise.resolve(
          jsonResponse({
            assets: [
              { ...assets[0], owner: null },
              { ...assets[1], id: "asset-b", name: "Asset B", owner: null },
            ],
          }),
        );
      }
      if (path.endsWith("/pursue-asset/evaluate")) {
        return Promise.resolve(
          jsonResponse(
            evaluation("INSUFFICIENT_EVIDENCE", {
              decision: {
                decision: "INSUFFICIENT_EVIDENCE",
                score: null,
                confidence: null,
                unknowns: ["Decision evidence is missing."],
              },
              action_intelligence: { recommended_actions: [] },
            }),
          ),
        );
      }
      return Promise.resolve(
        jsonResponse({ detail: "Evaluation unavailable" }, 503),
      );
    });

    renderView();
    expect(
      await screen.findByRole("heading", { name: "Pursue Asset" }),
    ).toBeTruthy();
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(0);
    expect(screen.getByText(/No ranked action was returned/)).toBeTruthy();
    const unavailableCard = screen
      .getByRole("heading", { name: "Asset B" })
      .closest("article");
    expect(unavailableCard).not.toBeNull();
    expect(
      within(unavailableCard as HTMLElement).getByText(
        /Decision and WHY data are unavailable for this asset/,
      ),
    ).toBeTruthy();
    expect(unavailableCard?.textContent).toContain(
      "no fallback conclusion is shown",
    );

    const evaluatedCard = screen
      .getByRole("heading", { name: "Pursue Asset" })
      .closest("article");
    expect(evaluatedCard).not.toBeNull();
    fireEvent.click(
      within(evaluatedCard as HTMLElement).getByText(
        "Evidence, provenance, ownership, licensing, and unknowns",
      ),
    );
    expect(
      within(evaluatedCard as HTMLElement).getByText(
        /Decision evidence is missing/,
      ),
    ).toBeTruthy();
  });

  it("handles catalog loading, failure and an empty successful catalog", async () => {
    let resolveCatalog: ((response: Response) => void) | undefined;
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveCatalog = resolve;
        }),
    );
    renderView();
    expect(
      screen.getByRole("status", { name: "Loading opportunities" }),
    ).toBeTruthy();
    resolveCatalog?.(jsonResponse({ assets: [] }));
    expect(
      await screen.findByText("The API returned no canonical assets."),
    ).toBeTruthy();

    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) =>
      String(input) === "/api/assets"
        ? Promise.resolve(jsonResponse({ detail: "Unavailable" }, 503))
        : Promise.resolve(jsonResponse({}, 404)),
    );
    cleanup();
    renderView();
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(2);
    });
    expect(screen.getByText("Opportunity data is unavailable.")).toBeTruthy();
  });

  it("rejects malformed successful catalog and evaluation payloads", async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) =>
      String(input) === "/api/assets"
        ? Promise.resolve(jsonResponse({ assets: [assets[0]] }))
        : Promise.resolve(jsonResponse({ decision: { decision: "PURSUE" } })),
    );

    renderView();
    const card = (
      await screen.findByRole("heading", { name: "Pursue Asset" })
    ).closest("article");
    expect(card).not.toBeNull();
    expect(
      await within(card as HTMLElement).findByText(
        /Decision and WHY data are unavailable for this asset/,
      ),
    ).toBeTruthy();
    expect(
      within(card as HTMLElement).getByText(/no fallback conclusion is shown/),
    ).toBeTruthy();

    cleanup();
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) =>
      String(input) === "/api/assets"
        ? Promise.resolve(jsonResponse({ assets: [{ id: "missing-name" }] }))
        : Promise.resolve(jsonResponse({})),
    );
    renderView();
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("Opportunity data is unavailable.")).toBeTruthy();
  });
});
