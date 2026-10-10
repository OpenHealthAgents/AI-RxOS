"use client";

import React from "react";
import { useEffect, useState } from "react";
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

interface Claim {
  classification: "FACT" | "INFERENCE" | "HYPOTHESIS" | "UNKNOWN";
  statement: string;
  evidence_ids: string[];
}

interface ResearchAnswer {
  asset_id: string;
  evaluation_cutoff: string;
  question: string;
  summary: string;
  summary_classification: Claim["classification"];
  summary_evidence_ids: string[];
  claims: Claim[];
  citations: Citation[];
  unknowns: string[];
  contradictions: Citation[];
}

const epistemicClasses = new Set([
  "FACT",
  "INFERENCE",
  "HYPOTHESIS",
  "UNKNOWN",
]);

function parseAnswer(value: unknown, requestedAssetId: string): ResearchAnswer {
  if (!value || typeof value !== "object") {
    throw new Error("Research Copilot returned an invalid answer.");
  }
  const answer = value as ResearchAnswer;
  if (
    answer.asset_id !== requestedAssetId ||
    !epistemicClasses.has(answer.summary_classification) ||
    !Array.isArray(answer.claims) ||
    !Array.isArray(answer.citations) ||
    !Array.isArray(answer.summary_evidence_ids) ||
    !Array.isArray(answer.unknowns) ||
    !Array.isArray(answer.contradictions)
  ) {
    throw new Error("Research Copilot returned an invalid answer.");
  }
  const citationIds = new Set(answer.citations.map((item) => item.evidence_id));
  const allReferences = [
    ...answer.summary_evidence_ids,
    ...answer.claims.flatMap((claim) => claim.evidence_ids),
    ...answer.contradictions.map((item) => item.evidence_id),
  ];
  if (
    allReferences.some((reference) => !citationIds.has(reference)) ||
    answer.claims.some((claim) => !epistemicClasses.has(claim.classification))
  ) {
    throw new Error(
      "Research Copilot returned unresolved evidence references.",
    );
  }
  return answer;
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
      !asset ||
      typeof asset !== "object" ||
      !("id" in asset) ||
      typeof asset.id !== "string" ||
      !("name" in asset) ||
      typeof asset.name !== "string"
    ) {
      return [];
    }
    return [{ id: asset.id, name: asset.name }];
  });
}

