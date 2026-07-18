import { Badge, Button, Card } from "@ai-rxos/ui";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-6 px-6 py-16">
      <div className="flex items-center gap-3">
        <h1 className="text-3xl font-bold">AI-RxOS</h1>
        <Badge tone="success">operational</Badge>
      </div>
      <p className="text-slate-400">
        AI-native drug discovery workspace — literature intelligence, knowledge graph,
        molecule design, and agentic workflows in one platform.
      </p>
      <Card title="Get started">
        <p className="mb-4 text-sm text-slate-400">
          This app talks to the API Gateway at{" "}
          <code>{process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8080"}</code>.
        </p>
        <Button>Open workspace</Button>
      </Card>
    </main>
  );
}
