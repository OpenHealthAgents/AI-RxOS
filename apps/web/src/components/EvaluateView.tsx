"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useWorkspace } from "../context/WorkspaceContext";

type JsonRecord = Record<string, unknown>;

interface AssetSummary {
  id: string;
  name: string;
  target?: string;
  modality?: string;
  stage?: string;
  primary_indication?: string;
}

interface AssetCatalog {
  tenant_id: string | null;
  assets: AssetSummary[];
}

interface AssetPayload {
  asset_id: string;
  tenant_id: string | null;
  asset: JsonRecord;
}

interface DomainPayload {
  asset_id: string;
  tenant_id: string | null;
  evaluation_cutoff: string | null;
  status: string;
  data: unknown;
  reason: string | null;
}

interface EvaluationPayload {
  asset_id: string;
  tenant_id: string | null;
  evaluation_cutoff: string;
  decision: JsonRecord;
  why: JsonRecord;
  biology: DomainPayload;
  clinical: DomainPayload;
  cns: DomainPayload;
  patients: DomainPayload;
  safety: DomainPayload;
  resistance: DomainPayload;
  combinations: DomainPayload;
  competitive: DomainPayload;
  licensing: DomainPayload;
  commercial: DomainPayload;
}

interface EvidencePayload {
  status: string;
  cutoff: string | null;
  evidence: unknown[];
}

interface HistoryPayload {
  status?: string;
  as_of: string;
  evidence: unknown[];
  milestones: unknown[];
}

