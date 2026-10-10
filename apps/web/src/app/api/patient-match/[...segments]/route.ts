import { NextResponse } from "next/server";
import { proxyAiServicesRequest } from "@/lib/ai-services-proxy";

const ASSET_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

export async function GET(
  request: Request,
  { params }: { params: { segments: string[] } },
) {
  const [kind, assetId, ...rest] = params.segments;
  if (
    kind !== "intelligence" ||
    !assetId ||
    !ASSET_ID_PATTERN.test(assetId) ||
    rest.length > 0
  ) {
    return NextResponse.json(
      { detail: "Invalid PatientMatch API path." },
      { status: 404 },
    );
  }

  const incomingUrl = new URL(request.url);
  const cutoff = incomingUrl.searchParams.get("cutoff");
  const query = cutoff ? `?cutoff=${encodeURIComponent(cutoff)}` : "";
  return proxyAiServicesRequest(
    request,
    `/api/assets/${encodeURIComponent(assetId)}/patients${query}`,
    "GET",
  );
}

export function POST(
  request: Request,
  { params }: { params: { segments: string[] } },
) {
  if (params.segments.length !== 1 || params.segments[0] !== "scenario") {
    return NextResponse.json(
      { detail: "Invalid PatientMatch API path." },
      { status: 404 },
    );
  }
  return proxyAiServicesRequest(
    request,
    "/api/v1/patient-match/scenario",
    "POST",
  );
}
