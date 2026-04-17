/**
 * Helpers for reading defaults from the workspace's active template.
 *
 * Each function takes the (possibly-null) active template and returns either
 * the template-provided default or a Taiwan-specific fallback. Templates
 * declare their own defaults in `data/templates/*.json` under the `election`
 * block.
 *
 * Civatas-TW: defaults are Taiwan-contextual (ROC central government,
 * 直轄市/縣市 local units, 中選會 election cycles, 主權/兩岸/民生 議題).
 *
 * Usage from a panel:
 *
 *   const { template } = useActiveTemplate(wsId);
 *   const macro = getDefaultMacroContext(template, locale);
 *   const params = getDefaultCalibParams(template);
 *   const partyColor = makePartyColorResolver(template);
 */

// ── Taiwan fallback defaults (used when no template is active) ──

const TW_DEFAULT_MACRO_ZH =
  "[台灣政治經濟現況]\n" +
  "中央政府由總統與行政院領導；立法院的席次分配在民進黨、國民黨、民眾黨之間。" +
  "選民通常把全國性議題（通膨、能源、外交、兩岸關係、國防）歸因於中央執政黨，" +
  "地方性議題（治安、學校、交通、縣市治理）歸因於縣市長與地方政府。" +
  "兩岸關係、美中台三角、抗中保台 vs 和平交流 是台灣政治長期軸線。";

const TW_DEFAULT_MACRO_EN =
  "[Taiwan Political & Economic Context]\n" +
  "The central government is headed by the President and Executive Yuan; " +
  "Legislative Yuan seats are split among DPP, KMT, and TPP. Voters attribute " +
  "national-scope issues (inflation, energy, cross-strait relations, defense) " +
  "to the ruling party at the central level, and local-scope issues " +
  "(public safety, schools, transit, county services) to county mayors and " +
  "local government. Cross-strait relations and US-China-Taiwan triangle " +
  "dynamics are the central long-term political axis.";

const TW_DEFAULT_LOCAL_KW =
  "縣市長預算 施政\n" +
  "縣市議會 議案\n" +
  "捷運 公車 交通建設\n" +
  "產業 就業 失業\n" +
  "國中小 課綱 教育經費\n" +
  "治安 警察 毒品\n" +
  "健保 醫院 長照\n" +
  "地方選舉 候選人 民調";

const TW_DEFAULT_NATIONAL_KW =
  "總統 行政院 內閣\n" +
  "立法院 法案 朝野協商\n" +
  "經濟 通膨 央行 升息\n" +
  "就業 薪資 基本工資\n" +
  "大選 民進黨 國民黨 民眾黨 民調\n" +
  "兩岸 中國 美國 外交\n" +
  "國防 軍購 兵役\n" +
  "健保 能源 核能 非核";

const US_DEFAULT_ELECTION_TYPE = "總統大選";

const US_DEFAULT_SANDBOX_QUERY = "台灣總統大選 民調 經濟 兩岸";

const US_DEFAULT_CALIB_PARAMS = {
  news_impact: 2.0,
  delta_cap_mult: 1.5,
  decay_rate_mult: 0.5,
  forget_rate: 0.15,
  recognition_penalty: 0.15,
  base_undecided: 0.10,
  max_undecided: 0.45,
  party_align_bonus: 15,
  incumbency_bonus: 12,
};

// ── Helpers ──

export type ActiveTemplate = any | null;

/** Default macro context — template-aware; TW 預設繁中。 */
export function getDefaultMacroContext(template: ActiveTemplate, locale: string = "zh-TW"): string {
  const fromTemplate = template?.election?.default_macro_context;
  if (fromTemplate) {
    return fromTemplate[locale] || fromTemplate["zh-TW"] || fromTemplate["en"] || TW_DEFAULT_MACRO_ZH;
  }
  return locale === "en" ? TW_DEFAULT_MACRO_EN : TW_DEFAULT_MACRO_ZH;
}

/** Default local search keywords. */
export function getDefaultLocalKeywords(template: ActiveTemplate): string {
  return template?.election?.default_search_keywords?.local || TW_DEFAULT_LOCAL_KW;
}

/** Default national search keywords. */
export function getDefaultNationalKeywords(template: ActiveTemplate): string {
  return template?.election?.default_search_keywords?.national || TW_DEFAULT_NATIONAL_KW;
}

/** Default sandbox auto-fetch query (single-line, fewer keywords). */
export function getDefaultSandboxQuery(_template: ActiveTemplate): string {
  return US_DEFAULT_SANDBOX_QUERY;
}

