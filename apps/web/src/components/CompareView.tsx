"use client";

import React, { useEffect, useMemo, useState } from "react";
import { requestJson } from "../lib/api-client";

interface AssetSummary {
  id: string;
  name: string;
  target?: string;
  modality?: string;
  stage?: string;
  primary_indication?: string;
}

interface ComparisonMetric {
  metric: string;
  status: string;
  raw_value: unknown;
  confidence: number | null;
  epistemic_class: string;
  supporting_evidence: Array<Record<string, unknown>>;
  provenance: Record<string, unknown>;
  source_output: Record<string, unknown>;
  unknowns: string[];
  rationale: string | null;
}

interface AssetDimensionComparison {
  asset_id: string;
  metrics: ComparisonMetric[];
}

interface DimensionComparison {
  dimension: string;
  comparison_metric: string | null;
  normalized_comparison: AssetDimensionComparison[];
  winner_asset_id: string | null;
  winner_status: string;
  confidence: number | null;
  supporting_evidence: Array<Record<string, unknown>>;
  contradictory_evidence: Array<Record<string, unknown>>;
  unknowns: string[];
  explanation: string;
  differentiator?: string | null;
}

interface CompareResponse {
  evaluation_cutoff: string;
  asset_ids: string[];
  dimensions: DimensionComparison[];
}

const DIMENSIONS = [
  "biology",
  "clinical",
  "CNS",
  "patient",
  "safety",
  "resistance",
  "competition",
  "licensing",
  "commercial",
] as const;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "UNKNOWN";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

function EvidenceList({ items }: { items: Array<Record<string, unknown>> }) {
  if (!items.length)
    return <p className="text-xs text-slate-600">Evidence unavailable.</p>;
  return (
    <ul className="list-disc space-y-1 pl-4 text-xs text-slate-700">
      {items.map((item, index) => (
        <li key={`${display(item.evidence_id)}-${index}`}>
          {display(
            item.citation ?? item.source_reference ?? item.source_type ?? item,
          )}
          <details className="mt-1">
            <summary className="cursor-pointer font-semibold">
              Evidence metadata and provenance
            </summary>
            <pre className="mt-1 whitespace-pre-wrap break-words">
              {JSON.stringify(item, null, 2)}
            </pre>
          </details>
        </li>
      ))}
    </ul>
  );
}

