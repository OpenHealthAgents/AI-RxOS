import { Badge, Card } from "@ai-rxos/ui";

const SERVICES = [
  "auth",
  "literature",
  "kg",
  "search",
  "agents",
  "workflows",
  "reports",
  "docking",
  "ai-services",
  "knowledge-service",
];

export default function AdminHome() {
  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col gap-6 px-6 py-16">
      <h1 className="text-3xl font-bold">Admin Console</h1>
      <Card title="Service registry">
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {SERVICES.map((name) => (
            <li key={name} className="flex items-center justify-between rounded border border-slate-800 px-3 py-2 text-sm">
              {name}
              <Badge tone="success">up</Badge>
            </li>
          ))}
        </ul>
      </Card>
    </main>
  );
}