/** Default election type label (used in CalibrationPanel state default). */
export function getDefaultElectionType(template: ActiveTemplate): string {
  const t = template?.election?.type;
  if (!t) return US_DEFAULT_ELECTION_TYPE;
  if (t === "presidential") return "總統大選";
  if (t === "senate") return "立委選舉";  // legacy (Senate concept doesn't map to TW exactly)
  if (t === "gubernatorial") return "縣市長選舉";
  if (t === "house") return "立委選舉";
  if (t === "mayoral") return "直轄市長選舉";
  if (t === "poll") return "民意調查";
  return t;
}

/** Default calibration params (template values merged with US defaults). */
export function getDefaultCalibParams(template: ActiveTemplate): typeof US_DEFAULT_CALIB_PARAMS {
  const overrides = template?.election?.default_calibration_params;
  if (!overrides) return { ...US_DEFAULT_CALIB_PARAMS };
  return { ...US_DEFAULT_CALIB_PARAMS, ...overrides };
}

/**
 * Default Vote Weighting (sampling_modality) per template.
 * Real-world turnout in US elections consistently favors older voters,
 * so "mixed_73" (Likely Voter) matches actual outcomes best for forecasting.
 *
 *  - presidential / senate / gubernatorial / house / mayoral → "mixed_73"
 *  - If template explicitly sets `election.default_sampling_modality`, use it.
 *  - Fallback → "mixed_73" (best for any US general election).
 *  - If no election block → "unweighted" (raw popular vote).
 */
export function getDefaultSamplingModality(template: ActiveTemplate): "unweighted" | "mixed_73" | "landline_only" {
  const override = (template as any)?.election?.default_sampling_modality;
  if (override === "unweighted" || override === "mixed_73" || override === "landline_only") {
    return override;
  }
  const electionType = template?.election?.type;
  if (!electionType) return "unweighted";
  if (["presidential", "senate", "gubernatorial", "house", "mayoral"].includes(electionType)) {
    return "mixed_73";
  }
  return "mixed_73";
}

/** Default KOL settings. */
export function getDefaultKolSettings(template: ActiveTemplate): { enabled: boolean; ratio: number; reach: number } {
  return template?.election?.default_kol || { enabled: false, ratio: 0.05, reach: 0.40 };
}

/** Default poll groups (used in PredictionPanel scenario tab). */
export function getDefaultPollGroups(template: ActiveTemplate): Array<{ id: string; name: string; weight: number }> {
  return template?.election?.default_poll_groups || [
    { id: "default", name: "Likely Voters", weight: 100 },
  ];
}

/** Default party base scores (keyed by party id, e.g. "D"/"R"/"I"). */
export function getDefaultPartyBaseScores(template: ActiveTemplate): Record<string, number> {
  return template?.election?.party_base_scores || {};
}

/**
 * Stage 1.8.2: candidates declared inside the template's election block.
 * Returns the raw candidate objects (id, name, party, party_label,
 * is_incumbent, color, description). Empty array if the template has none.
 */
export type TemplateCandidate = {
  id: string;
  name: string;
  party?: string;
  party_label?: string;
  is_incumbent?: boolean;
  color?: string;
  description?: string;
};
export function getDefaultCandidates(template: ActiveTemplate): TemplateCandidate[] {
  const cands = template?.election?.candidates;
  if (!Array.isArray(cands)) return [];
  return cands as TemplateCandidate[];
}

/**
 * Per-candidate base scores resolved from the template. Maps each candidate's
 * name to the party_base_score for their party id (D/R/I/...). Returns {}
 * when the template has no candidates or no party_base_scores.
 */
export function getDefaultCandidateBaseScores(template: ActiveTemplate): Record<string, number> {
  const cands = getDefaultCandidates(template);
  const partyScores = getDefaultPartyBaseScores(template);
  const out: Record<string, number> = {};
  for (const c of cands) {
    if (!c.name) continue;
    const score = c.party && partyScores[c.party] != null ? partyScores[c.party] : undefined;
    if (score != null) out[c.name] = score;
  }
  return out;
}

/**
 * Default prediction question — used when the user hasn't typed one and a
 * template is active. Falls back to a generic election prompt.
 */
export function getDefaultPredictionQuestion(template: ActiveTemplate): string {
  if (!template?.election) return "";
  const e = template.election;
  // Cycle-specific (e.g. 2024 總統大選)
  if (e.cycle && e.type === "presidential") {
    return `${e.cycle} 總統大選`;
  }
  if (e.type === "presidential") return "總統大選";
  if (e.type === "senate") return "立委選舉";
  if (e.type === "gubernatorial") return "縣市長選舉";
  if (e.type === "house") return "立委選舉";
  if (e.type === "mayoral") return "直轄市長選舉";
  if (e.type === "poll") return "民意調查";
  return "";
}

