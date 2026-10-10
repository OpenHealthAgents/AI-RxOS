interface JsonRequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
}

export async function requestJson<T>(
  path: string,
  options: JsonRequestOptions = {},
): Promise<T> {
  const response = await fetch(path, {
    method: options.method ?? "GET",
    credentials: "same-origin",
    cache: "no-store",
    signal: options.signal,
    headers:
      options.body === undefined
        ? undefined
        : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new Error(
      `The API returned an invalid response (${response.status}).`,
    );
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : undefined;
    throw new Error(
      typeof detail === "string"
        ? detail
        : detail === undefined
          ? `Request failed (${response.status}).`
          : JSON.stringify(detail),
    );
  }

  return payload as T;
}
