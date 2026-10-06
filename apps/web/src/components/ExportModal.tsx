"use client";

import React, { useState } from "react";
import { AssetIntelligence } from "../lib/types";

export interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  asset1: AssetIntelligence;
  asset2: AssetIntelligence;
  target: string;
  indication: string;
  setting: string;
}

export function ExportModal({
  isOpen,
  onClose,
  asset1,
  asset2,
  target,
  indication,
  setting,
}: ExportModalProps) {
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const markdownContent = `# Decision Intelligence Dossier: ${asset1.name} vs ${asset2.name}

**Target:** ${target}  
**Indication:** ${indication}  
**Setting:** ${setting}  
**Date Generated:** ${new Date().toISOString().split("T")[0]}  
**Platform:** NeoZenome Decision Intelligence Engine  

---

## 1. Executive Recommendations

- **${asset1.name} (${asset1.code_name || ""}):** [${asset1.recommendation.action}] ${asset1.recommendation.badge_text}
  - *Rationale:* ${asset1.recommendation.rationale}
  - *Development Potential:* ${asset1.recommendation.development_potential_score}% (${asset1.recommendation.development_potential_tier})
  - *Confidence:* ${(asset1.recommendation.confidence * 100).toFixed(0)}%

- **${asset2.name} (${asset2.code_name || ""}):** [${asset2.recommendation.action}] ${asset2.recommendation.badge_text}
  - *Rationale:* ${asset2.recommendation.rationale}
  - *Development Potential:* ${asset2.recommendation.development_potential_score}% (${asset2.recommendation.development_potential_tier})
  - *Confidence:* ${(asset2.recommendation.confidence * 100).toFixed(0)}%

---

## 2. Multi-Dimensional Biology Radar

| Metric | ${asset1.name} | ${asset2.name} |
| :--- | :--- | :--- |
| Target Selectivity | ${asset1.biology_profile.target_selectivity} / 100 | ${asset2.biology_profile.target_selectivity} / 100 |
| Potency (IC50) | ${asset1.biology_profile.potency} / 100 | ${asset2.biology_profile.potency} / 100 |
| Safety & Therapeutic Index | ${asset1.biology_profile.safety_ti} / 100 | ${asset2.biology_profile.safety_ti} / 100 |
| Clinical Readiness | ${asset1.biology_profile.clinical_readiness} / 100 | ${asset2.biology_profile.clinical_readiness} / 100 |
| Biomarker Strategy | ${asset1.biology_profile.biomarker_strategy} / 100 | ${asset2.biology_profile.biomarker_strategy} / 100 |
| CNS / Intracranial Penetration | ${asset1.biology_profile.cns_potential} / 100 | ${asset2.biology_profile.cns_potential} / 100 |

---

## 3. Stage Transition Probability (Model v0.1)

| Transition Phase | ${asset1.name} | ${asset2.name} (historical) |
| :--- | :--- | :--- |
| Preclinical → IND | ${(asset1.stage_transitions.preclinical_to_ind * 100).toFixed(0)}% | ${(asset2.stage_transitions.preclinical_to_ind * 100).toFixed(0)}% |
| Phase I → II | ${(asset1.stage_transitions.phase_i_to_ii * 100).toFixed(0)}% | ${(asset2.stage_transitions.phase_i_to_ii * 100).toFixed(0)}% |
| Phase II → III | ${(asset1.stage_transitions.phase_ii_to_iii * 100).toFixed(0)}% | ${(asset2.stage_transitions.phase_ii_to_iii * 100).toFixed(0)}% |
| Phase III → Approval | ${(asset1.stage_transitions.phase_iii_to_approval * 100).toFixed(0)}% | ${(asset2.stage_transitions.phase_iii_to_approval * 100).toFixed(0)}% |

---

## 4. Key Attributes Comparison

| Attribute | ${asset1.name} | ${asset2.name} |
| :--- | :--- | :--- |
| Selectivity | ${asset1.key_attributes["Selectivity"] || "-"} | ${asset2.key_attributes["Selectivity"] || "-"} |
| IC50 (HER2) | ${asset1.key_attributes["IC50 (HER2)"] || "-"} | ${asset2.key_attributes["IC50 (HER2)"] || "-"} |
| Activity in HER2 Mutants | ${asset1.key_attributes["Activity in HER2 mutants"] || "-"} | ${asset2.key_attributes["Activity in HER2 mutants"] || "-"} |
| CNS Penetration (preclinical) | ${asset1.key_attributes["CNS penetration (preclinical)"] || "-"} | ${asset2.key_attributes["CNS penetration (preclinical)"] || "-"} |
| Main Differentiation | ${asset1.key_attributes["Main differentiation"] || "-"} | ${asset2.key_attributes["Main differentiation"] || "-"} |
| Owner / Sponsor | ${asset1.owner} | ${asset2.owner} |
| Patent Exclusivity Window | ${asset1.business_profile.patent_ip} | ${asset2.business_profile.patent_ip} |

---

## 5. Verified Evidence Provenance

### ${asset1.name} Citations
${asset1.supporting_evidence
  .map(
    (e) => `- **[${e.source_ref}]** *${e.title}* (${e.publication_year}). Citation: ${e.citation}. Excerpt: "${e.excerpt}"`
  )
  .join("\n")}

### ${asset2.name} Citations
${asset2.supporting_evidence
  .map(
    (e) => `- **[${e.source_ref}]** *${e.title}* (${e.publication_year}). Citation: ${e.citation}. Excerpt: "${e.excerpt}"`
  )
  .join("\n")}

---

## 6. Disclaimers
*Scientific, licensing, and investment conclusions must be verified by human domain experts. IP and patent exclusivity notes do not constitute formal legal opinion or Freedom-to-Operate clearance.*
`;

  const handleCopy = () => {
    navigator.clipboard.writeText(markdownContent);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([markdownContent], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `NeoZenome_${asset1.name}_vs_${asset2.name}_Dossier.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-3xl rounded-xl border border-slate-200 bg-white shadow-2xl overflow-hidden my-8">
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white">
              ⬇️
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">
                Export Decision Dossier
              </h2>
              <p className="text-xs text-slate-500">
                Audited Markdown export with full provenance and transition probabilities
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
          >
            ✕
          </button>
        </div>

        <div className="p-6">
          <div className="rounded-lg border border-slate-200 bg-slate-900 text-slate-200 p-4 font-mono text-xs max-h-96 overflow-y-auto whitespace-pre-wrap">
            {markdownContent}
          </div>
        </div>

        <div className="border-t border-slate-200 bg-slate-50 px-6 py-3 flex items-center justify-between">
          <div className="text-xs text-slate-500">
            Format: GitHub Flavored Markdown (.md)
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleCopy}
              className="rounded-md border border-slate-300 bg-white px-4 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              {copied ? "✓ Copied to Clipboard" : "Copy Markdown"}
            </button>
            <button
              onClick={handleDownload}
              className="rounded-md bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-500"
            >
              Download Dossier (.md)
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
