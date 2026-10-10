"use client";

import React, { useEffect, useMemo, useState } from "react";
import { requestJson } from "../lib/api-client";

const CATEGORY_LABELS = [
  "Pursue",
  "Partner",
  "License",
  "Academic",
  "Emerging Threat",
  "Monitor",
  "Avoided",
  "Unclassified",
] as const;

export type OpportunityCategory = (typeof CATEGORY_LABELS)[number];

interface AssetSummary {
  id: string;
  name: string;
  target: string | null;
  stage: string | null;
  owner: string | null;
  primaryIndication: string | null;
}

interface Decision {
  decision: string;
  priority: string | null;
  score: number | null;
  confidence: number | null;
  unknowns: string[];
  supportingEvidence: string[];
  contradictoryEvidence: string[];
  policyName: string | null;
  policyVersion: string | null;
  modelVersions: Record<string, string>;
  featureVersions: Record<string, string>;
  evaluationCutoff: string | null;
}

interface WhyResult {
  explanation: string;
  supportingEvidence: string[];
  contradictoryEvidence: string[];
  unknowns: string[];
  evidenceGaps: string[];
}

interface RecommendedAction {
  action: string;
  priority: string;
  rationale: string;
  decisionValue: number | null;
  urgency: number | null;
  effort: number | null;
  uncertaintyReduction: number | null;
  supportingEvidence: string[];
  unknowns: string[];
  lineage: Record<string, unknown>;
}

interface OwnershipProfile {
  currentOwner: string | null;
  originator: string | null;
  developer: string | null;
  academicOrigin: string | null;
  partner: string | null;
  licensingStatus: string | null;
  licensingStatusVerified: boolean;
  licensingVerificationSource: string | null;
  licensingStatusRationale: string | null;
}

interface OpportunityRecord {
  asset: AssetSummary;
  evaluation: {
    decision: Decision;
    why: WhyResult;
    actions: RecommendedAction[];
    ownership: OwnershipProfile | null;
    licensingProfileState: string;
  } | null;
  error: "unavailable" | null;
  categories: OpportunityCategory[];
}

export interface OpportunitiesViewProps {
  onNavigateToCompare: (assetId: string) => void;
  onNavigateToEvaluate: (assetId: string) => void;
}

