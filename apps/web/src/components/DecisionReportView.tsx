"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import { requestJson } from "../lib/api-client";

interface AssetOption {
  id: string;
  name: string;
}

interface Citation {
  evidence_id: string;
  source_reference: string;
  source_type: string;
  title: string;
  citation: string | null;
  url: string | null;
  excerpt: string | null;
  polarity: string | null;
}

interface ReportSection {
  section_id: string;
  title: string;
  status: string;
  source_data: unknown;
  claims: {
    classification: "FACT" | "INFERENCE" | "HYPOTHESIS" | "UNKNOWN";
    statement: string;
    evidence_ids: string[];
  }[];
  evidence_ids: string[];
  unknowns: string[];
  contradictory_evidence_ids: string[];
}

interface DecisionReport {
  asset_id: string;
  asset_name: string;
  tenant_id: string | null;
  evaluation_cutoff: string;
  sections: ReportSection[];
  citations: Citation[];
}

function parseAssets(value: unknown): AssetOption[] {
  if (
    !value ||
    typeof value !== "object" ||
    !("assets" in value) ||
    !Array.isArray(value.assets)
  ) {
    throw new Error("The canonical asset API returned an invalid catalog.");
  }
  return value.assets.flatMap((asset) => {
    if (
      asset &&
      typeof asset === "object" &&
      "id" in asset &&
      typeof asset.id === "string" &&
      "name" in asset &&
      typeof asset.name === "string"
    ) {
      return [{ id: asset.id, name: asset.name }];
    }
    return [];
  });
}

function parseReport(value: unknown, assetId: string): DecisionReport {
  if (!value || typeof value !== "object") {
    throw new Error("The decision report API returned an invalid report.");
  }
  const report = value as DecisionReport;
  if (
    report.asset_id !== assetId ||
    !Array.isArray(report.sections) ||
    !Array.isArray(report.citations)
  ) {
    throw new Error("The decision report API returned an invalid report.");
  }
  const requiredIds = [
    "executive_summary",
    "asset_overview",
    "biology",
    "preclinical",
    "clinical",
    "cns",
    "patient_match",
    "safety",
    "resistance",
    "combination",
    "competition",
    "regulatory",
    "ip",
    "licensing",
    "commercial",
    "recommendation",
    "why",
    "contradictory_evidence",
    "unknowns",
    "next_actions",
  ];
  const actualIds = report.sections.map((section) => section.section_id);
  const citationIds = new Set(
    report.citations.map((citation) => citation.evidence_id),
  );
  if (
    requiredIds.some((id) => !actualIds.includes(id)) ||
    actualIds.some((id) => !requiredIds.includes(id)) ||
    report.sections.some(
      (section) =>
        !Array.isArray(section.claims) ||
        !Array.isArray(section.evidence_ids) ||
        !Array.isArray(section.unknowns) ||
        !Array.isArray(section.contradictory_evidence_ids) ||
        section.evidence_ids.some((id) => !citationIds.has(id)) ||
        section.contradictory_evidence_ids.some((id) => !citationIds.has(id)) ||
        section.claims.some(
          (claim) =>
            !["FACT", "INFERENCE", "HYPOTHESIS", "UNKNOWN"].includes(
              claim.classification,
            ) || claim.evidence_ids.some((id) => !citationIds.has(id)),
        ),
    )
  ) {
    throw new Error(
      "The decision report contains missing sections or unresolved citations.",
    );
  }
  return report;
}

