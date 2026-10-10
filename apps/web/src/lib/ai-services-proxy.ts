import { NextResponse } from "next/server";

const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

export async function proxyAiServicesRequest(
  request: Request,
  backendPath: string,
  method: "GET" | "POST",
): Promise<Response> {
  const backendUrl = process.env.AI_SERVICES_URL ?? "http://localhost:8090";
  const headers = new Headers({ accept: "application/json" });
  for (const name of ["authorization", "cookie", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  try {
    const upstream = await fetch(
      `${backendUrl.replace(/\/$/, "")}${backendPath}`,
      {
        method,
        headers,
        body: method === "POST" ? await request.text() : undefined,
        cache: "no-store",
      },
    );
    const responseHeaders = new Headers();
    for (const [name, value] of upstream.headers.entries()) {
      if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase())) {
        responseHeaders.set(name, value);
      }
    }
    return new Response(await upstream.arrayBuffer(), {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("AI services proxy request failed", error);
    return NextResponse.json(
      { detail: "AI services are unavailable. Please try again later." },
      { status: 502 },
    );
  }
}
