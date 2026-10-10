"use client";

import React, { useState } from "react";
import { requestJson } from "../lib/api-client";

interface CohortQuery {
  disease_subtype: string;
  mutation: string | null;
  expression: string | null;
  amplification: string | null;
  protein_expression: string | null;
  biomarker: string | null;
  prior_therapy: string[];
  resistance_state: string | null;
  line_of_therapy: string | null;
  cns_status: string | null;
}

interface RankedCandidate {
  asset_id: string;
  asset_name: string;
  match_score: number;
  rank: number;
  population_fit: string;
  mechanistic_synergy: string;
  evidence_citations: string[];
  contradictory_evidence?: unknown[];
  unknowns?: string[];
}

interface IntelligenceValue {
  name?: string;
  value?: unknown;
  status?: string;
  epistemic_class?: string;
  confidence?: number | null;
  supporting_evidence?: unknown[];
  provenance?: Record<string, unknown>;
  reason?: string | null;
}

interface PatientIntelligence {
  status?: string;
  data?: {
    primary_population?: IntelligenceValue;
    secondary_population?: IntelligenceValue;
    low_likelihood_population?: IntelligenceValue;
    biomarker_strategy?: IntelligenceValue;
    patient_match_score?: IntelligenceValue;
    confidence?: IntelligenceValue;
    evidence?: unknown[];
    unknowns?: string[];
    contradictory_evidence?: unknown[];
    ml_component?: {
      available?: boolean;
      model_name?: string;
      model_version?: string | null;
      feature_version?: string | null;
      reason?: string | null;
    };
    epistemic_classes?: string[];
  };
  reason?: string | null;
}

interface ScenarioResponse {
  query: CohortQuery;
  best_matched_asset: Record<string, unknown>;
  ranked_candidates: RankedCandidate[];
  interpretation: string;
  disclaimer: string;
  evaluated_at: string;
}

const FILTERS = [
  ["disease_subtype", "Disease / subtype"],
  ["mutation", "Mutation"],
  ["biomarker", "Biomarker"],
  ["expression", "Expression"],
  ["amplification", "Amplification"],
  ["protein_expression", "Protein expression"],
  ["prior_therapy", "Prior treatment(s), comma-separated"],
  ["line_of_therapy", "Line of therapy"],
  ["resistance_state", "Resistance state"],
  ["cns_status", "CNS status"],
] as const;

type FilterName = (typeof FILTERS)[number][0];
type FilterValues = Record<FilterName, string>;

