"use client";

import React from "react";
import { PatientMatchView } from "../../components/PatientMatchView";
import { useWorkspace } from "../../context/WorkspaceContext";

export default function PatientMatchPage() {
  const { allAssets } = useWorkspace();

  return <PatientMatchView assets={allAssets} />;
}
