"use client";

import React, { useEffect, useState } from "react";
import { requestJson } from "../lib/api-client";

interface AssetSummary {
  id: string;
  name: string;
}

const OUTCOME_TYPES = [
  "trial_readout",
  "trial_failure",
  "regulatory_approval",
  "complete_response_letter",
  "advisory_committee_vote",
  "company_acquisition",
  "licensing_deal",
  "biomarker_discovery",
  "clinical_hold",
  "black_box_warning",
] as const;

interface BacktestResponse {
  cutoff: string;
  evaluation_window_end: string;
  outcome_type: string | null;
  candidates: Array<Record<string, unknown>>;
  metrics: Record<string, unknown>;
  ranking: Record<string, unknown>;
  enrichment: Record<string, unknown>;
  calibration: Record<string, unknown>;
  counterfactual_status: string;
  unknowns: string[];
  limitations: string[];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "UNKNOWN";
  if (typeof value === "boolean") return value ? "YES" : "NO";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function confidenceDisplay(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value)
    ? `${Math.round(value * 100)}%`
    : "UNKNOWN";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

function Field({ label, value }: { label: string; value: unknown }) {
  return (
    <p className="break-words text-xs">
      <strong>{label}:</strong> {display(value)}
    </p>
  );
}

function JsonRows({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (!value.length)
      return (
        <p className="text-xs text-slate-600">UNKNOWN — no items returned.</p>
      );
    return (
      <ul className="space-y-2">
        {value.map((item, index) => (
          <li key={index} className="rounded bg-slate-50 p-2 text-xs">
            {typeof item === "object" && item !== null ? (
              <JsonRows value={item} />
            ) : (
              display(item)
            )}
          </li>
        ))}
      </ul>
    );
  }
  if (value && typeof value === "object") {
    return (
      <dl className="grid gap-x-3 gap-y-1 sm:grid-cols-[minmax(8rem,0.35fr)_1fr]">
        {Object.entries(value as Record<string, unknown>).map(
          ([key, nested]) => (
            <React.Fragment key={key}>
              <dt className="break-words text-xs font-semibold text-slate-600">
                {key.replaceAll("_", " ")}
              </dt>
              <dd className="min-w-0 break-words text-xs text-slate-800">
                {nested && typeof nested === "object" ? (
                  <JsonRows value={nested} />
                ) : (
                  display(nested)
                )}
              </dd>
            </React.Fragment>
          ),
        )}
      </dl>
    );
  }
  return <p className="text-xs">{display(value)}</p>;
}

function MetricPanel({
  title,
  value,
  statusKeys = ["status"],
}: {
  title: string;
  value: Record<string, unknown>;
  statusKeys?: string[];
}) {
  const status = statusKeys
    .map((key) => value[key])
    .find((item) => typeof item === "string");
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-slate-900">{title}</h3>
        <span className="rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold">
          {display(status)}
        </span>
      </div>
      <div className="mt-2">
        <JsonRows value={value} />
      </div>
    </article>
  );
}

export interface BacktestViewProps {
  assets?: AssetSummary[];
}