const EMPTY_FILTERS: FilterValues = {
  disease_subtype: "",
  mutation: "",
  biomarker: "",
  expression: "",
  amplification: "",
  protein_expression: "",
  prior_therapy: "",
  line_of_therapy: "",
  resistance_state: "",
  cns_status: "",
};

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "UNKNOWN";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function confidenceDisplay(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value * 100)}%`
    : "UNKNOWN";
}

function evidenceReferences(values: unknown[] | undefined): string[] {
  if (!values?.length) return [];
  return values.map((item) => {
    if (typeof item === "string") return item;
    if (!item || typeof item !== "object") return display(item);
    const record = item as Record<string, unknown>;
    return display(
      record.citation ?? record.source_reference ?? record.evidence_id ?? item,
    );
  });
}

function epistemicLabel(value: unknown): string {
  const labels: Record<string, string> = {
    FACT: "OBSERVED (API: FACT)",
    DERIVED_FEATURE: "DERIVED (API: DERIVED_FEATURE)",
    ML_PREDICTION: "PREDICTED (API: ML_PREDICTION)",
    AI_INFERENCE: "INFERRED (API: AI_INFERENCE)",
    HYPOTHESIS: "HYPOTHESIS",
    UNKNOWN: "UNKNOWN",
  };
  return typeof value === "string" ? (labels[value] ?? value) : "UNKNOWN";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

function IntelligenceDetail({
  label,
  value,
}: {
  label: string;
  value: IntelligenceValue | undefined;
}) {
  if (!value) {
    return (
      <div>
        <p>
          <strong>{label} state:</strong> UNKNOWN / NOT RETURNED
        </p>
      </div>
    );
  }
  const confidence = confidenceDisplay(value.confidence);
  const evidence = evidenceReferences(value.supporting_evidence);
  const hasEvidenceMetadata = value.supporting_evidence?.some(
    (item) => item !== null && typeof item === "object",
  );
  return (
    <div>
      <p>
        <strong>{label} state:</strong> {value.status ?? "UNKNOWN"} ·{" "}
        {epistemicLabel(value.epistemic_class)}
      </p>
      <p>
        <strong>{label}:</strong> {display(value.value)}
      </p>
      <p>
        <strong>{label} confidence:</strong> {confidence}
      </p>
      {value.reason && (
        <p>
          <strong>{label} reason:</strong> {value.reason}
        </p>
      )}
      {evidence.length > 0 && (
        <ul className="list-disc pl-4">
          {evidence.map((item, index) => (
            <li key={`${index}-${item}`}>{item}</li>
          ))}
        </ul>
      )}
      {hasEvidenceMetadata && (
        <details>
          <summary className="cursor-pointer font-semibold">
            Supporting evidence metadata and provenance
          </summary>
          <pre className="mt-1 whitespace-pre-wrap break-words">
            {JSON.stringify(value.supporting_evidence, null, 2)}
          </pre>
        </details>
      )}
      {value.provenance && Object.keys(value.provenance).length > 0 && (
        <p>
          <strong>{label} provenance:</strong> {display(value.provenance)}
        </p>
      )}
    </div>
  );
}

export function PatientMatchView() {
  const [filters, setFilters] = useState<FilterValues>(EMPTY_FILTERS);
  const [result, setResult] = useState<ScenarioResponse | null>(null);
  const [intelligence, setIntelligence] = useState<
    Record<string, PatientIntelligence>
  >({});
  const [intelligenceErrors, setIntelligenceErrors] = useState<
    Record<string, string>
  >({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setFilter(name: FilterName, value: string) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  async function submitScenario(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const hasFilter = Object.values(filters).some((value) => value.trim());
    if (!hasFilter) {
      setError("Enter at least one cohort filter before searching.");
      return;
    }

    const query: CohortQuery = {
      disease_subtype: filters.disease_subtype.trim(),
      mutation: filters.mutation.trim() || null,
      biomarker: filters.biomarker.trim() || null,
      expression: filters.expression.trim() || null,
      amplification: filters.amplification.trim() || null,
      protein_expression: filters.protein_expression.trim() || null,
      prior_therapy: filters.prior_therapy
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      line_of_therapy: filters.line_of_therapy.trim() || null,
      resistance_state: filters.resistance_state.trim() || null,
      cns_status: filters.cns_status.trim() || null,
    };

    setLoading(true);
    setError(null);
    setResult(null);
    setIntelligence({});
    setIntelligenceErrors({});
    try {
      const response = await requestJson<ScenarioResponse>(
        "/api/patient-match/scenario",
        {
          method: "POST",
          body: query,
        },
      );
      setResult(response);
      const reports = await Promise.allSettled(
        response.ranked_candidates.map(async (candidate) => {
          const report = await requestJson<PatientIntelligence>(
            `/api/patient-match/intelligence/${encodeURIComponent(candidate.asset_id)}`,
          );
          return [candidate.asset_id, report] as const;
        }),
      );
      const available: Record<string, PatientIntelligence> = {};
      const unavailable: Record<string, string> = {};
      reports.forEach((report, index) => {
        const candidateId = response.ranked_candidates[index]?.asset_id;
        if (report.status === "fulfilled")
          available[report.value[0]] = report.value[1];
        else if (candidateId)
          unavailable[candidateId] = errorMessage(report.reason);
      });
      setIntelligence(available);
      setIntelligenceErrors(unavailable);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 text-slate-800 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Existing PatientMatch scenario and intelligence APIs
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            PatientMatch population intelligence
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Drug-development cohort analysis only. This is not a
            patient-specific clinical treatment recommendation.
          </p>
          <p className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
            Validation limitation: the current scenario endpoint ranks a fixed
            benchmark asset set with deterministic keyword rules. Its ranks and
            match scores are API outputs, not calibrated or clinically validated
            predictions. Review the returned evidence and unknowns before
            drawing conclusions.
          </p>
        </header>

        <form
          onSubmit={submitScenario}
          className="mt-4 rounded-xl border border-slate-200 bg-white p-4"
        >
          <fieldset>
            <legend className="font-semibold text-slate-900">
              Cohort filters
            </legend>
            <p className="mt-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
              Backend limitation: the current scenario matcher uses disease
              subtype, mutation, biomarker, resistance state, and prior
              therapies. Expression, amplification, protein expression, line of
              therapy, and CNS status are accepted by the API but are not
              separate matching inputs and will not affect its ranks or scores.
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {FILTERS.map(([name, label]) => (
                <label
                  key={name}
                  className="grid gap-1 text-xs font-semibold text-slate-700"
                >
                  {label}
                  <input
                    type="text"
                    value={filters[name]}
                    onChange={(event) => setFilter(name, event.target.value)}
                    className="rounded border border-slate-300 px-2.5 py-2 text-sm font-normal"
                  />
                </label>
              ))}
            </div>
          </fieldset>
          <button
            type="submit"
            disabled={loading}
            className="mt-4 rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {loading ? "Evaluating cohort…" : "Rank populations"}
          </button>
        </form>

        {loading && (
          <p role="status" className="mt-4 text-sm text-slate-600">
            Loading backend cohort ranking and evidence…
          </p>
        )}
        {error && (
          <p
            role="alert"
            className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-900"
          >
            {error}
          </p>
        )}

        {result && (
          <section
            aria-label="Ranked patient populations"
            className="mt-5 space-y-4"
          >
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-950">
              <p>
                <strong>Backend interpretation:</strong>{" "}
                {result.interpretation || "UNKNOWN"}
              </p>
              <p className="mt-1">{result.disclaimer}</p>
              <p className="mt-1 text-xs">
                Evaluated at: {result.evaluated_at}
              </p>
            </div>
            {result.ranked_candidates.map((candidate) => {
              const report = intelligence[candidate.asset_id];
              const data = report?.data;
              const score = data?.patient_match_score;
              const confidence = data?.confidence;
              const model = data?.ml_component;
              const primary = data?.primary_population;
              const citations = [
                ...candidate.evidence_citations,
                ...evidenceReferences(primary?.supporting_evidence),
                ...evidenceReferences(data?.evidence),
              ];
              const distinctCitations = [
                ...new Set(citations.filter((item) => item !== "UNKNOWN")),
              ];
              return (
                <article
                  key={candidate.asset_id}
                  className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Backend rule-based benchmark rank #{candidate.rank}
                      </p>
                      <h2 className="mt-1 text-lg font-bold text-slate-900">
                        {candidate.asset_name}
                      </h2>
                      <p className="mt-1 text-sm">
                        <strong>Patient population fit:</strong>{" "}
                        {candidate.population_fit || "UNKNOWN"}
                      </p>
                      <p className="mt-1 text-sm">
                        <strong>Rationale:</strong>{" "}
                        {candidate.mechanistic_synergy || "UNKNOWN"}
                      </p>
                    </div>
                    <div className="rounded bg-slate-50 p-3 text-sm">
                      <p>
                        <strong>API heuristic cohort match score:</strong>{" "}
                        {display(candidate.match_score)}
                      </p>
                      <p>
                        <strong>Intelligence confidence:</strong>{" "}
                        {confidenceDisplay(confidence?.value)}
                        {" · "}
                        {confidence?.status ?? "UNKNOWN"}
                      </p>
                    </div>
                  </div>

                  {intelligenceErrors[candidate.asset_id] && (
                    <p
                      role="alert"
                      className="mt-3 rounded bg-rose-50 p-2 text-xs text-rose-900"
                    >
                      Intelligence detail unavailable:{" "}
                      {intelligenceErrors[candidate.asset_id]}
                    </p>
                  )}
                  {report && (
                    <div className="mt-3 space-y-3 border-t border-slate-100 pt-3">
                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="space-y-2 text-xs">
                          <IntelligenceDetail
                            label="Primary population"
                            value={primary}
                          />
                          <IntelligenceDetail
                            label="Secondary population"
                            value={data?.secondary_population}
                          />
                          <IntelligenceDetail
                            label="Low-likelihood population"
                            value={data?.low_likelihood_population}
                          />
                          <IntelligenceDetail
                            label="Biomarker strategy"
                            value={data?.biomarker_strategy}
                          />
                          <p>
                            <strong>API match score state:</strong>{" "}
                            {score?.status ?? "UNKNOWN"} ·{" "}
                            {epistemicLabel(score?.epistemic_class)}
                          </p>
                          <p>
                            <strong>API match score value:</strong>{" "}
                            {display(score?.value)}
                          </p>
                          {(primary?.reason || score?.reason) && (
                            <p>
                              <strong>Unknown / reason:</strong>{" "}
                              {primary?.reason ?? score?.reason}
                            </p>
                          )}
                        </div>
                        <div className="space-y-2 text-xs">
                          <p>
                            <strong>Population intelligence state:</strong>{" "}
                            {report.status ?? "UNKNOWN"}
                          </p>
                          <p>
                            <strong>Model state:</strong>{" "}
                            {model?.available ? "AVAILABLE" : "UNAVAILABLE"}
                          </p>
                          <p>
                            <strong>Model/version:</strong>{" "}
                            {model?.model_name ?? "UNKNOWN"} /{" "}
                            {model?.model_version ?? "UNKNOWN"}
                          </p>
                          <p>
                            <strong>Model feature version:</strong>{" "}
                            {model?.feature_version ?? "UNKNOWN"}
                          </p>
                          {model?.reason && (
                            <p>
                              <strong>Model reason:</strong> {model.reason}
                            </p>
                          )}
                          <p>
                            <strong>Epistemic classes reported:</strong>{" "}
                            {data?.epistemic_classes
                              ?.map(epistemicLabel)
                              .join(", ") || "UNKNOWN"}
                          </p>
                        </div>
                      </div>
                      {data?.unknowns?.length ? (
                        <ul
                          aria-label="PatientMatch uncertainty and unknowns"
                          className="list-disc rounded bg-amber-50 p-3 pl-7 text-xs text-amber-950"
                        >
                          {data.unknowns.map((unknown, index) => (
                            <li key={`${index}-${unknown}`}>{unknown}</li>
                          ))}
                        </ul>
                      ) : null}
                      <div>
                        <h3 className="text-xs font-semibold text-slate-800">
                          Contradictory evidence
                        </h3>
                        {data?.contradictory_evidence?.length ? (
                          <ul className="mt-1 list-disc pl-4 text-xs">
                            {data.contradictory_evidence.map((item, index) => (
                              <li key={index}>{display(item)}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="mt-1 text-xs text-slate-600">
                            Not returned by the PatientMatch intelligence API;
                            absence is not evidence that contradictions do not
                            exist.
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  <div className="mt-3 grid gap-3 border-t border-slate-100 pt-3 md:grid-cols-2">
                    <div>
                      <h3 className="text-xs font-semibold text-slate-800">
                        Supporting evidence
                      </h3>
                      {distinctCitations.length ? (
                        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs">
                          {distinctCitations.map((citation, index) => (
                            <li key={`${index}-${citation}`}>{citation}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="mt-1 text-xs text-slate-600">
                          Evidence unavailable / UNKNOWN.
                        </p>
                      )}
                    </div>
                    <div>
                      <h3 className="text-xs font-semibold text-slate-800">
                        Contradictory evidence
                      </h3>
                      {candidate.contradictory_evidence?.length ? (
                        <ul className="mt-1 list-disc pl-4 text-xs">
                          {candidate.contradictory_evidence.map(
                            (item, index) => (
                              <li key={index}>{display(item)}</li>
                            ),
                          )}
                        </ul>
                      ) : (
                        <p className="mt-1 text-xs text-slate-600">
                          Not returned by this scenario API; absence is not
                          negative evidence.
                        </p>
                      )}
                    </div>
                  </div>
                  {data?.evidence?.length ? (
                    <details className="mt-3 border-t border-slate-100 pt-3 text-xs">
                      <summary className="cursor-pointer font-semibold">
                        PatientMatch evidence metadata and provenance
                      </summary>
                      <pre className="mt-2 whitespace-pre-wrap break-words">
                        {JSON.stringify(data.evidence, null, 2)}
                      </pre>
                    </details>
                  ) : null}
                  {candidate.unknowns?.length ? (
                    <ul className="mt-3 list-disc rounded bg-amber-50 p-3 pl-7 text-xs text-amber-950">
                      {candidate.unknowns.map((unknown, index) => (
                        <li key={`${index}-${unknown}`}>{unknown}</li>
                      ))}
                    </ul>
                  ) : null}
                </article>
              );
            })}
            {!result.ranked_candidates.length && (
              <p className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-600">
                No populations were returned by the backend for this cohort.
              </p>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
