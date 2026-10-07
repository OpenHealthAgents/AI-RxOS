import {
  Asset,
  AssetAlias,
  AssetDevelopmentCode,
  ResolutionMatch,
  ResolutionMatchType,
  ResolutionResult,
} from "./canonical_domain";

/**
 * Normalizes an identifier, code, or name token by stripping whitespace,
 * punctuation, and uppercasing. Mirrors Python normalize_key.
 */
export function normalizeKey(text: string | null | undefined): string {
  if (!text) return "";
  return text.trim().toUpperCase().replace(/[\s\-_/.:,;()[\]{}'"]+/g, "");
}

/**
 * Basic character bigram similarity calculation (Dice's coefficient)
 * for fuzzy string matching across drug names and codes.
 */
function stringSimilarity(s1: string, s2: string): number {
  if (s1 === s2) return 1.0;
  if (s1.length < 2 || s2.length < 2) return 0.0;

  const getBigrams = (str: string): Map<string, number> => {
    const map = new Map<string, number>();
    for (let i = 0; i < str.length - 1; i++) {
      const pair = str.substring(i, i + 2);
      map.set(pair, (map.get(pair) || 0) + 1);
    }
    return map;
  };

  const b1 = getBigrams(s1);
  const b2 = getBigrams(s2);
  let intersection = 0;

  for (const [pair, count] of b1.entries()) {
    if (b2.has(pair)) {
      intersection += Math.min(count, b2.get(pair)!);
    }
  }

  const total = (s1.length - 1) + (s2.length - 1);
  return total > 0 ? (2.0 * intersection) / total : 0.0;
}

export interface ResolveOptions {
  targetHint?: string;
  companyHint?: string;
  minConfidence?: number;
}

/**
 * CanonicalAssetResolver provides multi-tier, deterministic entity resolution
 * for drug assets across development codes, generic names, brand names, former names,
 * and company codes with strict confidence score calibration.
 */
export class CanonicalAssetResolver {
  private assets = new Map<string, Asset>();
  private codeIndex = new Map<string, string>(); // normalized code -> assetId
  private genericNameIndex = new Map<string, string>(); // normalized generic -> assetId
  private formerNameIndex = new Map<string, string>(); // normalized former name -> assetId
  private companyCodeIndex = new Map<string, string>(); // normalized company code -> assetId
  private aliasIndex = new Map<string, string>(); // normalized alias -> assetId
  private nameIndex = new Map<string, string>(); // normalized preferred name -> assetId
  private tokenIndex = new Map<string, Set<string>>(); // token -> set of assetIds
  private registryIndex = new Map<string, string>(); // external registry id -> assetId

  public registerAsset(asset: Asset): Asset {
    this.assets.set(asset.id, asset);

    // 1. Preferred Name and Canonical Slug
    const normName = normalizeKey(asset.preferred_name);
    if (normName) {
      this.nameIndex.set(normName, asset.id);
      this.addToken(normName, asset.id);
    }

    if (asset.canonical_slug) {
      const normSlug = normalizeKey(asset.canonical_slug);
      if (normSlug) {
        this.nameIndex.set(normSlug, asset.id);
        this.addToken(normSlug, asset.id);
      }
    }

    // 2. Generic Name
    if (asset.generic_name) {
      const normGen = normalizeKey(asset.generic_name);
      if (normGen) {
        this.genericNameIndex.set(normGen, asset.id);
        this.addToken(normGen, asset.id);
      }
    }

    // 3. Development Codes
    if (asset.development_code) {
      const normDc = normalizeKey(asset.development_code);
      if (normDc) {
        this.codeIndex.set(normDc, asset.id);
        this.addToken(normDc, asset.id);
      }
    }

    for (const dev of asset.development_codes || []) {
      const normCode = normalizeKey(dev.code);
      if (normCode) {
        this.codeIndex.set(normCode, asset.id);
        this.addToken(normCode, asset.id);
      }
    }

    // 4. Former Names
    for (const fn of asset.former_names || []) {
      const normFn = normalizeKey(fn);
      if (normFn) {
        this.formerNameIndex.set(normFn, asset.id);
        this.addToken(normFn, asset.id);
      }
    }

    // 5. Company Codes
    for (const cc of asset.company_codes || []) {
      const normCc = normalizeKey(cc);
      if (normCc) {
        this.companyCodeIndex.set(normCc, asset.id);
        this.addToken(normCc, asset.id);
      }
    }

    // 6. Aliases & Synonyms
    for (const al of asset.aliases || []) {
      const normAl = normalizeKey(al.alias);
      if (normAl) {
        this.aliasIndex.set(normAl, asset.id);
        this.addToken(normAl, asset.id);
      }
    }

    // 7. Identity Registry Identifiers
    if (asset.identity?.registry_identifiers) {
      for (const regVal of Object.values(asset.identity.registry_identifiers)) {
        const normReg = normalizeKey(regVal);
        if (normReg) {
          this.registryIndex.set(normReg, asset.id);
          this.addToken(normReg, asset.id);
        }
      }
    }

    return asset;
  }

  private addToken(token: string, assetId: string): void {
    let set = this.tokenIndex.get(token);
    if (!set) {
      set = new Set<string>();
      this.tokenIndex.set(token, set);
    }
    set.add(assetId);
  }

  public getAsset(assetId: string): Asset | undefined {
    const asset = this.assets.get(assetId);
    if (asset && asset.is_deprecated && asset.merged_into_asset_id) {
      return this.assets.get(asset.merged_into_asset_id);
    }
    return asset;
  }

  private buildMatch(
    asset: Asset,
    matchedTerm: string,
    matchType: ResolutionMatchType,
    confidence: number
  ): ResolutionMatch {
    return {
      asset_id: asset.id,
      canonical_name: asset.preferred_name,
      matched_term: matchedTerm,
      match_type: matchType,
      confidence: Math.round(confidence * 1000) / 1000,
      is_canonical: true,
      target: asset.target || asset.primary_target_symbol || "",
      modality: asset.modality || asset.modality_code || "",
      owner: asset.owner || asset.owner_company_name || null,
      stage: asset.stage || asset.current_development_stage || null,
    };
  }

  public resolve(query: string, options: ResolveOptions = {}): ResolutionResult {
    const normQ = normalizeKey(query);
    if (!normQ) {
      return {
        query,
        resolved: false,
        confidence: 0,
        match_type: "UNRESOLVED",
        candidates: [],
      };
    }

    const { targetHint, companyHint, minConfidence = 0.75 } = options;

    // 1. Exact match on Primary Name (Confidence: 1.0)
    if (this.nameIndex.has(normQ)) {
      const asset = this.getAsset(this.nameIndex.get(normQ)!);
      if (asset) {
        return {
          query,
          resolved: true,
          confidence: 1.0,
          match_type: "PRIMARY_NAME",
          match: this.buildMatch(asset, query, "PRIMARY_NAME", 1.0),
          candidates: [],
        };
      }
    }

    // 2. Exact match on Generic Name (Confidence: 1.0)
    if (this.genericNameIndex.has(normQ)) {
      const asset = this.getAsset(this.genericNameIndex.get(normQ)!);
      if (asset) {
        return {
          query,
          resolved: true,
          confidence: 1.0,
          match_type: "GENERIC_NAME",
          match: this.buildMatch(asset, query, "GENERIC_NAME", 1.0),
          candidates: [],
        };
      }
    }

    // 3. Exact match on Development Code (Confidence: 1.0)
    if (this.codeIndex.has(normQ)) {
      const asset = this.getAsset(this.codeIndex.get(normQ)!);
      if (asset) {
        return {
          query,
          resolved: true,
          confidence: 1.0,
          match_type: "DEVELOPMENT_CODE",
          match: this.buildMatch(asset, query, "DEVELOPMENT_CODE", 1.0),
          candidates: [],
        };
      }
    }

    // 4. Exact match on Registry ID (Confidence: 1.0)
    if (this.registryIndex.has(normQ)) {
      const asset = this.getAsset(this.registryIndex.get(normQ)!);
      if (asset) {
        return {
          query,
          resolved: true,
          confidence: 1.0,
          match_type: "REGISTRY_ID",
          match: this.buildMatch(asset, query, "REGISTRY_ID", 1.0),
          candidates: [],
        };
      }
    }

    // 5. Exact match on Company Code (Confidence: 0.98)
    if (this.companyCodeIndex.has(normQ)) {
      const asset = this.getAsset(this.companyCodeIndex.get(normQ)!);
      if (asset) {
        return {
          query,
          resolved: true,
          confidence: 0.98,
          match_type: "COMPANY_CODE",
          match: this.buildMatch(asset, query, "COMPANY_CODE", 0.98),
          candidates: [],
        };
      }
    }

    // 6. Exact match on Former Name (Confidence: 0.95)
    if (this.formerNameIndex.has(normQ)) {
      const asset = this.getAsset(this.formerNameIndex.get(normQ)!);
      if (asset) {
        return {
          query,
          resolved: true,
          confidence: 0.95,
          match_type: "FORMER_NAME",
          match: this.buildMatch(asset, query, "FORMER_NAME", 0.95),
          candidates: [],
        };
      }
    }

    // 7. Exact match on Synonyms / Aliases (Confidence: 0.95)
    if (this.aliasIndex.has(normQ)) {
      const asset = this.getAsset(this.aliasIndex.get(normQ)!);
      if (asset) {
        return {
          query,
          resolved: true,
          confidence: 0.95,
          match_type: "ALIAS",
          match: this.buildMatch(asset, query, "ALIAS", 0.95),
          candidates: [],
        };
      }
    }

    // 8. Normalized Token Set Match (Confidence: 0.98)
    if (this.tokenIndex.has(normQ)) {
      const matchingIds = Array.from(this.tokenIndex.get(normQ)!);
      if (matchingIds.length === 1 && matchingIds[0]) {
        const asset = this.getAsset(matchingIds[0]);
        if (asset) {
          return {
            query,
            resolved: true,
            confidence: 0.98,
            match_type: "NORMALIZED_TOKEN",
            match: this.buildMatch(asset, query, "NORMALIZED_TOKEN", 0.98),
            candidates: [],
          };
        }
      } else if (matchingIds.length > 1) {
        const candidates = matchingIds
          .map((aid) => this.getAsset(aid))
          .filter((a): a is Asset => Boolean(a))
          .map((a) => this.buildMatch(a, query, "NORMALIZED_TOKEN", 0.85));

        return {
          query,
          resolved: false,
          confidence: 0.85,
          match_type: "AMBIGUOUS",
          candidates,
          disambiguation_notes: `Multiple assets (${candidates.length}) match normalized token '${normQ}'.`,
        };
      }
    }

    // 9. Partial / Code Substring with Contextual Agreement
    for (const [code, assetId] of this.codeIndex.entries()) {
      if (normQ.includes(code) || code.includes(normQ)) {
        const asset = this.getAsset(assetId);
        if (asset) {
          let score = 0.90;
          const targetMatch = Boolean(targetHint && (asset.target || asset.primary_target_symbol)?.toUpperCase() === targetHint.toUpperCase());
          const ownerStr = asset.owner || asset.owner_company_name;
          const companyMatch = Boolean(companyHint && ownerStr && ownerStr.toUpperCase().includes(companyHint.toUpperCase()));

          if (targetMatch && companyMatch) score = 0.98;
          else if (targetMatch || companyMatch) score = 0.96;

          return {
            query,
            resolved: true,
            confidence: score,
            match_type: "CONTEXTUAL_MATCH",
            match: this.buildMatch(asset, code, "CONTEXTUAL_MATCH", score),
            candidates: [],
            disambiguation_notes: "Resolved via substring pattern and contextual corroboration.",
          };
        }
      }
    }

    // 10. Fuzzy Match
    const allTerms = new Map<string, string>([
      ...this.codeIndex,
      ...this.nameIndex,
      ...this.aliasIndex,
      ...this.genericNameIndex,
    ]);

    const candidates: ResolutionMatch[] = [];
    for (const [term, assetId] of allTerms.entries()) {
      const asset = this.getAsset(assetId);
      if (!asset) continue;

      const rawSim = stringSimilarity(normQ, term);
      if (rawSim >= 0.70) {
        let boostedSim = rawSim;
        const targetStr = asset.target || asset.primary_target_symbol;
        if (targetHint && targetStr && targetStr.toUpperCase() === targetHint.toUpperCase()) {
          boostedSim = Math.min(boostedSim + 0.05, 0.95);
        }
        const ownerStr = asset.owner || asset.owner_company_name;
        if (companyHint && ownerStr && ownerStr.toUpperCase().includes(companyHint.toUpperCase())) {
          boostedSim = Math.min(boostedSim + 0.05, 0.95);
        }

        candidates.push(this.buildMatch(asset, term, "FUZZY", boostedSim));
      }
    }

    candidates.sort((a, b) => b.confidence - a.confidence);

    if (candidates.length > 0) {
      const best = candidates[0];
      if (best && best.confidence >= minConfidence) {
        if (candidates.length > 1) {
          const second = candidates[1];
          if (second && second.asset_id !== best.asset_id && (best.confidence - second.confidence) < 0.03) {
            return {
              query,
              resolved: false,
              confidence: best.confidence,
              match_type: "AMBIGUOUS",
              candidates: candidates.slice(0, 3),
              disambiguation_notes: `Ambiguous fuzzy match between '${best.canonical_name}' (${best.confidence}) and '${second.canonical_name}' (${second.confidence}).`,
            };
          }
        }

        return {
          query,
          resolved: true,
          confidence: best.confidence,
          match_type: "FUZZY",
          match: best,
          candidates,
          disambiguation_notes: `Fuzzy reconciled with ${Math.round(best.confidence * 1000) / 10}% confidence.`,
        };
      }
    }

    return {
      query,
      resolved: false,
      confidence: 0,
      match_type: "UNRESOLVED",
      candidates: [],
    };
  }

  public resolveMultiple(
    queries: string[],
    options: ResolveOptions = {}
  ): Record<string, ResolutionResult> {
    const res: Record<string, ResolutionResult> = {};
    for (const q of queries) {
      res[q] = this.resolve(q, options);
    }
    return res;
  }

  /**
   * Consolidates multiple names to verify they point to the exact same canonical asset.
   */
  public consolidateNames(
    names: string[],
    options: ResolveOptions = {}
  ): {
    canonicalAsset: Asset | null;
    jointConfidence: number;
    results: Record<string, ResolutionResult>;
  } {
    const results = this.resolveMultiple(names, options);
    const resolvedIds = new Set<string>();
    const confidences: number[] = [];

    for (const res of Object.values(results)) {
      if (res.resolved && res.match) {
        resolvedIds.add(res.match.asset_id);
        confidences.push(res.confidence);
      }
    }

    if (resolvedIds.size === 1) {
      const assetId = Array.from(resolvedIds)[0];
      if (assetId) {
        const canonicalAsset = this.getAsset(assetId) || null;
        const jointConfidence = confidences.length > 0
          ? Math.round((confidences.reduce((a, b) => a + b, 0) / confidences.length) * 1000) / 1000
          : 1.0;

        return { canonicalAsset, jointConfidence, results };
      }
    }

    return { canonicalAsset: null, jointConfidence: 0, results };
  }
}
