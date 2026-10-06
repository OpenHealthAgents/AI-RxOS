import { NextResponse } from "next/server";
import { ALL_ASSETS } from "@/lib/data";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const target = searchParams.get("target");
  const action = searchParams.get("action");

  let filtered = ALL_ASSETS;
  if (target) {
    filtered = filtered.filter((a) => a.target.toLowerCase() === target.toLowerCase());
  }
  if (action) {
    filtered = filtered.filter((a) => a.recommendation.action === action);
  }

  return NextResponse.json(filtered);
}