export function BacktestView({ assets: suppliedAssets }: BacktestViewProps) {
  const [assets, setAssets] = useState<AssetSummary[]>(suppliedAssets ?? []);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(!suppliedAssets);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [cutoff, setCutoff] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [outcomeType, setOutcomeType] = useState("");
  const [modelName, setModelName] = useState("");
  const [modelVersion, setModelVersion] = useState("");
  const [featureVersion, setFeatureVersion] = useState("");
  const [topK, setTopK] = useState("5");
  const [threshold, setThreshold] = useState("0.5");
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (suppliedAssets) {
      setAssets(suppliedAssets);
      setCatalogLoading(false);
      return;
    }
    const controller = new AbortController();
    requestJson<{ assets: AssetSummary[] }>("/api/assets", {
      signal: controller.signal,
    })
      .then((catalog) => {
        setAssets(catalog.assets);
        setSelectedIds(catalog.assets.slice(0, 1).map((asset) => asset.id));
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setCatalogError(errorMessage(caught));
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false);
      });
    return () => controller.abort();
  }, [suppliedAssets]);

  function toggleAsset(id: string) {
    setSelectedIds((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : current.length < 20
          ? [...current, id]
          : current,
    );
    setResult(null);
    setError(null);
  }

  async function runBacktest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedIds.length) {
      setError("Select at least one asset or universe member.");
      return;
    }
    if (!cutoff) {
      setError("Select a prediction cutoff date.");
      return;
    }
    const parsedTopK = Number(topK);
    const parsedThreshold = Number(threshold);
    if (!Number.isInteger(parsedTopK) || parsedTopK < 1 || parsedTopK > 20) {
      setError("Top K must be an integer from 1 to 20.");
      return;
    }
    if (
      !Number.isFinite(parsedThreshold) ||
      parsedThreshold < 0 ||
      parsedThreshold > 1
    ) {
      setError("Decision threshold must be between 0 and 1.");
      return;
    }

    const body = {
      asset_ids: selectedIds,
      cutoff,
      ...(windowEnd ? { evaluation_window_end: windowEnd } : {}),
      ...(outcomeType ? { outcome_type: outcomeType } : {}),
      ...(modelName.trim() ? { model_name: modelName.trim() } : {}),
      ...(modelVersion.trim() ? { model_version: modelVersion.trim() } : {}),
      ...(featureVersion.trim()
        ? { feature_version: featureVersion.trim() }
        : {}),
      top_k: parsedTopK,
      decision_threshold: parsedThreshold,
    };
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await requestJson<BacktestResponse>("/api/backtest", {
          method: "POST",
          body,
        }),
      );
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 text-slate-800 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Prompt 60 Backtest API
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Historical backtest
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Point-in-time predictions and later-observed outcomes are separated
            below. Sensitivity results are hypothetical, not historical
            observations.
          </p>
          <p className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950">
            This integration currently uses a fixture-backed asset catalog and
            seeded temporal outcome records. Treat it as an API/integration
            workflow, not a validated historical ML benchmark. Only eligible
            stored predictions with compatible, evidence-backed labels are
            scored; missing history remains unavailable.
          </p>
        </header>

        <form
          onSubmit={runBacktest}
          className="mt-4 space-y-4 rounded-xl border border-slate-200 bg-white p-4"
        >
          <fieldset>
            <legend className="font-semibold text-slate-900">
              Asset / universe (1–20)
            </legend>
            {catalogLoading ? (
              <p role="status" className="mt-2 text-sm">
                Loading canonical assets…
              </p>
            ) : null}
            {catalogError && (
              <p role="alert" className="mt-2 text-sm text-rose-800">
                Asset catalog unavailable: {catalogError}
              </p>
            )}
            <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {assets.map((asset) => (
                <label
                  key={asset.id}
                  className="flex items-center gap-2 rounded border border-slate-200 p-2 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(asset.id)}
                    disabled={
                      !selectedIds.includes(asset.id) &&
                      selectedIds.length >= 20
                    }
                    onChange={() => toggleAsset(asset.id)}
                  />
                  {asset.name}{" "}
                  <span className="text-xs text-slate-500">({asset.id})</span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <label className="grid gap-1 text-xs font-semibold">
              Prediction cutoff
              <input
                required
                type="date"
                value={cutoff}
                onChange={(event) => setCutoff(event.target.value)}
                className="rounded border border-slate-300 px-2 py-2 text-sm font-normal"
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold">
              Evaluation window end (optional)
              <input
                type="date"
                value={windowEnd}
                onChange={(event) => setWindowEnd(event.target.value)}
                className="rounded border border-slate-300 px-2 py-2 text-sm font-normal"
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold">
              Outcome type (optional)
              <select
                value={outcomeType}
                onChange={(event) => setOutcomeType(event.target.value)}
                className="rounded border border-slate-300 bg-slate-50 px-2 py-2 text-sm font-normal"
              >
                <option value="">All outcome types</option>
                {OUTCOME_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-xs font-semibold">
              Model name (optional)
              <input
                type="text"
                value={modelName}
                onChange={(event) => setModelName(event.target.value)}
                className="rounded border border-slate-300 px-2 py-2 text-sm font-normal"
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold">
              Model version (optional)
              <input
                type="text"
                value={modelVersion}
                onChange={(event) => setModelVersion(event.target.value)}
                className="rounded border border-slate-300 px-2 py-2 text-sm font-normal"
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold">
              Feature version (optional)
              <input
                type="text"
                value={featureVersion}
                onChange={(event) => setFeatureVersion(event.target.value)}
                className="rounded border border-slate-300 px-2 py-2 text-sm font-normal"
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold">
              Top K
              <input
                type="number"
                min="1"
                max="20"
                step="1"
                value={topK}
                onChange={(event) => setTopK(event.target.value)}
                className="rounded border border-slate-300 px-2 py-2 text-sm font-normal"
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold">
              Decision threshold
              <input
                type="number"
                min="0"
                max="1"
                step="0.01"
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
                className="rounded border border-slate-300 px-2 py-2 text-sm font-normal"
              />
            </label>
          </div>
          <button
            type="submit"
            disabled={loading || catalogLoading}
            className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {loading ? "Running backtest…" : "Run backtest"}
          </button>
        </form>

        {loading && (
          <p role="status" className="mt-4 text-sm text-slate-600">
            Backtest is running…
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
          <section aria-label="Backtest results" className="mt-5 space-y-4">
            <div className="rounded-lg border border-slate-300 bg-slate-100 p-3 text-sm">
              <strong>Prediction cutoff:</strong> {result.cutoff} ·{" "}
              <strong>Evaluation window end:</strong>{" "}
              {result.evaluation_window_end} · <strong>Outcome type:</strong>{" "}
              {result.outcome_type ?? "UNKNOWN"}
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              {result.candidates.map((rawCandidate, index) => {
                const candidate = asRecord(rawCandidate);
                const prediction = asRecord(candidate.prediction);
                const outcomes = Array.isArray(candidate.observed_outcomes)
                  ? candidate.observed_outcomes
                  : [];
                const comparison = asRecord(candidate.prediction_outcome);
                const sensitivity = asRecord(candidate.sensitivity_analysis);
                const explicitCorrectness =
                  comparison.correctness ??
                  comparison.is_correct ??
                  comparison.correct;
                return (
                  <article
                    key={`${display(candidate.asset_id)}-${index}`}
                    className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"
                  >
                    <header className="border-b border-slate-200 bg-slate-50 p-4">
                      <h2 className="font-bold text-slate-900">
                        {display(candidate.asset_name)}
                      </h2>
                      <p className="text-xs text-slate-600">
                        {display(candidate.asset_id)}
                      </p>
                    </header>
                    <section
                      aria-label="Known at cutoff"
                      className="border-b-4 border-blue-700 p-4"
                    >
                      <h3 className="text-sm font-bold uppercase tracking-wide text-blue-900">
                        KNOWN AT CUTOFF
                      </h3>
                      <p className="mb-2 text-xs text-slate-600">
                        Inputs and prediction available as of{" "}
                        {display(prediction.prediction_cutoff ?? result.cutoff)}
                        .
                      </p>
                      <div className="space-y-1">
                        <Field
                          label="Prediction status"
                          value={prediction.status}
                        />
                        <Field
                          label="Prediction type"
                          value={prediction.prediction_type}
                        />
                        <Field
                          label="Predicted value"
                          value={prediction.predicted_value}
                        />
                        <Field
                          label="Predicted class"
                          value={prediction.predicted_class}
                        />
                        <Field
                          label="Confidence"
                          value={confidenceDisplay(prediction.confidence)}
                        />
                        <Field
                          label="Model / version"
                          value={`${display(prediction.model_name)} / ${display(prediction.model_version)}`}
                        />
                        <Field
                          label="Feature version"
                          value={prediction.feature_version}
                        />
                        <Field
                          label="Prediction correctness (API field)"
                          value={explicitCorrectness ?? "NOT RETURNED BY API"}
                        />
                      </div>
                      <h4 className="mt-3 text-xs font-semibold">
                        Information available then — feature lineage
                      </h4>
                      <JsonRows value={prediction.feature_lineage} />
                      <h4 className="mt-3 text-xs font-semibold">
                        Prediction provenance
                      </h4>
                      <JsonRows value={prediction.provenance} />
                    </section>

                    <section
                      aria-label="Learned later"
                      className="border-b-4 border-amber-600 bg-amber-50/40 p-4"
                    >
                      <h3 className="text-sm font-bold uppercase tracking-wide text-amber-950">
                        LEARNED LATER
                      </h3>
                      <p className="mb-2 text-xs text-slate-700">
                        Observed outcomes are displayed separately from
                        cutoff-time information.
                      </p>
                      <JsonRows value={outcomes} />
                      <h4 className="mt-3 text-xs font-semibold">
                        Prediction/outcome comparability
                      </h4>
                      <JsonRows value={comparison} />
                    </section>

                    <section aria-label="Sensitivity analysis" className="p-4">
                      <h3 className="text-sm font-bold uppercase tracking-wide text-purple-900">
                        HYPOTHETICAL — SENSITIVITY ANALYSIS
                      </h3>
                      <JsonRows value={sensitivity} />
                    </section>
                  </article>
                );
              })}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <MetricPanel
                title="Model performance / label sufficiency"
                value={result.metrics}
                statusKeys={["label_status"]}
              />
              <MetricPanel title="Ranking" value={result.ranking} />
              <MetricPanel title="Enrichment" value={result.enrichment} />
              <MetricPanel title="Calibration" value={result.calibration} />
            </div>
            <MetricPanel
              title="Evidence, provenance & temporal limitations"
              value={{
                counterfactual_status: result.counterfactual_status,
                unknowns: result.unknowns,
                limitations: result.limitations,
              }}
              statusKeys={["counterfactual_status"]}
            />
          </section>
        )}
      </div>
    </div>
  );
}