const DECISION_CATEGORY: Record<string, OpportunityCategory> = {
  PURSUE: "Pursue",
  PARTNER: "Partner",
  LICENSE: "License",
  MONITOR: "Monitor",
  AVOID: "Avoided",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function uniqueStrings(...groups: string[][]): string[] {
  return [...new Set(groups.flat())];
}

function stringRecord(value: unknown): Record<string, string> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

function parseAsset(value: unknown): AssetSummary {
  if (!isRecord(value)) {
    throw new Error("Invalid asset catalog response.");
  }
  const id = stringValue(value.id);
  const name = stringValue(value.name);
  if (!id || !name) throw new Error("Invalid asset catalog response.");
  return {
    id,
    name,
    target: stringValue(value.target),
    stage: stringValue(value.stage),
    owner: stringValue(value.owner),
    primaryIndication: stringValue(value.primary_indication),
  };
}

function parseAction(value: unknown): RecommendedAction | null {
  if (!isRecord(value)) {
    return null;
  }
  const action = stringValue(value.action);
  const priority = stringValue(value.priority);
  const rationale = stringValue(value.rationale);
  if (!action || !priority || !rationale) return null;
  return {
    action,
    priority,
    rationale,
    decisionValue: numberValue(value.decision_value),
    urgency: numberValue(value.urgency),
    effort: numberValue(value.effort),
    uncertaintyReduction: numberValue(value.uncertainty_reduction),
    supportingEvidence: stringArray(value.supporting_evidence),
    unknowns: stringArray(value.unknowns),
    lineage: isRecord(value.lineage) ? value.lineage : {},
  };
}

function parseEvaluation(
  value: unknown,
  requestedAssetId: string,
): OpportunityRecord["evaluation"] {
  if (
    !isRecord(value) ||
    value.asset_id !== requestedAssetId ||
    !isRecord(value.decision) ||
    !isRecord(value.why)
  ) {
    throw new Error("Invalid asset evaluation response.");
  }
  const decision = value.decision;
  const why = value.why;
  const decisionName = stringValue(decision.decision);
  const explanation = stringValue(why.explanation);
  if (!decisionName || !explanation) {
    throw new Error("Invalid asset evaluation response.");
  }

  const actionResult = isRecord(value.action_intelligence)
    ? value.action_intelligence
    : null;
  const actions = Array.isArray(actionResult?.recommended_actions)
    ? actionResult.recommended_actions
        .map(parseAction)
        .filter((item): item is RecommendedAction => item !== null)
    : [];

  const licensing = isRecord(value.licensing) ? value.licensing : null;
  const ownership =
    licensing && isRecord(licensing.data) ? licensing.data : null;

  return {
    decision: {
      decision: decisionName,
      priority: stringValue(decision.priority),
      score: numberValue(decision.score),
      confidence: numberValue(decision.confidence),
      unknowns: stringArray(decision.unknowns),
      supportingEvidence: stringArray(decision.supporting_evidence),
      contradictoryEvidence: stringArray(decision.contradictory_evidence),
      policyName: stringValue(decision.policy_name),
      policyVersion: stringValue(decision.policy_version),
      modelVersions: stringRecord(decision.model_versions),
      featureVersions: stringRecord(decision.feature_versions),
      evaluationCutoff: stringValue(decision.evaluation_cutoff),
    },
    why: {
      explanation,
      supportingEvidence: stringArray(why.supporting_evidence),
      contradictoryEvidence: stringArray(why.contradictory_evidence),
      unknowns: stringArray(why.unknowns),
      evidenceGaps: stringArray(why.evidence_gaps),
    },
    actions,
    ownership: ownership
      ? {
          currentOwner: stringValue(ownership.current_owner),
          originator: stringValue(ownership.originator),
          developer: stringValue(ownership.developer),
          academicOrigin: stringValue(ownership.academic_origin),
          partner: stringValue(ownership.partner),
          licensingStatus: stringValue(ownership.licensing_status),
          licensingStatusVerified: ownership.licensing_status_verified === true,
          licensingVerificationSource: stringValue(
            ownership.licensing_verification_source,
          ),
          licensingStatusRationale: stringValue(
            ownership.licensing_status_rationale,
          ),
        }
      : null,
    licensingProfileState: stringValue(licensing?.status) ?? "UNKNOWN",
  };
}

export function classifyOpportunityCategories(
  decision: string | null,
  academicOrigin: string | null,
): OpportunityCategory[] {
  const categories: OpportunityCategory[] = [];
  const decisionCategory = decision ? DECISION_CATEGORY[decision] : undefined;
  if (decisionCategory) categories.push(decisionCategory);
  if (academicOrigin) categories.push("Academic");
  return categories.length ? categories : ["Unclassified"];
}

function unavailable(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === ""
    ? "UNKNOWN / NOT RETURNED"
    : String(value);
}

function confidenceLabel(value: number | null): string {
  return value === null
    ? "UNKNOWN"
    : `${Math.round(value * 100)}% (API confidence)`;
}

function licensingLabel(record: OpportunityRecord): string {
  const ownership = record.evaluation?.ownership;
  const status = ownership?.licensingStatus;
  if (!status || status === "UNKNOWN") return "UNKNOWN / NOT RETURNED";
  if (status === "VERIFIED_AVAILABLE") {
    return ownership?.licensingStatusVerified &&
      ownership.licensingVerificationSource
      ? `VERIFIED_AVAILABLE — ${ownership.licensingVerificationSource}`
      : "VERIFIED_AVAILABLE status returned without a complete verification assertion; availability not asserted.";
  }
  return `${status} — licensing availability is not established.`;
}

function categoryDescription(category: OpportunityCategory): string {
  switch (category) {
    case "Pursue":
      return "Mapped only from the Master Decision Engine PURSUE decision.";
    case "Partner":
      return "Mapped only from the Master Decision Engine PARTNER decision.";
    case "License":
      return "Mapped from the Master Decision Engine LICENSE decision; this does not mean licensing is available.";
    case "Academic":
      return "Requires an academic_origin value from the ownership profile; it is not inferred from missing ownership.";
    case "Emerging Threat":
      return "No focal-asset emerging-threat classification is provided by the current API.";
    case "Monitor":
      return "Mapped only from the Master Decision Engine MONITOR decision.";
    case "Avoided":
      return "Mapped only from the Master Decision Engine AVOID decision.";
    case "Unclassified":
      return "The available decision and ownership data do not support one of the listed categories.";
  }
}

export function OpportunitiesView({
  onNavigateToCompare,
  onNavigateToEvaluate,
}: OpportunitiesViewProps) {
  const [records, setRecords] = useState<OpportunityRecord[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<
    OpportunityCategory | "All"
  >("All");
  const [search, setSearch] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setCatalogLoading(true);
    setCatalogError(false);

    void (async () => {
      try {
        const catalog = await requestJson<unknown>("/api/assets", {
          signal: controller.signal,
        });
        if (!isRecord(catalog) || !Array.isArray(catalog.assets)) {
          throw new Error("Invalid asset catalog response.");
        }
        const assets = catalog.assets.map(parseAsset);
        const opportunityRecords = await Promise.all(
          assets.map(async (asset): Promise<OpportunityRecord> => {
            try {
              const payload = await requestJson<unknown>(
                `/api/assets/${encodeURIComponent(asset.id)}/evaluate`,
                { signal: controller.signal },
              );
              const evaluation = parseEvaluation(payload, asset.id);
              return {
                asset,
                evaluation,
                error: null,
                categories: classifyOpportunityCategories(
                  evaluation?.decision.decision ?? null,
                  evaluation?.ownership?.academicOrigin ?? null,
                ),
              };
            } catch {
              if (controller.signal.aborted)
                throw new Error("Request aborted.");
              return {
                asset,
                evaluation: null,
                error: "unavailable",
                categories: ["Unclassified"],
              };
            }
          }),
        );
        if (!controller.signal.aborted) setRecords(opportunityRecords);
      } catch {
        if (!controller.signal.aborted) {
          setRecords([]);
          setCatalogError(true);
        }
      } finally {
        if (!controller.signal.aborted) setCatalogLoading(false);
      }
    })();

    return () => controller.abort();
  }, [reloadKey]);

  const categoryCounts = useMemo(
    () =>
      Object.fromEntries(
        CATEGORY_LABELS.map((category) => [
          category,
          records.filter((record) => record.categories.includes(category))
            .length,
        ]),
      ) as Record<OpportunityCategory, number>,
    [records],
  );

  const visibleRecords = useMemo(() => {
    const query = search.trim().toLowerCase();
    return records.filter((record) => {
      const categoryMatches =
        selectedCategory === "All" ||
        record.categories.includes(selectedCategory);
      const searchMatches =
        !query ||
        [record.asset.name, record.asset.id, record.asset.target]
          .filter((value): value is string => Boolean(value))
          .some((value) => value.toLowerCase().includes(query));
      return categoryMatches && searchMatches;
    });
  }, [records, search, selectedCategory]);

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 text-slate-800 sm:px-6">
      <div className="mx-auto max-w-7xl">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Prompt 66 · Evidence-backed opportunity command center
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Opportunities
          </h1>
          <p className="mt-1 max-w-4xl text-sm text-slate-600">
            Canonical assets, Master Decision Engine results, WHY explanations,
            and Prompt 56 ranked actions. Categories are mapped from supported
            API fields; this workspace does not create assignments or workflow
            state.
          </p>
        </header>

        {catalogLoading ? (
          <div
            role="status"
            aria-label="Loading opportunities"
            className="mt-5 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600"
          >
            Loading canonical assets and decision intelligence…
          </div>
        ) : catalogError ? (
          <div
            role="alert"
            className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-5"
          >
            <h2 className="font-semibold text-rose-950">
              Opportunity data is unavailable.
            </h2>
            <p className="mt-1 text-sm text-rose-900">
              The canonical asset catalog could not be loaded. No opportunity
              conclusions are available.
            </p>
            <button
              type="button"
              onClick={() => setReloadKey((current) => current + 1)}
              className="mt-3 rounded-md border border-rose-300 bg-white px-3 py-2 text-sm font-semibold text-rose-900 hover:bg-rose-100"
            >
              Retry
            </button>
          </div>
        ) : records.length === 0 ? (
          <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <h2 className="font-semibold text-slate-900">
              The API returned no canonical assets.
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              This does not establish that no opportunities exist outside the
              returned catalog.
            </p>
          </div>
        ) : (
          <>
            <section
              aria-label="Opportunity categories"
              className="mt-4 rounded-xl border border-slate-200 bg-white p-3"
            >
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  aria-pressed={selectedCategory === "All"}
                  onClick={() => setSelectedCategory("All")}
                  className={`rounded-md border px-3 py-2 text-xs font-semibold ${
                    selectedCategory === "All"
                      ? "border-blue-700 bg-blue-700 text-white"
                      : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                  }`}
                >
                  All ({records.length})
                </button>
                {CATEGORY_LABELS.map((category) => (
                  <button
                    key={category}
                    type="button"
                    aria-pressed={selectedCategory === category}
                    onClick={() => setSelectedCategory(category)}
                    className={`rounded-md border px-3 py-2 text-xs font-semibold ${
                      selectedCategory === category
                        ? "border-blue-700 bg-blue-700 text-white"
                        : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                    }`}
                  >
                    {category} ({categoryCounts[category]})
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-500" aria-live="polite">
                {selectedCategory === "All"
                  ? "Category mapping is deterministic and does not replace the original backend decision. Academic origin is a separate contextual category. Emerging-threat classification is not available from the current focal-asset API."
                  : categoryDescription(selectedCategory)}
              </p>
            </section>

            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <label className="grid gap-1 text-sm font-semibold">
                Filter canonical assets
                <input
                  type="search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search name, ID, or target"
                  className="min-h-10 rounded-md border border-slate-300 bg-white px-3 text-sm font-normal"
                />
              </label>
              <p className="text-xs text-slate-600" aria-live="polite">
                Showing {visibleRecords.length} of {records.length} returned
                assets. Per-asset analysis failures remain visible below.
              </p>
            </div>

            {visibleRecords.length === 0 ? (
              <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center">
                <h2 className="font-semibold text-slate-900">
                  No matching opportunities in the returned catalog.
                </h2>
                <p className="mt-1 text-sm text-slate-600">
                  This filter result is not evidence that no opportunities exist
                  globally.
                </p>
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                {visibleRecords.map((record) => (
                  <OpportunityCard
                    key={record.asset.id}
                    record={record}
                    onNavigateToCompare={onNavigateToCompare}
                    onNavigateToEvaluate={onNavigateToEvaluate}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function OpportunityCard({
  record,
  onNavigateToCompare,
  onNavigateToEvaluate,
}: {
  record: OpportunityRecord;
  onNavigateToCompare: (assetId: string) => void;
  onNavigateToEvaluate: (assetId: string) => void;
}) {
  const evaluation = record.evaluation;
  const decision = evaluation?.decision;
  const why = evaluation?.why;
  const nextAction = evaluation?.actions[0];
  const ownership = evaluation?.ownership;
  const assetOwner = record.asset.owner;
  const profileOwner = ownership?.currentOwner;
  const ownerStatus =
    ownership?.licensingStatus === "OWNERSHIP_UNCLEAR"
      ? "Ownership unresolved by profile."
      : profileOwner
        ? "Profile-reported current owner; separate identity verification is not returned."
        : assetOwner
          ? "Catalog-reported owner; separate identity verification is not returned."
          : "UNKNOWN / NOT RETURNED";
  const evidenceReferences = [
    ...(decision?.supportingEvidence ?? []),
    ...(decision?.contradictoryEvidence ?? []),
    ...(decision?.unknowns ?? []),
    ...(why?.supportingEvidence ?? []),
    ...(why?.contradictoryEvidence ?? []),
    ...(why?.evidenceGaps ?? []),
    ...(why?.unknowns ?? []),
  ];

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                {record.asset.name}
              </h2>
              <p className="text-xs text-slate-500">
                Canonical ID: <code>{record.asset.id}</code>
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {record.categories.map((category) => (
                <span
                  key={category}
                  className="rounded-full bg-blue-50 px-2.5 py-1 text-xs font-semibold text-blue-900"
                >
                  {category}
                </span>
              ))}
            </div>
          </div>

          {record.error ? (
            <div
              role="status"
              className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950"
            >
              Decision and WHY data are unavailable for this asset. It remains
              unclassified; no fallback conclusion is shown.
            </div>
          ) : (
            <>
              <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <DataField label="Backend decision">
                  {unavailable(decision?.decision)}
                  {decision?.priority ? ` · Priority ${decision.priority}` : ""}
                </DataField>
                <DataField label="Master Decision Engine score">
                  {decision?.score === null || decision?.score === undefined
                    ? "UNKNOWN"
                    : `${decision.score} / 100 (API scale)`}
                </DataField>
                <DataField label="Confidence">
                  {confidenceLabel(decision?.confidence ?? null)}
                </DataField>
                <DataField label="Target / stage">
                  {unavailable(record.asset.target)} ·{" "}
                  {unavailable(record.asset.stage)}
                </DataField>
                <DataField label="Owner / source status">
                  {profileOwner ?? assetOwner ?? "UNKNOWN / NOT RETURNED"} ·{" "}
                  {ownerStatus}
                </DataField>
                <DataField label="Sponsor">
                  UNKNOWN / NOT RETURNED BY CURRENT ASSET API
                </DataField>
              </dl>

              <section className="mt-4 rounded-lg border border-blue-100 bg-blue-50/50 p-3">
                <h3 className="text-sm font-semibold text-slate-900">
                  Why now / decision context
                </h3>
                <p className="mt-1 text-sm text-slate-700">
                  {why?.explanation ??
                    "WHY explanation is unavailable from the API."}
                </p>
                <p className="mt-2 text-xs font-medium text-amber-900">
                  Time-sensitive trigger: NOT RETURNED BY THE CURRENT API. No
                  urgency or new event is inferred here.
                </p>
              </section>

              <section className="mt-3 rounded-lg border border-slate-200 p-3">
                <h3 className="text-sm font-semibold text-slate-900">
                  Prompt 56 next recommended action
                </h3>
                {nextAction ? (
                  <>
                    <p className="mt-1 text-sm font-semibold text-slate-800">
                      {nextAction.priority} · {nextAction.action}
                    </p>
                    <p className="mt-1 text-sm text-slate-700">
                      {nextAction.rationale}
                    </p>
                    <dl className="mt-2 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
                      <DataField label="Decision value">
                        {unavailable(nextAction.decisionValue)}
                      </DataField>
                      <DataField label="Urgency (API)">
                        {unavailable(nextAction.urgency)}
                      </DataField>
                      <DataField label="Effort (API)">
                        {unavailable(nextAction.effort)}
                      </DataField>
                      <DataField label="Uncertainty reduction (API)">
                        {unavailable(nextAction.uncertaintyReduction)}
                      </DataField>
                    </dl>
                    <p className="mt-2 text-xs text-slate-600">
                      Suggested action only; no task has been created or
                      executed.
                    </p>
                  </>
                ) : (
                  <p className="mt-1 text-sm text-slate-600">
                    No ranked action was returned. Action availability is
                    unknown; no task was created.
                  </p>
                )}
              </section>
            </>
          )}

          <details className="mt-3 rounded-md border border-slate-200 p-3">
            <summary className="cursor-pointer text-sm font-semibold text-slate-800">
              Evidence, provenance, ownership, licensing, and unknowns
            </summary>
            <div className="mt-3 space-y-3 text-xs text-slate-700">
              {evaluation && (
                <>
                  <p>
                    Evaluation cutoff: {unavailable(decision?.evaluationCutoff)}
                  </p>
                  <p>
                    Decision category is separate from backend decision{" "}
                    <strong>{unavailable(decision?.decision)}</strong>. A
                    LICENSE decision does not establish licensing availability.
                  </p>
                  <p>
                    Licensing profile response state:{" "}
                    {unavailable(evaluation.licensingProfileState)}
                  </p>
                  <p>
                    Profile-reported licensing status: {licensingLabel(record)}
                  </p>
                  {ownership?.academicOrigin && (
                    <p>
                      Academic origin (ownership profile):{" "}
                      {ownership.academicOrigin}
                    </p>
                  )}
                  {ownership?.originator && (
                    <p>Profile-reported originator: {ownership.originator}</p>
                  )}
                  {ownership?.developer && (
                    <p>Profile-reported developer: {ownership.developer}</p>
                  )}
                  {ownership?.partner && (
                    <p>Profile-reported partner: {ownership.partner}</p>
                  )}
                  <p>
                    Decision policy: {unavailable(decision?.policyName)}{" "}
                    {decision?.policyVersion ?? ""}
                  </p>
                  <p>
                    Model versions:{" "}
                    {Object.keys(decision?.modelVersions ?? {}).length
                      ? JSON.stringify(decision?.modelVersions)
                      : "UNKNOWN / NOT RETURNED"}
                  </p>
                  <p>
                    Feature versions:{" "}
                    {Object.keys(decision?.featureVersions ?? {}).length
                      ? JSON.stringify(decision?.featureVersions)
                      : "UNKNOWN / NOT RETURNED"}
                  </p>
                  <EvidenceGroup
                    title="Supporting evidence references"
                    items={uniqueStrings(
                      decision?.supportingEvidence ?? [],
                      why?.supportingEvidence ?? [],
                    )}
                  />
                  <EvidenceGroup
                    title="Contradictory evidence references"
                    items={uniqueStrings(
                      decision?.contradictoryEvidence ?? [],
                      why?.contradictoryEvidence ?? [],
                    )}
                  />
                  <EvidenceGroup
                    title="Unknowns and evidence gaps"
                    items={uniqueStrings(
                      decision?.unknowns ?? [],
                      why?.unknowns ?? [],
                      why?.evidenceGaps ?? [],
                    )}
                  />
                  {nextAction && (
                    <>
                      <EvidenceGroup
                        title="Next-action evidence references"
                        items={nextAction.supportingEvidence}
                      />
                      <EvidenceGroup
                        title="Next-action unknowns"
                        items={nextAction.unknowns}
                      />
                      <p>
                        Action lineage:{" "}
                        <code className="break-all">
                          {JSON.stringify(nextAction.lineage)}
                        </code>
                      </p>
                    </>
                  )}
                  {!evidenceReferences.length && (
                    <p>
                      Evidence references and uncertainty details are not
                      returned.
                    </p>
                  )}
                </>
              )}
            </div>
          </details>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2 lg:w-40 lg:flex-col">
          <button
            type="button"
            onClick={() => onNavigateToEvaluate(record.asset.id)}
            className="rounded-md bg-blue-700 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Open Evaluate
          </button>
          <button
            type="button"
            onClick={() => onNavigateToCompare(record.asset.id)}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Compare this asset
          </button>
        </div>
      </div>
    </article>
  );
}

function DataField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-slate-800">{children}</dd>
    </div>
  );
}

function EvidenceGroup({ title, items }: { title: string; items: string[] }) {
  return (
    <section>
      <h4 className="font-semibold">{title}</h4>
      {items.length ? (
        <ul className="mt-1 list-disc space-y-1 pl-4">
          {items.map((item, index) => (
            <li key={`${item}-${index}`} className="break-words">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1">No {title.toLowerCase()} returned.</p>
      )}
    </section>
  );
}
