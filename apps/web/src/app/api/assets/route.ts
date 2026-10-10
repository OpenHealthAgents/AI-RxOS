import { proxyAiServicesRequest } from "@/lib/ai-services-proxy";

export function GET(request: Request) {
  return proxyAiServicesRequest(request, "/api/assets", "GET");
}
