"use client";

import React from "react";
import { BacktestView } from "../../components/BacktestView";
import { useWorkspace } from "../../context/WorkspaceContext";

export default function BacktestPage() {
  const { allAssets } = useWorkspace();

  return <BacktestView assets={allAssets} />;
}
