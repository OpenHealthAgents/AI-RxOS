import { NextResponse } from "next/server";
import { ALL_ASSETS } from "@/lib/data";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const assetIds: string[] = body.asset_ids || ["zongertinib", "neratinib"];
    const target = body.target || "HER2";
    const indication = body.indication || "Breast Cancer";
    const setting = body.setting || "Metastatic";

    // Attempt to proxy to FastAPI backend if available
    try {
      const backendUrl = process.env.AI_SERVICES_URL || "http://localhost:8090";
      const resp = await fetch(`${backendUrl}/api/v1/decision/compare`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: assetIds, target, indication, setting }),
        signal: AbortSignal.timeout(1500),
      });
      if (resp.ok) {
        const data = await resp.json();
        return NextResponse.json(data);
      }
    } catch {
      // Fallback to local computation
    }

    const assets = ALL_ASSETS.filter((a) => assetIds.includes(a.id));

    return NextResponse.json({
      target,
      indication,
      setting,
      assets,
      comparison_summary: `Head-to-head comparison for ${target} in ${indication} (${setting}).`,
      key_differentiators: [
        "Mutant-selectivity vs Pan-HER off-target inhibition",
        "CNS intracranial brain-to-plasma penetration",
        "Therapeutic index & GI tolerability profile",
      ],
      head_to_head_advantages: {
        zongertinib: ["Mutant-selective", "Brain-penetrant", "Low diarrhea rate"],
        neratinib: ["Approved status", "Established clinical benchmark"],
      },
      recommendation_summary: {
        zongertinib: "High-Priority Asset - PURSUE",
        neratinib: "Established Asset - NICHE USE",
      },
    });
  } catch (error) {
    return NextResponse.json({ error: String(error) }, { status: 400 });
  }
}
