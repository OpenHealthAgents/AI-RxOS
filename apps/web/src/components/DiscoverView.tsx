"use client";

import React, { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

interface DiscoverFilter {
  field: string;
  operator: string;
  value: string | number | boolean | string[] | number[];
  source_span?: string | null;
}

interface DiscoverCandidate {
  asset_id: string;
  name: string;
  ranking: number;
  scores: {
    derived_search_score: number | null;
    score_type: string;
    ml_ranking_status: string;
    ml_ranking_score: number | null;
    ml_unavailable_reason: string | null;
  };
  confidence: number | null;
  confidence_status: string;
  reasons: string[];
  evidence: Array<{
    evidence_id: string;
    evidence_type: string;
    source_citation: string;
    source_url: string | null;
  }>;
  evidence_status: string;
  unknowns: string[];
}

interface DiscoverResult {
  query_id: string;
  query: string;
  tenant_id: string | null;
  evaluation_cutoff: string | null;
  status: "AVAILABLE" | "UNAVAILABLE";
  parsed_intent: { target_type: string; entities: Record<string, string[]> };
  filters: DiscoverFilter[];
  candidates: DiscoverCandidate[];
  ranking_status: string;
  ml_ranking_status: string;
  unknowns: string[];
}

interface CompareResult {
  evaluation_cutoff: string;
  dimensions: Array<{
    dimension: string;
    winner_asset_id: string | null;
    winner_status: string;
    confidence: number | null;
    explanation: string;
    unknowns: string[];
  }>;
}

function describeError(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail !== undefined) return JSON.stringify(detail);
  }
  return fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((item) => typeof item === "string")
  );
}

function isNullableNumber(value: unknown): value is number | null {
  return (
    value === null || (typeof value === "number" && Number.isFinite(value))
  );
}

function isDiscoverResult(payload: unknown): payload is DiscoverResult {
  if (
    !isRecord(payload) ||
    typeof payload.query_id !== "string" ||
    typeof payload.query !== "string" ||
    typeof payload.status !== "string" ||
    !isRecord(payload.parsed_intent) ||
    typeof payload.parsed_intent.target_type !== "string" ||
    !isRecord(payload.parsed_intent.entities) ||
    !Object.values(payload.parsed_intent.entities).every(isStringArray) ||
    !Array.isArray(payload.filters) ||
    !Array.isArray(payload.candidates) ||
    typeof payload.ranking_status !== "string" ||
    typeof payload.ml_ranking_status !== "string" ||
    !isStringArray(payload.unknowns) ||
    (payload.tenant_id !== null && typeof payload.tenant_id !== "string") ||
    (payload.evaluation_cutoff !== null &&
      typeof payload.evaluation_cutoff !== "string")
  ) {
    return false;
  }

  const validFilters = payload.filters.every(
    (filter) =>
      isRecord(filter) &&
      typeof filter.field === "string" &&
      typeof filter.operator === "string" &&
      (typeof filter.value === "string" ||
        typeof filter.value === "number" ||
        typeof filter.value === "boolean" ||
        (Array.isArray(filter.value) &&
          filter.value.every(
            (item) => typeof item === "string" || typeof item === "number",
          ))),
  );
  const validCandidates = payload.candidates.every((candidate) => {
    if (
      !isRecord(candidate) ||
      typeof candidate.asset_id !== "string" ||
      typeof candidate.name !== "string" ||
      typeof candidate.ranking !== "number" ||
      !isRecord(candidate.scores) ||
      !isNullableNumber(candidate.scores.derived_search_score) ||
      typeof candidate.scores.score_type !== "string" ||
      typeof candidate.scores.ml_ranking_status !== "string" ||
      !isNullableNumber(candidate.scores.ml_ranking_score) ||
      (candidate.scores.ml_unavailable_reason !== null &&
        typeof candidate.scores.ml_unavailable_reason !== "string") ||
      !isNullableNumber(candidate.confidence) ||
      typeof candidate.confidence_status !== "string" ||
      !isStringArray(candidate.reasons) ||
      !Array.isArray(candidate.evidence) ||
      typeof candidate.evidence_status !== "string" ||
      !isStringArray(candidate.unknowns)
    ) {
      return false;
    }
    return candidate.evidence.every(
      (evidence) =>
        isRecord(evidence) &&
        typeof evidence.evidence_id === "string" &&
        typeof evidence.evidence_type === "string" &&
        typeof evidence.source_citation === "string" &&
        (evidence.source_url === null ||
          typeof evidence.source_url === "string"),
    );
  });
  return validFilters && validCandidates;
}

function parseDiscoverResult(payload: unknown): DiscoverResult {
  if (!isDiscoverResult(payload)) {
    throw new Error("The discovery API returned an invalid response.");
  }
  return payload;
}