export function CompareView({
  initialAssetId,
  initialAsset2Id,
}: {
  initialAssetId?: string | null;
  initialAsset2Id?: string | null;
}) {
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [dimensions, setDimensions] = useState<string[]>([...DIMENSIONS]);
  const [cutoff, setCutoff] = useState("");
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    requestJson<{ assets: AssetSummary[] }>("/api/assets", {
      signal: controller.signal,
    })
      .then((catalog) => {
        setAssets(catalog.assets);
        const requestedIds = [initialAssetId, initialAsset2Id].filter(
          (assetId): assetId is string => Boolean(assetId),
        );
        if (requestedIds.length) {
          setSelectedIds(
            requestedIds.filter((assetId) =>
              catalog.assets.some((asset) => asset.id === assetId),
            ),
          );
        } else {
          setSelectedIds(catalog.assets.slice(0, 2).map((asset) => asset.id));
        }
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setCatalogError(errorMessage(caught));
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false);
      });
    return () => controller.abort();
  }, [initialAssetId, initialAsset2Id]);

  const selectedAssets = useMemo(
    () =>
      selectedIds
        .map((id) => assets.find((asset) => asset.id === id))
        .filter((asset): asset is AssetSummary => Boolean(asset)),
    [assets, selectedIds],
  );
  const visibleDimensions =
    result?.dimensions.filter((item) =>
      dimensions.some(
        (dimension) => dimension.toLowerCase() === item.dimension.toLowerCase(),
      ),
    ) ?? [];

  function toggleAsset(id: string) {
    setSelectedIds((current) => {
      const next = current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id];
      return next;
    });
    setResult(null);
    setError(null);
  }

  function toggleDimension(dimension: string) {
    setDimensions((current) =>
      current.includes(dimension)
        ? current.filter((item) => item !== dimension)
        : [...current, dimension],
    );
  }

  async function compareAssets(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedIds.length < 2 || selectedIds.length > 20) {
      setError("Select between 2 and 20 assets.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await requestJson<CompareResponse>("/api/compare", {
          method: "POST",
          body: { asset_ids: selectedIds, ...(cutoff ? { cutoff } : {}) },
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
            Prompt 59 Compare API
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Compare assets
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            API-reported differences, evidence gaps, and uncertainty. Missing
            evidence is not treated as negative evidence.
          </p>
        </header>

        <form
          onSubmit={compareAssets}
          className="mt-4 space-y-4 rounded-xl border border-slate-200 bg-white p-4"
        >
          <fieldset>
            <legend className="text-sm font-semibold text-slate-900">
              Assets (2–20)
            </legend>
            {catalogLoading ? (
              <p role="status" className="mt-2 text-sm text-slate-600">
                Loading canonical assets…
              </p>
            ) : catalogError ? (
              <p role="alert" className="mt-2 text-sm text-rose-800">
                Asset catalog unavailable: {catalogError}
              </p>
            ) : (
              <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {assets.map((asset) => (
                  <label
                    key={asset.id}
                    className="flex items-start gap-2 rounded-md border border-slate-200 p-2 text-sm"
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
                    <span>
                      <span className="block font-medium">{asset.name}</span>
                      <span className="block text-xs text-slate-500">
                        {asset.id}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p className="mt-2 text-xs text-slate-600">
              Selected: {selectedIds.length}
            </p>
          </fieldset>

          <fieldset>
            <legend className="text-sm font-semibold text-slate-900">
              Comparison dimensions
            </legend>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
              {DIMENSIONS.map((dimension) => (
                <label
                  key={dimension}
                  className="flex items-center gap-1.5 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={dimensions.includes(dimension)}
                    onChange={() => toggleDimension(dimension)}
                  />
                  {dimension}
                </label>
              ))}
            </div>
          </fieldset>

          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1 text-sm">
              Evaluation cutoff (optional)
              <input
                type="date"
                value={cutoff}
                onChange={(event) => setCutoff(event.target.value)}
                className="rounded border border-slate-300 px-2 py-1.5"
              />
            </label>
            <button
              type="submit"
              disabled={
                loading ||
                catalogLoading ||
                selectedIds.length < 2 ||
                dimensions.length === 0
              }
              className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              {loading ? "Comparing…" : "Compare"}
            </button>
          </div>
          {selectedAssets.length > 0 && (
            <div
              aria-label="Selected asset summary"
              className="flex flex-wrap gap-2"
            >
              {selectedAssets.map((asset) => (
                <span
                  key={asset.id}
                  className="rounded-full bg-slate-100 px-3 py-1 text-xs"
                >
                  {asset.name} · {asset.target ?? "UNKNOWN"} ·{" "}
                  {asset.stage ?? "UNKNOWN"}
                </span>
              ))}
            </div>
          )}
        </form>

        {error && (
          <p
            role="alert"
            className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-900"
          >
            {error}
          </p>
        )}
        {result && (
          <section aria-label="Comparison results" className="mt-5 space-y-4">
            <p className="text-sm text-slate-600">
              Evaluation cutoff: <strong>{result.evaluation_cutoff}</strong> ·
              Assets: {result.asset_ids.join(", ")}
            </p>
            {visibleDimensions.map((dimension) => (
              <article
                key={dimension.dimension}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
                  <div>
                    <h2 className="font-bold capitalize text-slate-900">
                      {dimension.dimension}
                    </h2>
                    <p className="mt-1 text-sm text-slate-700">
                      {dimension.explanation}
                    </p>
                    {dimension.differentiator && (
                      <p className="mt-1 text-sm">
                        <strong>Backend differentiator:</strong>{" "}
                        {dimension.differentiator}
                      </p>
                    )}
                  </div>
                  <div className="text-right text-xs">
                    <p className="font-semibold">
                      Backend outcome:{" "}
                      {dimension.winner_status.replaceAll("_", " ")}
                    </p>
                    <p>
                      Winner:{" "}
                      {dimension.winner_asset_id ?? "UNKNOWN / NONE IDENTIFIED"}
                    </p>
                    <p>
                      Confidence:{" "}
                      {dimension.confidence === null
                        ? "UNKNOWN"
                        : `${Math.round(dimension.confidence * 100)}%`}
                    </p>
                  </div>
                </div>
                <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Side-by-side metrics (each asset retains its own evidence
                  state)
                </p>
                <div className="mt-2 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {dimension.normalized_comparison.map((assetResult) => {
                    const asset = assets.find(
                      (item) => item.id === assetResult.asset_id,
                    );
                    return (
                      <section
                        key={assetResult.asset_id}
                        className="rounded-lg border border-slate-200 bg-slate-50 p-3"
                      >
                        <h3 className="font-semibold text-slate-900">
                          {asset?.name ?? assetResult.asset_id}
                        </h3>
                        {assetResult.metrics.map((metric, index) => (
                          <div
                            key={`${metric.metric}-${index}`}
                            className="mt-3 border-t border-slate-200 pt-2"
                          >
                            <p className="text-sm font-medium">
                              {metric.metric.replaceAll("_", " ")}
                            </p>
                            <p className="mt-1 text-xs">
                              <strong>Value:</strong>{" "}
                              {display(metric.raw_value)}
                            </p>
                            <p className="text-xs">
                              <strong>Evidence state:</strong>{" "}
                              {metric.status.replaceAll("_", " ")}
                            </p>
                            <p className="text-xs">
                              <strong>Confidence:</strong>{" "}
                              {metric.confidence === null
                                ? "UNKNOWN"
                                : `${Math.round(metric.confidence * 100)}%`}
                            </p>
                            <p className="text-xs">
                              <strong>Evidence maturity:</strong>{" "}
                              {metric.epistemic_class || "UNKNOWN"}
                            </p>
                            {metric.rationale && (
                              <p className="mt-1 text-xs text-slate-700">
                                {metric.rationale}
                              </p>
                            )}
                            {metric.unknowns.length > 0 && (
                              <ul className="mt-1 list-disc pl-4 text-xs text-amber-900">
                                {metric.unknowns.map((unknown, i) => (
                                  <li key={`${i}-${unknown}`}>{unknown}</li>
                                ))}
                              </ul>
                            )}
                            <details className="mt-2 text-xs">
                              <summary className="cursor-pointer font-semibold">
                                Evidence & provenance
                              </summary>
                              <div className="mt-2 space-y-2">
                                <EvidenceList
                                  items={metric.supporting_evidence}
                                />
                                <p>
                                  <strong>Provenance:</strong>{" "}
                                  {Object.keys(metric.provenance).length
                                    ? display(metric.provenance)
                                    : "UNKNOWN"}
                                </p>
                                {Object.keys(asRecord(metric.source_output))
                                  .length > 0 && (
                                  <p>
                                    <strong>Source output:</strong>{" "}
                                    {display(metric.source_output)}
                                  </p>
                                )}
                              </div>
                            </details>
                          </div>
                        ))}
                      </section>
                    );
                  })}
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div>
                    <h3 className="text-xs font-semibold">
                      Dimension supporting evidence
                    </h3>
                    <EvidenceList items={dimension.supporting_evidence} />
                  </div>
                  <div>
                    <h3 className="text-xs font-semibold">
                      Contradictory evidence
                    </h3>
                    <EvidenceList items={dimension.contradictory_evidence} />
                  </div>
                </div>
                {dimension.unknowns.length > 0 && (
                  <ul className="mt-3 list-disc rounded bg-amber-50 p-3 pl-7 text-xs text-amber-950">
                    {dimension.unknowns.map((unknown, index) => (
                      <li key={`${index}-${unknown}`}>{unknown}</li>
                    ))}
                  </ul>
                )}
              </article>
            ))}
          </section>
        )}
      </div>
    </div>
  );
}