async function getJson(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(path, {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store",
    signal,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`;
    if (
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) {
      detail = payload.detail;
    }
    throw new Error(detail);
  }
  return payload;
}

function asRecord(value: unknown): JsonRecord {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonRecord)
    : {};
}

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function invalidApiResponse(endpoint: string): Error {
  return new Error(`The ${endpoint} API returned an invalid response.`);
}

function parseAssetCatalog(value: unknown): AssetCatalog {
  if (!isRecord(value) || !Array.isArray(value.assets)) {
    throw invalidApiResponse("asset catalog");
  }
  const assets = value.assets.map((item) => {
    if (
      !isRecord(item) ||
      typeof item.id !== "string" ||
      typeof item.name !== "string"
    ) {
      throw invalidApiResponse("asset catalog");
    }
    return {
      id: item.id,
      name: item.name,
      target: typeof item.target === "string" ? item.target : undefined,
      modality: typeof item.modality === "string" ? item.modality : undefined,
      stage: typeof item.stage === "string" ? item.stage : undefined,
      primary_indication:
        typeof item.primary_indication === "string"
          ? item.primary_indication
          : undefined,
    };
  });
  return {
    tenant_id: typeof value.tenant_id === "string" ? value.tenant_id : null,
    assets,
  };
}

function parseAssetPayload(value: unknown, requestedId: string): AssetPayload {
  if (
    !isRecord(value) ||
    typeof value.asset_id !== "string" ||
    !isRecord(value.asset) ||
    typeof value.asset.id !== "string" ||
    typeof value.asset.name !== "string" ||
    value.asset_id.toLowerCase() !== requestedId.toLowerCase() ||
    value.asset.id.toLowerCase() !== requestedId.toLowerCase()
  ) {
    throw invalidApiResponse("asset");
  }
  return {
    asset_id: value.asset_id,
    tenant_id: typeof value.tenant_id === "string" ? value.tenant_id : null,
    asset: value.asset,
  };
}

const DOMAIN_KEYS = [
  "biology",
  "clinical",
  "cns",
  "patients",
  "safety",
  "resistance",
  "combinations",
  "competitive",
  "licensing",
  "commercial",
] as const;

function parseDomain(
  value: unknown,
  key: (typeof DOMAIN_KEYS)[number],
  assetId: string,
  cutoff: string,
  tenantId: string | null,
): DomainPayload {
  if (!isRecord(value)) {
    return {
      asset_id: assetId,
      tenant_id: tenantId,
      evaluation_cutoff: cutoff,
      status: "UNKNOWN",
      data: null,
      reason: `${key} domain was not returned by the evaluation API.`,
    };
  }
  return {
    asset_id: typeof value.asset_id === "string" ? value.asset_id : assetId,
    tenant_id: typeof value.tenant_id === "string" ? value.tenant_id : tenantId,
    evaluation_cutoff:
      typeof value.evaluation_cutoff === "string"
        ? value.evaluation_cutoff
        : cutoff,
    status: typeof value.status === "string" ? value.status : "UNKNOWN",
    data: value.data ?? null,
    reason:
      typeof value.reason === "string"
        ? value.reason
        : value.status === "UNKNOWN"
          ? `${key} domain state was not provided by the evaluation API.`
          : null,
  };
}

function parseEvaluationPayload(
  value: unknown,
  requestedId: string,
): EvaluationPayload {
  if (
    !isRecord(value) ||
    typeof value.asset_id !== "string" ||
    value.asset_id.toLowerCase() !== requestedId.toLowerCase() ||
    typeof value.evaluation_cutoff !== "string" ||
    !isRecord(value.decision)
  ) {
    throw invalidApiResponse("evaluation");
  }
  const tenantId = typeof value.tenant_id === "string" ? value.tenant_id : null;
  const domains = Object.fromEntries(
    DOMAIN_KEYS.map((key) => [
      key,
      parseDomain(
        value[key],
        key,
        value.asset_id as string,
        value.evaluation_cutoff as string,
        tenantId,
      ),
    ]),
  ) as Pick<EvaluationPayload, (typeof DOMAIN_KEYS)[number]>;
  return {
    asset_id: value.asset_id,
    tenant_id: tenantId,
    evaluation_cutoff: value.evaluation_cutoff,
    decision: value.decision,
    why: isRecord(value.why) ? value.why : {},
    ...domains,
  };
}

function parseEvidencePayload(value: unknown): EvidencePayload {
  if (
    !isRecord(value) ||
    typeof value.status !== "string" ||
    !(value.cutoff === null || typeof value.cutoff === "string") ||
    !Array.isArray(value.evidence)
  ) {
    throw invalidApiResponse("evidence");
  }
  return {
    status: value.status,
    cutoff: value.cutoff,
    evidence: value.evidence,
  };
}

function parseHistoryPayload(value: unknown): HistoryPayload {
  if (
    !isRecord(value) ||
    typeof value.as_of !== "string" ||
    !Array.isArray(value.evidence) ||
    !Array.isArray(value.milestones)
  ) {
    throw invalidApiResponse("history");
  }
  return {
    status: typeof value.status === "string" ? value.status : undefined,
    as_of: value.as_of,
    evidence: value.evidence,
    milestones: value.milestones,
  };
}

function textValue(value: unknown, unknownLabel = "UNKNOWN"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean")
    return String(value);
  return unknownLabel;
}

function identityOf(asset: JsonRecord): AssetSummary {
  return {
    id: textValue(asset.id, ""),
    name: textValue(asset.name, "Unknown asset"),
    target: typeof asset.target === "string" ? asset.target : undefined,
    modality: typeof asset.modality === "string" ? asset.modality : undefined,
    stage: typeof asset.stage === "string" ? asset.stage : undefined,
    primary_indication:
      typeof asset.primary_indication === "string"
        ? asset.primary_indication
        : undefined,
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

const SECTIONS = [
  { id: "overview", title: "Decision summary" },
  { id: "development-potential", title: "Development Potential" },
  { id: "biology", title: "Biology Profile" },
  { id: "key-attributes", title: "Key Attributes" },
  { id: "preclinical", title: "Preclinical Evidence" },
  { id: "clinical", title: "Clinical Development" },
  { id: "cns", title: "CNS" },
  { id: "patient-match", title: "Patient Match" },
  { id: "safety", title: "Safety" },
  { id: "resistance", title: "Resistance" },
  { id: "combinations", title: "Combinations" },
  { id: "landscape", title: "Competitive Landscape" },
  { id: "regulatory", title: "Regulatory / IP" },
  { id: "licensing", title: "Licensing" },
  { id: "commercial", title: "Commercial Opportunity" },
  { id: "evidence", title: "Evidence & Temporal History" },
] as const;

export function EvaluateView() {
  const searchParams = useSearchParams();
  const { activeSection, setActiveSection } = useWorkspace();
  const requestedAsset = searchParams.get("asset") ?? "";
  const section = searchParams.get("section");
  const cutoff = searchParams.get("cutoff");
  const [assets, setAssets] = useState<AssetSummary[]>([]);
  const [assetId, setAssetId] = useState(requestedAsset);
  const [asset, setAsset] = useState<JsonRecord | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationPayload | null>(null);
  const [evidence, setEvidence] = useState<EvidencePayload | null>(null);
  const [history, setHistory] = useState<HistoryPayload | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [loading, setLoading] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [whyOpen, setWhyOpen] = useState(false);
  const [why, setWhy] = useState<JsonRecord | null>(null);
  const [whyLoading, setWhyLoading] = useState(false);
  const [whyError, setWhyError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setCatalogLoading(true);
    getJson("/api/assets")
      .then((catalog) => {
        if (!alive) return;
        const parsedCatalog = parseAssetCatalog(catalog);
        setAssets(parsedCatalog.assets);
        const initial = requestedAsset
          ? parsedCatalog.assets.find(
              (item) => item.id.toLowerCase() === requestedAsset.toLowerCase(),
            )
          : parsedCatalog.assets[0];
        if (initial) setAssetId(initial.id);
        else if (requestedAsset) setAssetId(requestedAsset);
      })
      .catch((caught: unknown) => {
        if (alive) setCatalogError(errorMessage(caught));
      })
      .finally(() => {
        if (alive) setCatalogLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [requestedAsset]);

  useEffect(() => {
    if (section) setActiveSection(section);
  }, [section, setActiveSection]);

  useEffect(() => {
    if (!assetId) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setAsset(null);
    setEvaluation(null);
    setEvidence(null);
    setHistory(null);
    setEvidenceError(null);
    setHistoryError(null);
    setWhy(null);
    setWhyError(null);
    const encodedId = encodeURIComponent(assetId);
    const cutoffQuery = cutoff ? `?cutoff=${encodeURIComponent(cutoff)}` : "";
    const historyQuery = cutoff ? `?as_of=${encodeURIComponent(cutoff)}` : "";
    void (async () => {
      try {
        const required = await Promise.all([
          getJson(`/api/assets/${encodedId}`, controller.signal),
          getJson(
            `/api/assets/${encodedId}/evaluate${cutoffQuery}`,
            controller.signal,
          ),
        ]);
        if (controller.signal.aborted) return;
        setAsset(parseAssetPayload(required[0], assetId).asset);
        setEvaluation(parseEvaluationPayload(required[1], assetId));
        const optional = await Promise.allSettled([
          getJson(
            `/api/assets/${encodedId}/evidence${cutoffQuery}`,
            controller.signal,
          ).then(parseEvidencePayload),
          getJson(
            `/api/assets/${encodedId}/history${historyQuery}`,
            controller.signal,
          ).then(parseHistoryPayload),
        ]);
        if (controller.signal.aborted) return;
        if (optional[0].status === "fulfilled") setEvidence(optional[0].value);
        else setEvidenceError(errorMessage(optional[0].reason));
        if (optional[1].status === "fulfilled") setHistory(optional[1].value);
        else setHistoryError(errorMessage(optional[1].reason));
      } catch (caught) {
        if (!controller.signal.aborted) setError(errorMessage(caught));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [assetId, cutoff]);

  useEffect(() => {
    if (!activeSection) return;
    document.getElementById(activeSection)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  }, [activeSection, evaluation]);

  const canonical = useMemo(() => (asset ? identityOf(asset) : null), [asset]);
  const decision = useMemo(() => evaluation?.decision ?? {}, [evaluation]);
  const decisionSummary = useMemo(() => {
    const {
      decision: _decision,
      priority: _priority,
      confidence: _confidence,
      ...summary
    } = asRecord(decision);
    return summary;
  }, [decision]);
  const decisionRecord = asRecord(decision);
  const decisionValue = textValue(decisionRecord.decision);
  const decisionPriority = textValue(decisionRecord.priority);
  const confidence = decisionRecord.confidence;
  const decisionConfidence =
    typeof confidence === "number"
      ? `${Math.round(confidence * 100)}%`
      : "UNKNOWN";
  const businessProfile = asRecord(asset?.business_profile);
  const keyAttributes = asRecord(asset?.key_attributes);

  async function showWhy() {
    if (!evaluation) return;
    setWhyOpen(true);
    setWhyLoading(true);
    setWhyError(null);
    try {
      const suffix = cutoff ? `?cutoff=${encodeURIComponent(cutoff)}` : "";
      const response = await getJson(
        `/api/assets/${encodeURIComponent(evaluation.asset_id)}/why${suffix}`,
      );
      if (!isRecord(response)) throw invalidApiResponse("WHY");
      setWhy(response);
    } catch (caught) {
      setWhyError(errorMessage(caught));
    } finally {
      setWhyLoading(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 text-slate-800 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Prompt 57 Core APIs · Prompt 54–55 decision and WHY
          </p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
            Evaluate asset
          </h1>
          <p className="mt-1 text-sm text-slate-600">
            Cutoff-aware evaluation from the canonical asset and intelligence
            APIs. Unknown and unavailable values remain explicit.
          </p>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <label className="sr-only" htmlFor="evaluate-asset">
              Canonical asset
            </label>
            <select
              id="evaluate-asset"
              value={assetId}
              onChange={(event) => setAssetId(event.target.value)}
              disabled={catalogLoading || assets.length === 0}
              className="min-h-10 min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:opacity-60"
            >
              {assetId && !assets.some((item) => item.id === assetId) && (
                <option value={assetId}>{assetId}</option>
              )}
              {assets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.id}
                </option>
              ))}
            </select>
            {cutoff && (
              <p className="self-center rounded-md bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-900">
                Historical evaluation cutoff: {cutoff}
              </p>
            )}
          </div>
        </header>

        {catalogError && (
          <p
            role="alert"
            className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-900"
          >
            Asset catalog unavailable: {catalogError}
          </p>
        )}
        {(catalogLoading || loading) && (
          <div
            role="status"
            aria-label="Loading asset evaluation"
            className="mt-5 space-y-3"
          >
            {[0, 1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-28 animate-pulse rounded-xl bg-white p-4"
              >
                <div className="h-4 w-1/3 rounded bg-slate-200" />
                <div className="mt-4 h-3 w-2/3 rounded bg-slate-100" />
              </div>
            ))}
          </div>
        )}
        {error && (
          <div
            role="alert"
            className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900"
          >
            <strong>Evaluation unavailable.</strong> {error}
          </div>
        )}
        {!catalogLoading && !loading && !error && !assetId && (
          <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <h2 className="font-semibold">
              No canonical assets are available.
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              The asset catalog did not return an asset to evaluate.
            </p>
          </div>
        )}

        {asset && evaluation && canonical && !loading && (
          <>
            <section
              id="overview"
              className="mt-5 scroll-mt-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Canonical asset · {canonical.id}
                  </p>
                  <h2 className="mt-1 text-2xl font-bold text-slate-900">
                    {canonical.name}
                  </h2>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs">
                    <Pill label="Target" value={canonical.target} />
                    <Pill label="Modality" value={canonical.modality} />
                    <Pill label="Stage" value={canonical.stage} />
                    <Pill
                      label="Indication"
                      value={canonical.primary_indication}
                    />
                  </div>
                </div>
                <div className="min-w-52 rounded-lg bg-slate-900 p-4 text-white">
                  <p className="text-xs uppercase tracking-wide text-slate-300">
                    Recommendation
                  </p>
                  <p className="mt-1 text-xl font-bold">{decisionValue}</p>
                  <p className="mt-2 text-sm">Priority: {decisionPriority}</p>
                  <p className="text-sm">Confidence: {decisionConfidence}</p>
                  <button
                    type="button"
                    onClick={showWhy}
                    className="mt-3 rounded-md bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-white"
                  >
                    WHY this recommendation?
                  </button>
                </div>
              </div>
              <p className="mt-4 text-xs text-slate-500">
                Tenant scope: {evaluation.tenant_id ?? "UNKNOWN / NOT RETURNED"}{" "}
                · Evaluation cutoff: {evaluation.evaluation_cutoff}
              </p>
            </section>

            <nav
              aria-label="Evaluation sections"
              className="sticky top-0 z-10 mt-4 bg-[#f8fafc]/95 py-2"
            >
              <div className="flex gap-2 overflow-x-auto">
                {SECTIONS.map((section) => (
                  <button
                    type="button"
                    key={section.id}
                    onClick={() => {
                      setActiveSection(section.id);
                      document
                        .getElementById(section.id)
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                    className="shrink-0 rounded-full border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:border-blue-500 hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {section.title}
                  </button>
                ))}
              </div>
            </nav>

            <div className="mt-3 space-y-4 pb-12">
              <section id="development-potential" className="scroll-mt-20">
                <Section
                  title="Development Potential"
                  subtitle="Master Decision Engine output"
                  status="AVAILABLE"
                  data={decisionSummary}
                  onScoreClick={showWhy}
                />
              </section>
              <DomainSection
                id="biology"
                title="Biology Profile"
                domain={evaluation.biology}
                onScoreClick={showWhy}
              />
              <section id="key-attributes" className="scroll-mt-20">
                <Section
                  title="Key Attributes"
                  subtitle="Fields returned by the canonical asset API"
                  data={keyAttributes}
                />
              </section>
              <section id="preclinical" className="scroll-mt-20">
                <Section
                  title="Preclinical Evidence"
                  subtitle="Only the backend evidence ledger is used; no preclinical outcomes are inferred."
                  status={evidence?.status ?? "UNKNOWN"}
                  data={evidence?.evidence ?? null}
                  error={evidenceError}
                />
              </section>
              <DomainSection
                id="clinical"
                title="Clinical Development"
                domain={evaluation.clinical}
                onScoreClick={showWhy}
              />
              <DomainSection
                id="cns"
                title="CNS"
                domain={evaluation.cns}
                onScoreClick={showWhy}
              />
              <DomainSection
                id="patient-match"
                title="Patient Match"
                domain={evaluation.patients}
                onScoreClick={showWhy}
              />
              <DomainSection
                id="safety"
                title="Safety"
                domain={evaluation.safety}
                onScoreClick={showWhy}
              />
              <DomainSection
                id="resistance"
                title="Resistance"
                domain={evaluation.resistance}
                onScoreClick={showWhy}
              />
              <DomainSection
                id="combinations"
                title="Combinations"
                domain={evaluation.combinations}
                onScoreClick={showWhy}
              />
              <DomainSection
                id="landscape"
                title="Competitive Landscape"
                domain={evaluation.competitive}
                onScoreClick={showWhy}
              />
              <section id="regulatory" className="scroll-mt-20">
                <Section
                  title="Regulatory / IP"
                  subtitle="Canonical business profile; no separate regulatory endpoint is provided by the core evaluation response."
                  status={
                    Object.keys(businessProfile).length
                      ? "AVAILABLE"
                      : "UNKNOWN"
                  }
                  data={businessProfile}
                />
              </section>
              <DomainSection
                id="licensing"
                title="Licensing"
                domain={evaluation.licensing}
                onScoreClick={showWhy}
              />
              <DomainSection
                id="commercial"
                title="Commercial Opportunity"
                domain={evaluation.commercial}
                onScoreClick={showWhy}
              />
              <section id="evidence" className="scroll-mt-20">
                <Section
                  title="Evidence & Provenance"
                  subtitle={`Evidence status: ${evidence?.status ?? "UNKNOWN"}${evidence?.cutoff ? ` · cutoff ${evidence.cutoff}` : ""}`}
                  status={evidence?.status ?? "UNKNOWN"}
                  data={evidence?.evidence ?? null}
                  error={evidenceError}
                />
                <div className="mt-3">
                  <Section
                    title="Temporal history"
                    subtitle={
                      history ? `As of ${history.as_of}` : "History API"
                    }
                    status={history ? "AVAILABLE" : "UNKNOWN"}
                    data={
                      history
                        ? {
                            evidence: history.evidence,
                            milestones: history.milestones,
                          }
                        : null
                    }
                    error={historyError}
                  />
                </div>
              </section>
            </div>
          </>
        )}

        {whyOpen && (
          <div
            role="presentation"
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setWhyOpen(false);
            }}
          >
            <section
              role="dialog"
              aria-modal="true"
              aria-labelledby="why-title"
              className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-xl bg-white p-5 shadow-2xl"
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h2
                    id="why-title"
                    className="text-lg font-bold text-slate-900"
                  >
                    WHY explanation
                  </h2>
                  <p className="mt-1 text-sm text-slate-600">
                    Explanation returned by the existing WHY Engine API.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setWhyOpen(false)}
                  aria-label="Close WHY explanation"
                  className="rounded px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
                >
                  Close
                </button>
              </div>
              {whyLoading && (
                <p role="status" className="mt-4 text-sm">
                  Loading WHY explanation…
                </p>
              )}
              {whyError && (
                <p role="alert" className="mt-4 text-sm text-rose-800">
                  {whyError}
                </p>
              )}
              {why && <JsonValue value={why} />}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function stripNestedProvenance(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => stripNestedProvenance(item));
  }
  if (value && typeof value === "object") {
    const record = value as JsonRecord;
    const cleaned: JsonRecord = {};
    for (const [key, nested] of Object.entries(record)) {
      if (key === "provenance") continue;
      cleaned[key] = stripNestedProvenance(nested);
    }
    return cleaned;
  }
  return value;
}

function collectProvenance(
  value: unknown,
  path = "domain",
): Array<{ path: string; value: unknown }> {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) =>
      collectProvenance(item, `${path}[${index}]`),
    );
  }
  if (!isRecord(value)) return [];
  return Object.entries(value).flatMap(([key, nested]) => {
    if (key === "provenance") {
      if (isRecord(nested) && Object.keys(nested).length > 0) {
        return [{ path, value: nested }];
      }
      return [];
    }
    return collectProvenance(nested, `${path}.${key}`);
  });
}

function isHttpUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function Pill({ label, value }: { label: string; value?: string }) {
  return (
    <span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-700">
      <strong>{label}:</strong> {value ?? "UNKNOWN"}
    </span>
  );
}

function DomainSection({
  id,
  title,
  domain,
  onScoreClick,
}: {
  id: string;
  title: string;
  domain: DomainPayload;
  onScoreClick: () => void;
}) {
  const provenance = collectProvenance(domain.data);
  return (
    <section id={id} className="scroll-mt-20">
      <Section
        title={title}
        subtitle={
          domain.reason ?? `Cutoff ${domain.evaluation_cutoff ?? "UNKNOWN"}`
        }
        status={domain.status}
        data={stripNestedProvenance(domain.data)}
        onScoreClick={onScoreClick}
      />
      {provenance.length > 0 && (
        <details className="mt-2 rounded-lg border border-slate-200 bg-white p-3">
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">
            Model and evidence provenance
          </summary>
          <div className="mt-3 space-y-3">
            {provenance.map((entry) => (
              <div key={entry.path} className="rounded-md bg-slate-50 p-3">
                <p className="mb-2 text-xs font-semibold text-slate-600">
                  {entry.path}
                </p>
                <JsonValue value={entry.value} />
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function Section({
  title,
  subtitle,
  status,
  data,
  error,
  onScoreClick,
}: {
  title: string;
  subtitle: string;
  status?: string;
  data: unknown;
  error?: string | null;
  onScoreClick?: () => void;
}) {
  const empty =
    data === null ||
    data === undefined ||
    (Array.isArray(data) && data.length === 0) ||
    (typeof data === "object" &&
      !Array.isArray(data) &&
      Object.keys(data).length === 0);
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="font-bold text-slate-900">{title}</h2>
          <p className="mt-1 text-xs text-slate-600">{subtitle}</p>
        </div>
        {status && (
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusClass(status)}`}
          >
            {status.replaceAll("_", " ")}
          </span>
        )}
      </div>
      {error && (
        <p
          role="alert"
          className="mt-3 rounded-md bg-rose-50 p-3 text-sm text-rose-900"
        >
          Section unavailable: {error}
        </p>
      )}
      {empty && !error ? (
        <p className="mt-3 rounded-md bg-amber-50 p-3 text-sm text-amber-900">
          {status && status !== "AVAILABLE"
            ? `${status.replaceAll("_", " ")} — no value is available from this endpoint.`
            : "UNKNOWN — no data was returned by the API."}
        </p>
      ) : (
        <div className="mt-3">
          <JsonValue value={data} onScoreClick={onScoreClick} />
        </div>
      )}
      {onScoreClick && (
        <button
          type="button"
          onClick={onScoreClick}
          className="mt-3 rounded-md border border-blue-200 px-3 py-2 text-xs font-semibold text-blue-800 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          WHY / evidence / unknowns
        </button>
      )}
    </article>
  );
}