function isCompareResult(payload: unknown): payload is CompareResult {
  if (
    !isRecord(payload) ||
    typeof payload.evaluation_cutoff !== "string" ||
    !Array.isArray(payload.dimensions) ||
    !payload.dimensions.every(
      (dimension) =>
        isRecord(dimension) &&
        typeof dimension.dimension === "string" &&
        (dimension.winner_asset_id === null ||
          typeof dimension.winner_asset_id === "string") &&
        typeof dimension.winner_status === "string" &&
        isNullableNumber(dimension.confidence) &&
        typeof dimension.explanation === "string" &&
        isStringArray(dimension.unknowns),
    )
  ) {
    return false;
  }
  return true;
}

function parseCompareResult(payload: unknown): CompareResult {
  if (!isCompareResult(payload)) {
    throw new Error("The comparison API returned an invalid response.");
  }
  return payload;
}

function displayValue(value: DiscoverFilter["value"]): string {
  return Array.isArray(value) ? value.join(", ") : String(value);
}

export function DiscoverView() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedForCompare, setSelectedForCompare] = useState<string[]>([]);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(
    null,
  );
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const interpretation = useMemo(
    () => result?.parsed_intent.entities ?? {},
    [result],
  );

  async function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery) {
      setError("Enter an opportunity query to search.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedForCompare([]);
    setCompareResult(null);
    try {
      const response = await fetch("/api/discover", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: cleanQuery }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        throw new Error(
          describeError(payload, `Discovery failed (${response.status}).`),
        );
      }
      setResult(parseDiscoverResult(payload));
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Discovery failed. Please retry.",
      );
    } finally {
      setLoading(false);
    }
  }

  function toggleCompare(assetId: string) {
    setCompareError(null);
    setSelectedForCompare((current) => {
      if (current.includes(assetId))
        return current.filter((id) => id !== assetId);
      if (current.length === 2) {
        setCompareError("Select no more than two candidates at a time.");
        return current;
      }
      return [...current, assetId];
    });
  }

  async function compareSelected() {
    if (selectedForCompare.length !== 2) return;
    setCompareLoading(true);
    setCompareError(null);
    setCompareResult(null);
    try {
      const response = await fetch("/api/compare", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: selectedForCompare }),
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        throw new Error(
          describeError(payload, `Comparison failed (${response.status}).`),
        );
      }
      setCompareResult(parseCompareResult(payload));
    } catch (caught) {
      setCompareError(
        caught instanceof Error
          ? caught.message
          : "Comparison failed. Please retry.",
      );
    } finally {
      setCompareLoading(false);
    }
  }

  function exportResults() {
    if (!result) return;
    const file = new Blob([JSON.stringify(result, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(file);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `discover-${result.query_id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 text-slate-800 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Prompt 58 · Opportunity Discovery
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
            Discover opportunities
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Search the canonical asset catalog using natural language. Ranking
            and confidence are shown only as returned by the discovery API.
          </p>
        </header>

        <form
          onSubmit={submitSearch}
          className="mt-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          aria-label="Opportunity search"
        >
          <label
            htmlFor="discover-query"
            className="mb-2 block text-sm font-semibold text-slate-800"
          >
            Opportunity query
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              id="discover-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. HER2-mutant assets with clinical evidence and CNS activity"
              maxLength={2000}
              required
              className="min-h-11 flex-1 rounded-md border border-slate-300 px-3 text-sm text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100"
            />
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="min-h-11 rounded-md bg-blue-700 px-5 text-sm font-semibold text-white hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? "Searching…" : "Search"}
            </button>
          </div>
        </form>

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"
          >
            <strong>Discovery unavailable.</strong> {error}
          </div>
        )}

        {loading && (
          <div
            role="status"
            aria-label="Searching opportunities"
            className="mt-5 space-y-3"
          >
            {[0, 1, 2].map((item) => (
              <div
                key={item}
                className="h-36 animate-pulse rounded-xl border border-slate-200 bg-white p-4"
              >
                <div className="h-4 w-1/3 rounded bg-slate-200" />
                <div className="mt-4 h-3 w-2/3 rounded bg-slate-100" />
                <div className="mt-3 h-3 w-1/2 rounded bg-slate-100" />
              </div>
            ))}
          </div>
        )}

        {!result && !loading && !error && (
          <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <h2 className="font-semibold text-slate-900">
              Start with a question
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              Query interpretation, filters, ranking, evidence, and uncertainty
              will appear here.
            </p>
          </div>
        )}

        {result && !loading && (
          <div className="mt-5 space-y-5">
            <section
              aria-labelledby="query-interpretation"
              className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2
                    id="query-interpretation"
                    className="font-semibold text-slate-900"
                  >
                    Query interpretation
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">{result.query}</p>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                  {result.parsed_intent.target_type}
                  {result.evaluation_cutoff
                    ? ` · As of ${result.evaluation_cutoff}`
                    : ""}
                </span>
              </div>
              <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(interpretation).map(([name, values]) => (
                  <div key={name} className="rounded-md bg-slate-50 p-3">
                    <dt className="text-xs font-semibold uppercase text-slate-500">
                      {name.replaceAll("_", " ")}
                    </dt>
                    <dd className="mt-1 text-sm text-slate-900">
                      {values.length ? values.join(", ") : "UNKNOWN"}
                    </dd>
                  </div>
                ))}
                {Object.keys(interpretation).length === 0 && (
                  <p className="text-sm text-slate-600">
                    No entities were parsed.
                  </p>
                )}
              </dl>
              <div className="mt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Active filters
                </h3>
                {result.filters.length ? (
                  <ul className="mt-2 flex flex-wrap gap-2">
                    {result.filters.map((filter, index) => (
                      <li
                        key={`${filter.field}-${index}`}
                        className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1 text-xs text-blue-900"
                      >
                        {filter.field} {filter.operator}{" "}
                        {displayValue(filter.value)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-slate-600">
                    No structured filters were derived.
                  </p>
                )}
              </div>
              <p className="mt-3 text-xs text-slate-500">
                Ranking: {result.ranking_status.replaceAll("_", " ")} · ML
                ranking: {result.ml_ranking_status}
              </p>
              {result.unknowns.map((unknown, index) => (
                <p key={index} className="mt-1 text-xs text-amber-800">
                  UNKNOWN: {unknown}
                </p>
              ))}
            </section>

            <section aria-labelledby="ranked-candidates">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2
                    id="ranked-candidates"
                    className="text-lg font-bold text-slate-900"
                  >
                    Ranked candidates
                  </h2>
                  <p className="text-xs text-slate-600">
                    {result.candidates.length} result
                    {result.candidates.length === 1 ? "" : "s"} · deterministic
                    search heuristic; not an ML opportunity score
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={compareSelected}
                    disabled={selectedForCompare.length !== 2 || compareLoading}
                    className="rounded-md border border-blue-700 px-3 py-2 text-xs font-semibold text-blue-800 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {compareLoading
                      ? "Comparing…"
                      : `Compare selected (${selectedForCompare.length}/2)`}
                  </button>
                  <button
                    type="button"
                    onClick={exportResults}
                    className="rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    Export results
                  </button>
                </div>
              </div>

              {compareError && (
                <p role="alert" className="mb-3 text-sm text-rose-800">
                  {compareError}
                </p>
              )}
              {compareResult && (
                <div
                  role="region"
                  aria-label="Comparison results"
                  className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-4"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <h3 className="font-semibold text-slate-900">
                        API comparison · cutoff{" "}
                        {compareResult.evaluation_cutoff}
                      </h3>
                      <p className="text-xs text-slate-600">
                        Only evidence-supported winners are shown; otherwise the
                        API state is preserved.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setCompareResult(null)}
                      aria-label="Close comparison results"
                      className="rounded px-2 py-1 text-sm text-slate-700 hover:bg-white"
                    >
                      Close
                    </button>
                  </div>
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {compareResult.dimensions.map((dimension) => (
                      <div
                        key={dimension.dimension}
                        className="rounded-md border border-blue-100 bg-white p-3"
                      >
                        <div className="flex justify-between gap-2 text-sm font-semibold">
                          <span>{dimension.dimension}</span>
                          <span>
                            {dimension.winner_asset_id ??
                              dimension.winner_status}
                          </span>
                        </div>
                        <p className="mt-1 text-xs text-slate-600">
                          Confidence:{" "}
                          {dimension.confidence === null
                            ? "UNKNOWN"
                            : `${Math.round(dimension.confidence * 100)}%`}
                        </p>
                        <p className="mt-1 text-xs text-slate-700">
                          {dimension.explanation}
                        </p>
                        {dimension.unknowns.map((unknown, index) => (
                          <p
                            key={index}
                            className="mt-1 text-xs text-amber-800"
                          >
                            UNKNOWN: {unknown}
                          </p>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.candidates.length === 0 && (
                <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
                  <h3 className="font-semibold text-slate-900">
                    No candidates found
                  </h3>
                  <p className="mt-1 text-sm text-slate-600">
                    The API returned no matching candidates. Try changing the
                    query; no assets or scores have been added as substitutes.
                  </p>
                </div>
              )}

              <div className="space-y-3">
                {result.candidates.map((candidate) => (
                  <article
                    key={candidate.asset_id}
                    className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded bg-slate-900 px-2 py-1 text-xs font-bold text-white">
                            #{candidate.ranking}
                          </span>
                          <h3 className="text-lg font-bold text-slate-900">
                            {candidate.name}
                          </h3>
                          <span className="text-xs text-slate-500">
                            {candidate.asset_id}
                          </span>
                          <span
                            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                              candidate.evidence_status === "AVAILABLE"
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-amber-100 text-amber-900"
                            }`}
                          >
                            Evidence {candidate.evidence_status}
                          </span>
                        </div>
                        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                          <Score
                            label="Search score"
                            value={
                              candidate.scores.derived_search_score === null
                                ? "UNKNOWN"
                                : `${candidate.scores.derived_search_score.toFixed(1)} / 100`
                            }
                            detail="Deterministic heuristic; not a decision score."
                          />
                          <Score
                            label="ML opportunity score"
                            value={
                              candidate.scores.ml_ranking_score === null
                                ? "UNAVAILABLE"
                                : candidate.scores.ml_ranking_score.toFixed(2)
                            }
                            detail={
                              candidate.scores.ml_unavailable_reason ??
                              candidate.scores.ml_ranking_status
                            }
                          />
                          <Score
                            label="Confidence"
                            value={
                              candidate.confidence === null
                                ? "UNKNOWN"
                                : `${Math.round(candidate.confidence * 100)}%`
                            }
                            detail={candidate.confidence_status.replaceAll(
                              "_",
                              " ",
                            )}
                          />
                          <Score
                            label="Clinical score"
                            value="UNKNOWN"
                            detail="Not returned by the Discover API."
                          />
                          <Score
                            label="CNS"
                            value="UNKNOWN"
                            detail="Not returned by the Discover API."
                          />
                          <Score
                            label="Patient fit"
                            value="UNKNOWN"
                            detail="Not returned by the Discover API."
                          />
                          <Score
                            label="Licensing"
                            value="UNKNOWN"
                            detail="Not returned by the Discover API; no availability claim."
                          />
                          <Score
                            label="Commercial"
                            value="UNKNOWN"
                            detail="Not returned by the Discover API."
                          />
                        </div>
                        {candidate.reasons.length > 0 && (
                          <div className="mt-3">
                            <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                              Ranking reasons
                            </h4>
                            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-700">
                              {candidate.reasons.map((reason, index) => (
                                <li key={index}>{reason}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        <div className="mt-3">
                          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Supporting evidence
                          </h4>
                          {candidate.evidence.length ? (
                            <ul className="mt-1 space-y-1 text-sm">
                              {candidate.evidence.map((evidence) => (
                                <li
                                  key={evidence.evidence_id}
                                  className="text-slate-700"
                                >
                                  <span className="font-medium">
                                    {evidence.evidence_type}:
                                  </span>{" "}
                                  {evidence.source_url ? (
                                    <a
                                      href={evidence.source_url}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="text-blue-700 underline"
                                    >
                                      {evidence.source_citation}
                                    </a>
                                  ) : (
                                    evidence.source_citation
                                  )}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mt-1 text-sm text-amber-800">
                              Supporting evidence unavailable.
                            </p>
                          )}
                        </div>
                        {candidate.unknowns.map((unknown, index) => (
                          <p
                            key={index}
                            className="mt-2 text-xs text-amber-800"
                          >
                            UNKNOWN: {unknown}
                          </p>
                        ))}
                      </div>

                      <div className="flex shrink-0 flex-wrap items-center gap-2 lg:max-w-40">
                        <button
                          type="button"
                          onClick={() =>
                            router.push(
                              `/evaluate?asset=${encodeURIComponent(candidate.asset_id)}`,
                            )
                          }
                          className="rounded-md bg-blue-700 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                          Evaluate
                        </button>
                        <button
                          type="button"
                          aria-pressed={selectedForCompare.includes(
                            candidate.asset_id,
                          )}
                          onClick={() => toggleCompare(candidate.asset_id)}
                          className="rounded-md border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          {selectedForCompare.includes(candidate.asset_id)
                            ? "Remove compare"
                            : "Add to compare"}
                        </button>
                        <button
                          type="button"
                          disabled
                          title="Watch lists are not available in the current backend."
                          className="cursor-not-allowed rounded-md border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-400"
                        >
                          Watch unavailable
                        </button>
                        <button
                          type="button"
                          disabled
                          title="Opportunity creation is not available in the current backend."
                          className="cursor-not-allowed rounded-md border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-400"
                        >
                          Create unavailable
                        </button>
                        <span className="basis-full text-[11px] text-slate-500">
                          Watch and opportunity creation require backend
                          services not currently available.
                        </span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function Score({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="rounded-md bg-slate-50 p-3">
      <div className="text-[11px] font-medium text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-bold text-slate-900">{value}</div>
      <div className="mt-1 text-[11px] text-slate-600">{detail}</div>
    </div>
  );
}