/** Stage 1.8: Default Evolution-panel params (sim_days, search_interval, etc.) */
export interface EvolutionParams {
  sim_days: number;
  search_interval: number;
  use_dynamic_search: boolean;
  neutral_ratio: number;
  delta_cap_mult: number;
  individuality_mult: number;
  concurrency: number;
}
const TW_DEFAULT_EVOLUTION_PARAMS: EvolutionParams = {
  sim_days: 60,
  search_interval: 3,
  use_dynamic_search: true,
  neutral_ratio: 0.15,
  delta_cap_mult: 1.5,
  individuality_mult: 1.0,
  concurrency: 5,
};
export function getDefaultEvolutionParams(template: ActiveTemplate): EvolutionParams {
  const overrides = template?.election?.default_evolution_params;
  if (!overrides) return { ...TW_DEFAULT_EVOLUTION_PARAMS };
  return { ...TW_DEFAULT_EVOLUTION_PARAMS, ...overrides };
}

/** Stage 1.8: Default evolution time window (cycle templates only). Returns
 *  null if the template doesn't specify one — caller should use its own fallback. */
export function getDefaultEvolutionWindow(template: ActiveTemplate): { start_date: string; end_date: string } | null {
  const win = template?.election?.default_evolution_window;
  if (!win || !win.start_date || !win.end_date) return null;
  return { start_date: win.start_date, end_date: win.end_date };
}

/** Stage 1.8: Default alignment-target settings. */
export function getDefaultAlignment(template: ActiveTemplate): { mode: "none" | "election" | "satisfaction" } {
  const m = template?.election?.default_alignment?.mode;
  if (m === "election" || m === "satisfaction" || m === "none") return { mode: m };
  return { mode: "none" };
}

// ── Party color resolver ──

// TW default party detection patterns — used as fallback when no template
// is active or the active template has no election block.
// Keys are 3-letter TW party codes matching what evolver.py and templates use.
const US_PARTY_DETECTION: Record<string, string[]> = {
  DPP: ["民進黨", "民主進步黨", "dpp", "綠營", "賴清德", "蕭美琴", "蔡英文", "沈伯洋", "何欣純", "賴瑞隆"],
  KMT: ["國民黨", "中國國民黨", "kmt", "藍營", "侯友宜", "盧秀燕", "蔣萬安", "韓國瑜", "鄭麗文", "江啟臣", "柯志恩"],
  TPP: ["民眾黨", "台灣民眾黨", "tpp", "白營", "白色力量", "柯文哲", "黃國昌", "麥玉珍"],
  IND: ["無黨籍", "獨立參選", "無黨"],
};
const US_PARTY_PALETTE: Record<string, string[]> = {
  DPP: ["#1B9431", "#1B9431"],   // 綠營
  KMT: ["#000095", "#000095"],   // 藍營
  TPP: ["#28C8C8", "#28C8C8"],   // 白營（偏青）
  IND: ["#6B7280", "#6B7280"],   // 獨立
};

/**
 * Build a `partyColor(name: string) => string` function that uses the
 * template's party_palette + party_detection rules first, falling back to
 * generic US D/R/I detection.
 */
export function makePartyColorResolver(template: ActiveTemplate): (s: string) => string {
  const detection = (template?.election?.party_detection as Record<string, string[]> | undefined) || US_PARTY_DETECTION;
  const palette   = (template?.election?.party_palette   as Record<string, string[]> | undefined) || US_PARTY_PALETTE;

  return function partyColor(s: string): string {
    if (!s) return "#888";
    const text = s.toLowerCase();
    for (const [partyId, patterns] of Object.entries(detection)) {
      for (const pat of patterns) {
        if (text.includes(pat.toLowerCase())) {
          const colors = palette[partyId];
          if (colors && colors.length > 0) return colors[1] || colors[0];
        }
      }
    }
    return "#94a3b8"; // neutral slate
  };
}

/**
 * Build a `partyId(name, desc) => "D" | "R" | "I" | null` function for
 * PredictionPanel's PARTY_PALETTES lookups. Uses the template detection
 * first; falls back to generic US D/R/I patterns.
 */
export function makePartyIdResolver(template: ActiveTemplate): (name: string, description?: string) => string | null {
  const detection = (template?.election?.party_detection as Record<string, string[]> | undefined) || US_PARTY_DETECTION;

  return function detectPartyId(name: string, description: string = ""): string | null {
    const text = `${name} ${description}`.toLowerCase();
    for (const [partyId, patterns] of Object.entries(detection)) {
      for (const pat of patterns) {
        if (text.includes(pat.toLowerCase())) return partyId;
      }
    }
    return null;
  };
}
