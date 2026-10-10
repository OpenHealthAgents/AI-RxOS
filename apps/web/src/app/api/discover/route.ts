import { proxyAiServicesRequest } from "@/lib/ai-services-proxy";

export function POST(request: Request) {
  return proxyAiServicesRequest(request, "/api/discover", "POST");
}