function safeExternalUrl(value: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

export function buildDecisionReportMarkdown(report: DecisionReport): string {
  const citationLines = report.citations.map(
    (citation) =>
      `- [${citation.evidence_id}] ${citation.source_reference}: ${citation.title}${citation.citation ? ` — ${citation.citation}` : ""}${citation.url ? ` (${citation.url})` : ""}`,
  );
  const sections = report.sections.map((section) => {
    const data =
      section.source_data === null || section.source_data === undefined
        ? "Not returned by the existing APIs."
        : `\`\`\`json\n${JSON.stringify(section.source_data, null, 2)}\n\`\`\``;
    const claims = section.claims
      .map(
        (claim) =>
          `- **${claim.classification}:** ${claim.statement}${claim.evidence_ids.length ? ` [${claim.evidence_ids.map((id) => `[${id}]`).join(", ")}]` : ""}`,
      )
      .join("\n");
    const citations = section.evidence_ids.map((id) => `- [${id}]`).join("\n");
    const contradictions = section.contradictory_evidence_ids
      .map((id) => `- [${id}]`)
      .join("\n");
    const unknowns = section.unknowns.map((item) => `- ${item}`).join("\n");
    return [
      `## ${section.title}`,
      `Status: **${section.status}**`,
      "",
      data,
      claims ? `\nClaims:\n${claims}` : "",
      citations ? `\nEvidence references:\n${citations}` : "",
      contradictions ? `\nContradictory evidence:\n${contradictions}` : "",
      unknowns ? `\nUnknowns:\n${unknowns}` : "",
    ]
      .filter(Boolean)
      .join("\n");
  });
  return [
    `# Decision Report: ${report.asset_name}`,
    `Canonical asset ID: ${report.asset_id}`,
    `Evaluation cutoff: ${report.evaluation_cutoff}`,
    "",
    ...sections,
    "## Citations",
    citationLines.length
      ? citationLines.join("\n")
      : "No evidence citations returned.",
    "",
    "This report preserves current API outputs; unknown or unavailable data is not a negative finding. Recommendation, WHY, and actions are returned by existing services.",
  ].join("\n\n");
}

export function DecisionReportView() {
  const [assets, setAssets] = useState<AssetOption[]>([]);
  const [assetId, setAssetId] = useState("");
  const [report, setReport] = useState<DecisionReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    requestJson<unknown>("/api/assets", { signal: controller.signal })
      .then((payload) => {
        const items = parseAssets(payload);
        setAssets(items);
        const requestedId = new URLSearchParams(window.location.search).get(
          "asset",
        );
        if (requestedId && items.some((item) => item.id === requestedId)) {
          setAssetId(requestedId);
        }
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Canonical assets are unavailable.",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  async function loadReport() {
    if (!assetId) return;
    setBuilding(true);
    setError(null);
    setReport(null);
    try {
      const response = await requestJson<unknown>(
        `/api/assets/${encodeURIComponent(assetId)}/report`,
      );
      setReport(parseReport(response, assetId));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Decision report is unavailable.",
      );
    } finally {
      setBuilding(false);
    }
  }

  const citationsById = useMemo(
    () =>
      new Map(
        (report?.citations ?? []).map((item) => [item.evidence_id, item]),
      ),
    [report],
  );

  function downloadReport() {
    if (!report) return;
    const blob = new Blob([buildDecisionReportMarkdown(report)], {
      type: "text/markdown",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.asset_id}-decision-report.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 text-slate-800 sm:px-6">
      <div className="mx-auto max-w-6xl">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Prompt 68 · Decision report
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Asset Decision Report
          </h1>
          <p className="mt-1 max-w-4xl text-sm text-slate-600">
            Report sections reuse canonical asset, evaluation, evidence, WHY,
            recommendation, and action outputs. Missing domains remain
            explicitly unknown or unavailable.
          </p>
        </header>

        <div className="mt-5 flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-end">
          <label className="grid flex-1 gap-1 text-sm font-semibold">
            Canonical asset
            <select
              value={assetId}
              onChange={(event) => setAssetId(event.target.value)}
              disabled={loading}
              className="min-h-10 rounded-md border border-slate-300 bg-white px-3 font-normal"
            >
              <option value="">Select an asset</option>
              {assets.map((asset) => (
                <option value={asset.id} key={asset.id}>
                  {asset.name} · {asset.id}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={loadReport}
            disabled={loading || building || !assetId}
            className="min-h-10 rounded-md bg-blue-700 px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            {building ? "Building report…" : "Load current report"}
          </button>
          {report && (
            <button
              type="button"
              onClick={downloadReport}
              className="min-h-10 rounded-md border border-slate-300 px-4 text-sm font-semibold"
            >
              Download Markdown
            </button>
          )}
        </div>

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-950"
          >
            {error}
          </div>
        )}
        {loading && (
          <p role="status" className="mt-4">
            Loading canonical assets…
          </p>
        )}

        {report && (
          <>
            <p className="mt-4 text-sm text-slate-600">
              {report.asset_name} · Canonical ID {report.asset_id} · Cutoff{" "}
              {report.evaluation_cutoff}
            </p>
            <div className="mt-3 space-y-3">
              {report.sections.map((section) => (
                <section
                  key={section.section_id}
                  className="rounded-xl border border-slate-200 bg-white p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="font-semibold text-slate-900">
                      {section.title}
                    </h2>
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold">
                      {section.status}
                    </span>
                  </div>
                  {section.source_data !== null &&
                  section.source_data !== undefined ? (
                    <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-xs">
                      {JSON.stringify(section.source_data, null, 2)}
                    </pre>
                  ) : (
                    <p className="mt-2 text-sm text-slate-600">
                      Information was not returned; this is not evidence of a
                      negative result.
                    </p>
                  )}
                  {section.claims.length > 0 && (
                    <ul className="mt-3 space-y-2 text-sm">
                      {section.claims.map((claim, index) => (
                        <li key={`${claim.classification}-${index}`}>
                          <span className="font-bold text-blue-800">
                            {claim.classification}
                          </span>
                          <span>: {claim.statement}</span>
                          {claim.evidence_ids.length > 0 && (
                            <span className="ml-1 text-xs text-slate-600">
                              [{claim.evidence_ids.join(", ")}]
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  {section.unknowns.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-sm text-amber-900">
                      {section.unknowns.map((unknown, index) => (
                        <li key={index}>{unknown}</li>
                      ))}
                    </ul>
                  )}
                  {section.evidence_ids.length > 0 && (
                    <ul className="mt-2 space-y-1 text-xs">
                      {section.evidence_ids.map((id) => {
                        const citation = citationsById.get(id);
                        const sourceUrl = safeExternalUrl(
                          citation?.url ?? null,
                        );
                        return (
                          <li key={id}>
                            {citation ? (
                              <a
                                href={sourceUrl}
                                target={sourceUrl ? "_blank" : undefined}
                                rel={sourceUrl ? "noreferrer" : undefined}
                                className="text-blue-700 underline"
                              >
                                [{citation.source_reference}] {citation.title}
                              </a>
                            ) : (
                              <span>Unresolved evidence reference: {id}</span>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>
              ))}
            </div>
            <section className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
              <h2 className="font-semibold">Citations</h2>
              {report.citations.length === 0 ? (
                <p className="mt-1 text-sm text-slate-600">
                  No internal evidence objects were returned for this asset.
                </p>
              ) : (
                <ul className="mt-2 space-y-3 text-sm">
                  {report.citations.map((citation) => (
                    <li key={citation.evidence_id}>
                      <p className="font-medium">
                        [{citation.source_reference}] {citation.title}
                      </p>
                      <p className="text-xs text-slate-600">
                        {citation.citation ?? citation.source_type} ·{" "}
                        {citation.evidence_id}
                      </p>
                      {citation.excerpt && (
                        <p className="mt-1 text-slate-700">
                          {citation.excerpt}
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