function statusClass(status: string): string {
  if (status === "AVAILABLE") return "bg-emerald-100 text-emerald-800";
  if (status === "UNAVAILABLE") return "bg-slate-200 text-slate-700";
  return "bg-amber-100 text-amber-900";
}

function JsonValue({
  value,
  depth = 0,
  path = "",
  onScoreClick,
}: {
  value: unknown;
  depth?: number;
  path?: string;
  onScoreClick?: () => void;
}): React.ReactElement {
  if (value === null || value === undefined || value === "") {
    return <span className="text-amber-800">UNKNOWN</span>;
  }
  if (Array.isArray(value)) {
    if (!value.length)
      return <span className="text-slate-500">No items returned.</span>;
    return (
      <ul
        className={`space-y-2 ${depth ? "ml-3 border-l border-slate-200 pl-3" : ""}`}
      >
        {value.map((item, index) => {
          const uniqueKey = `${path}.${index}`;
          return (
            <li key={uniqueKey} className="text-sm">
              <JsonValue
                value={item}
                depth={depth + 1}
                path={uniqueKey}
                onScoreClick={onScoreClick}
              />
            </li>
          );
        })}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <dl
        className={`grid gap-x-4 gap-y-2 sm:grid-cols-[minmax(9rem,0.4fr)_1fr] ${depth ? "rounded-md bg-slate-50 p-3" : ""}`}
      >
        {Object.entries(value as JsonRecord).map(([key, nested]) => {
          const uniqueKey = `${path}.${key}`;
          return (
            <React.Fragment key={uniqueKey}>
              <dt className="break-words text-xs font-semibold uppercase tracking-wide text-slate-500">
                {key.replaceAll("_", " ")}
              </dt>
              <dd className="min-w-0 break-words text-sm text-slate-800">
                {typeof nested === "number" &&
                /(score|confidence|potential|probability|risk)$/i.test(key) &&
                onScoreClick ? (
                  <button
                    type="button"
                    onClick={onScoreClick}
                    className="rounded underline decoration-dotted underline-offset-2 hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    aria-label={`Show WHY for ${key} ${nested}`}
                  >
                    {nested}
                  </button>
                ) : isHttpUrl(nested) && /^(source_)?url$/i.test(key) ? (
                  <a
                    href={nested}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-700 underline"
                  >
                    {nested}
                  </a>
                ) : (
                  <JsonValue
                    value={nested}
                    depth={depth + 1}
                    path={uniqueKey}
                    onScoreClick={onScoreClick}
                  />
                )}
              </dd>
            </React.Fragment>
          );
        })}
      </dl>
    );
  }
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  return <span>{String(value)}</span>;
}
