import { NextResponse } from "next/server";
import { proxyAiServicesRequest } from "@/lib/ai-services-proxy";

const ASSET_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const ALLOWED_ENDPOINTS = new Set([
  "",
  "evaluate",
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
  "evidence",
  "why",
  "history",
  "report",
]);

export async function GET(
  request: Request,
  { params }: { params: { segments: string[] } },
) {
  const [assetId, endpoint, ...rest] = params.segments;
  if (
    !assetId ||
    !ASSET_ID_PATTERN.test(assetId) ||
    rest.length > 0 ||
    !ALLOWED_ENDPOINTS.has(endpoint ?? "")
  ) {
    return NextResponse.json(
      { detail: "Invalid asset API path." },
      { status: 404 },
    );
  }

  const incomingUrl = new URL(request.url);
  const allowedParams = endpoint === "history" ? ["as_of"] : ["cutoff"];
  const query = new URLSearchParams();
  for (const key of allowedParams) {
    const value = incomingUrl.searchParams.get(key);
    if (value) query.set(key, value);
  }
  const suffix = endpoint ? `/${endpoint}` : "";
  const search = query.size > 0 ? `?${query.toString()}` : "";
  return proxyAiServicesRequest(
    request,
    `/api/assets/${encodeURIComponent(assetId)}${suffix}${search}`,
    "GET",
  );
}