export function ResearchCopilotView() {
  const [assets, setAssets] = useState<AssetOption[]>([]);
  const [assetId, setAssetId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ResearchAnswer | null>(null);
  const [loading, setLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    requestJson<unknown>("/api/assets", { signal: controller.signal })
      .then((payload) => setAssets(parseAssets(payload)))
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

  async function askQuestion(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!assetId || !question.trim()) return;
    setAsking(true);
    setError(null);
    setAnswer(null);
    try {
      const payload = await requestJson<unknown>("/api/research/copilot", {
        method: "POST",
        body: { asset_id: assetId, question: question.trim() },
      });
      setAnswer(parseAnswer(payload, assetId));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Research Copilot is unavailable.",
      );
    } finally {
      setAsking(false);
    }
  }

  const citationById = new Map(
    (answer?.citations ?? []).map((citation) => [
      citation.evidence_id,
      citation,
    ]),
  );

  return (
    <div className="flex-1 overflow-y-auto bg-[#f8fafc] px-4 py-5 text-slate-800 sm:px-6">
      <div className="mx-auto max-w-5xl">
        <header className="border-b border-slate-200 pb-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-blue-700">
            Prompt 67 · Evidence-grounded research
          </p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">
            Research Copilot
          </h1>
          <p className="mt-1 max-w-4xl text-sm text-slate-600">
            Ask about a canonical asset. Answers are separated into facts,
            inferences, hypotheses, and unknowns; cited sources link to
            retrieved internal evidence objects.
          </p>
        </header>

        {loading ? (
          <div role="status" className="mt-5 rounded-lg bg-white p-5">
            Loading canonical assets…
          </div>
        ) : (
          <form
            onSubmit={askQuestion}
            className="mt-5 grid gap-4 rounded-xl border border-slate-200 bg-white p-5"
          >
            <label className="grid gap-1 text-sm font-semibold">
              Canonical asset
              <select
                value={assetId}
                onChange={(event) => setAssetId(event.target.value)}
                className="min-h-10 rounded-md border border-slate-300 bg-white px-3 font-normal"
                required
              >
                <option value="">Select an asset</option>
                {assets.map((asset) => (
                  <option value={asset.id} key={asset.id}>
                    {asset.name} · {asset.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-1 text-sm font-semibold">
              Research question
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                maxLength={2000}
                rows={4}
                required
                placeholder="Ask about biology, clinical development, CNS, ownership, recommendation, or another supported area"
                className="rounded-md border border-slate-300 bg-white p-3 font-normal"
              />
            </label>
            <div>
              <button
                type="submit"
                disabled={asking || !assetId || !question.trim()}
                className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {asking ? "Retrieving evidence…" : "Ask with internal evidence"}
              </button>
            </div>
          </form>
        )}

        {error && (
          <div
            role="alert"
            className="mt-4 rounded-lg bg-rose-50 p-4 text-sm text-rose-950"
          >
            {error}
          </div>
        )}

        {answer && (
          <article className="mt-5 space-y-4 rounded-xl border border-slate-200 bg-white p-5">
            <div>
              <p className="text-xs text-slate-500">
                {answer.asset_id} · Cutoff {answer.evaluation_cutoff}
              </p>
              <h2 className="mt-1 text-lg font-bold">Answer</h2>
              <ClaimView
                claim={{
                  classification: answer.summary_classification,
                  statement: answer.summary,
                  evidence_ids: answer.summary_evidence_ids,
                }}
                citationById={citationById}
              />
            </div>
            <section aria-labelledby="research-claims-heading">
              <h3 id="research-claims-heading" className="font-semibold">
                Evidence-classified claims
              </h3>
              <div className="mt-2 space-y-3">
                {answer.claims.map((claim, index) => (
                  <ClaimView
                    key={`${claim.classification}-${index}`}
                    claim={claim}
                    citationById={citationById}
                  />
                ))}
              </div>
            </section>
            <EvidenceList
              title="Unknowns"
              citations={[]}
              messages={answer.unknowns}
            />
            <EvidenceList
              title="Contradictory evidence"
              citations={answer.contradictions}
            />
          </article>
        )}
      </div>
    </div>
  );
}

function ClaimView({
  claim,
  citationById,
}: {
  claim: Claim;
  citationById: Map<string, Citation>;
}) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <p className="text-xs font-bold tracking-wide text-blue-800">
        {claim.classification}
      </p>
      <p className="mt-1 text-sm text-slate-800">{claim.statement}</p>
      {claim.evidence_ids.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs text-slate-600">
          {claim.evidence_ids.map((id) => {
            const citation = citationById.get(id);
            const sourceUrl = safeExternalUrl(citation?.url ?? null);
            return citation ? (
              <li key={id}>
                <a
                  href={sourceUrl}
                  target={sourceUrl ? "_blank" : undefined}
                  rel={sourceUrl ? "noreferrer" : undefined}
                  className="font-medium text-blue-700 underline"
                >
                  [{citation.source_reference}] {citation.title}
                </a>
              </li>
            ) : null;
          })}
        </ul>
      )}
    </div>
  );
}

function EvidenceList({
  title,
  citations,
  messages = [],
}: {
  title: string;
  citations: Citation[];
  messages?: string[];
}) {
  return (
    <section>
      <h3 className="font-semibold">{title}</h3>
      {messages.length === 0 && citations.length === 0 ? (
        <p className="mt-1 text-sm text-slate-600">
          None returned by the current evidence context.
        </p>
      ) : (
        <ul className="mt-2 space-y-2 text-sm">
          {messages.map((message, index) => (
            <li key={`message-${index}`}>{message}</li>
          ))}
          {citations.map((citation) => (
            <li key={citation.evidence_id}>
              <span className="font-semibold">
                {citation.polarity ?? "SOURCE"}
              </span>
              {" · "}
              {citation.source_reference}: {citation.title}
              {citation.excerpt ? (
                <p className="text-slate-600">{citation.excerpt}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
