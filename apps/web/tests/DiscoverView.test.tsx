import React from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DiscoverView } from "../src/components/DiscoverView";
import { navigationMocks } from "./setup";

const discoverResult = {
  query_id: "query-1",
  query: "HER2-mutant oncology opportunity",
  tenant_id: "tenant-context",
  evaluation_cutoff: null,
  status: "AVAILABLE" as const,
  parsed_intent: {
    target_type: "asset",
    entities: { target: ["HER2"], mutation: ["mutant"] },
  },
  filters: [
    { field: "target", operator: "equals", value: "HER2", source_span: "HER2" },
  ],
  candidates: [
    {
      asset_id: "asset-a",
      name: "Asset A",
      ranking: 1,
      scores: {
        derived_search_score: 82.4,
        score_type: "DETERMINISTIC_SEARCH_HEURISTIC",
        ml_ranking_status: "UNAVAILABLE",
        ml_ranking_score: null,
        ml_unavailable_reason: "No validated ranking model.",
      },
      confidence: null,
      confidence_status: "UNKNOWN_UNCALIBRATED",
      reasons: ["Matched target HER2"],
      evidence: [
        {
          evidence_id: "ev-1",
          evidence_type: "publication",
          source_citation: "PMID:12345",
          source_url: null,
        },
      ],
      evidence_status: "AVAILABLE",
      unknowns: ["No calibrated candidate confidence."],
    },
    {
      asset_id: "asset-b",
      name: "Asset B",
      ranking: 2,
      scores: {
        derived_search_score: null,
        score_type: "DETERMINISTIC_SEARCH_HEURISTIC",
        ml_ranking_status: "UNAVAILABLE",
        ml_ranking_score: null,
        ml_unavailable_reason: "No validated ranking model.",
      },
      confidence: null,
      confidence_status: "UNKNOWN_UNCALIBRATED",
      reasons: [],
      evidence: [],
      evidence_status: "UNKNOWN",
      unknowns: ["Supporting evidence unavailable."],
    },
  ],
  ranking_status: "AVAILABLE_DERIVED_SEARCH",
  ml_ranking_status: "UNAVAILABLE",
  unknowns: [],
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Discover workspace", () => {
  beforeEach(() => {
    navigationMocks.push.mockReset();
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("submits a natural-language query and renders interpretation, filters, ranking and evidence", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(discoverResult));
    render(<DiscoverView />);

    fireEvent.change(screen.getByLabelText("Opportunity query"), {
      target: { value: "HER2-mutant oncology opportunity" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText("Matched target HER2")).toBeTruthy();
    expect(screen.getByText("HER2")).toBeTruthy();
    expect(screen.getByText(/target equals HER2/i)).toBeTruthy();
    expect(screen.getByText("82.4 / 100")).toBeTruthy();
    expect(screen.getAllByText("UNKNOWN").length).toBeGreaterThan(0);
    expect(screen.getByText("PMID:12345")).toBeTruthy();
    expect(screen.getByText("Supporting evidence unavailable.")).toBeTruthy();
    expect(fetch).toHaveBeenCalledWith(
      "/api/discover",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({ query: "HER2-mutant oncology opportunity" }),
      }),
    );
  });

  it("shows a loading state during the discovery request", async () => {
    let resolveRequest: ((response: Response) => void) | undefined;
    vi.mocked(fetch).mockReturnValueOnce(
      new Promise<Response>((resolve) => {
        resolveRequest = resolve;
      }),
    );
    render(<DiscoverView />);
    fireEvent.change(screen.getByLabelText("Opportunity query"), {
      target: { value: "HER2 asset" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(
      screen.getByRole("status", { name: "Searching opportunities" }),
    ).toBeTruthy();
    resolveRequest?.(jsonResponse({ ...discoverResult, candidates: [] }));
    expect(await screen.findByText("No candidates found")).toBeTruthy();
  });

  it("navigates to evaluation using the canonical candidate identifier", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(discoverResult));
    render(<DiscoverView />);
    fireEvent.change(screen.getByLabelText("Opportunity query"), {
      target: { value: "HER2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    const evaluateButtons = await screen.findAllByRole("button", {
      name: "Evaluate",
    });
    const firstEvaluateButton = evaluateButtons[0];
    if (!firstEvaluateButton) throw new Error("Expected an Evaluate action.");
    fireEvent.click(firstEvaluateButton);
    expect(navigationMocks.push).toHaveBeenCalledWith(
      "/evaluate?asset=asset-a",
    );
  });

  it("runs Compare using the existing API and does not fabricate unsupported actions", async () => {
    const compareResult = {
      evaluation_cutoff: "2026-10-08",
      dimensions: [
        {
          dimension: "biology",
          winner_asset_id: null,
          winner_status: "INSUFFICIENT_EVIDENCE",
          confidence: null,
          explanation: "No defensible winner.",
          unknowns: ["Comparable evidence unavailable."],
        },
      ],
    };
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse(discoverResult))
      .mockResolvedValueOnce(jsonResponse(compareResult));
    render(<DiscoverView />);
    fireEvent.change(screen.getByLabelText("Opportunity query"), {
      target: { value: "HER2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    const addButtons = await screen.findAllByRole("button", {
      name: "Add to compare",
    });
    const [firstCandidate, secondCandidate] = addButtons;
    if (!firstCandidate || !secondCandidate) {
      throw new Error("Expected two candidate compare buttons.");
    }
    fireEvent.click(firstCandidate);
    fireEvent.click(secondCandidate);
    fireEvent.click(
      screen.getByRole("button", { name: "Compare selected (2/2)" }),
    );

    expect(
      await screen.findByRole("region", { name: "Comparison results" }),
    ).toBeTruthy();
    expect(screen.getByText("INSUFFICIENT_EVIDENCE")).toBeTruthy();
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/compare",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({ asset_ids: ["asset-a", "asset-b"] }),
      }),
    );
    expect(
      screen
        .getAllByRole("button", { name: "Watch unavailable" })[0]
        ?.hasAttribute("disabled"),
    ).toBe(true);
    expect(
      screen
        .getAllByRole("button", { name: "Create unavailable" })[0]
        ?.hasAttribute("disabled"),
    ).toBe(true);
  });

  it("displays API errors and a real empty result state", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        jsonResponse({ detail: "Unsupported filter." }, 422),
      )
      .mockResolvedValueOnce(
        jsonResponse({ ...discoverResult, candidates: [] }),
      );
    render(<DiscoverView />);
    const query = screen.getByLabelText("Opportunity query");
    fireEvent.change(query, { target: { value: "unknown filter" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.change(query, { target: { value: "HER2" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(screen.getByText("No candidates found")).toBeTruthy(),
    );
  });

  it("rejects a malformed successful API response instead of rendering it as a result", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ status: "AVAILABLE" }),
    );
    render(<DiscoverView />);
    fireEvent.change(screen.getByLabelText("Opportunity query"), {
      target: { value: "HER2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(
      await screen.findByText(
        "The discovery API returned an invalid response.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Ranked candidates")).toBeNull();
  });
});
