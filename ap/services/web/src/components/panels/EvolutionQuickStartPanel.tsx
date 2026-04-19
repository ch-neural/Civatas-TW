"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import {
  startEvolution,
  getEvolutionStatus,
  triggerCrawl,
  getNewsPool,
  injectNewsArticle,
  getWorkspacePersonas,
  saveUiSettings,
  getUiSettings,
  saveSnapshot,
} from "@/lib/api";
import { useActiveTemplate } from "@/hooks/use-active-template";
import { useLocaleStore } from "@/store/locale-store";
import { useShellStore } from "@/store/shell-store";

/* ── helpers ── */

function electionDate(cycle: number | null | undefined): string {
  // US presidential election: first Tuesday after first Monday in November
  if (!cycle) return "";
  const nov1 = new Date(cycle, 10, 1); // Nov 1
  const dayOfWeek = nov1.getDay(); // 0=Sun
  const firstMonday = dayOfWeek <= 1 ? 1 + (1 - dayOfWeek) : 1 + (8 - dayOfWeek);
  const elDay = firstMonday + 1; // Tuesday after first Monday
  return `${cycle}-11-${String(elDay).padStart(2, "0")}`;
}

function addDays(dateStr: string, days: number): string {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function daysBetween(a: string, b: string): number {
  return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000);
}

function fmtDate(d: string, en: boolean): string {
  if (!d) return "—";
  const dt = new Date(d);
  return en
    ? dt.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : dt.toLocaleDateString("zh-TW", { month: "long", day: "numeric", year: "numeric" });
}

/* ── default advanced parameters ── */

const DEFAULT_ADV_PARAMS = {
  // Political leaning shifts
  enable_dynamic_leaning: true,
  shift_sat_threshold_low: 20,
  shift_anx_threshold_high: 80,
  shift_consecutive_days_req: 5,
  // News impact & echo chamber
  news_impact: 2.0,
  serendipity_rate: 0.05,
  articles_per_agent: 3,
  forget_rate: 0.15,
  // Emotional response
  delta_cap_mult: 1.5,
  satisfaction_decay: 0.02,
  anxiety_decay: 0.05,
  // Undecided & party effects
  base_undecided: 0.10,
  max_undecided: 0.45,
  party_align_bonus: 15,
  incumbency_bonus: 12,
  // Life events & individuality
  individuality_multiplier: 1.0,
  neutral_ratio: 0.0,
  // News category mix (must sum to 100)
  news_mix_candidate: 25,
  news_mix_national: 35,
  news_mix_local: 30,
  news_mix_international: 10,
  // Feed stratification (MEDIA_HABIT_EXPOSURE_MIX)
  use_exposure_mix: false,
  replication_seed: 0,
};

type AdvParams = typeof DEFAULT_ADV_PARAMS;

/* ── Time-compression auto-scaling ──
 * Each virtual day represents (realDateRange / simDays) real days. If the user
 * shrinks simDays or widens the date range, each virtual day covers more real
 * time, so time-scale-dependent params (news_impact / decay / life-event rate
 * / leaning-shift consecutive-days requirement) must scale accordingly.
 *
 * Scale factor = currentCompression / templateRefCompression.
 *   factor > 1 → each virtual day is MORE compressed than template baseline
 *                → news_impact ↑, decay ↑, shift_consecutive_days_req ↓
 *   factor < 1 → each virtual day covers LESS real time → inverse
 *
 * Baseline is always the template's calibration (NOT current advParams) so the
 * scale can be re-applied on each simDays / date change without compounding.
 */
function computeCompression(startStr: string, endStr: string, days: number): number {
  if (!startStr || !endStr || !days || days <= 0) return 1;
  const s = new Date(startStr).getTime();
  const e = new Date(endStr).getTime();
  if (isNaN(s) || isNaN(e) || e <= s) return 1;
  const realDays = (e - s) / 86400000;
  return Math.max(0.1, realDays / days);
}

function clampNum(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

function scaleTimeDependentParams(baseline: AdvParams, factor: number): AdvParams {
  if (Math.abs(factor - 1) < 0.02) return baseline; // noise band
  const sqrtF = Math.sqrt(factor);
  return {
    ...baseline,
    // News impact scales sub-linearly — doubling compression shouldn't fully
    // double LLM shock; sqrt gives diminishing returns.
    news_impact: Math.round(clampNum(baseline.news_impact * sqrtF, 0.5, 5.0) * 10) / 10,
    // Consecutive-days threshold is linear: compressed time needs fewer days.
    shift_consecutive_days_req: clampNum(
      Math.round(baseline.shift_consecutive_days_req / factor),
      1, 14,
    ),
    // Decay / mean-reversion scale linearly with real-time-per-virtual-day.
    satisfaction_decay: Math.round(clampNum(baseline.satisfaction_decay * factor, 0, 0.1) * 1000) / 1000,
    anxiety_decay: Math.round(clampNum(baseline.anxiety_decay * factor, 0, 0.15) * 1000) / 1000,
    // Max daily change cap — sqrt scaling to allow larger daily moves when
    // compressed, without letting tiny sim_days produce unrealistic swings.
    delta_cap_mult: Math.round(clampNum(baseline.delta_cap_mult * sqrtF, 0.5, 3.0) * 10) / 10,
    // Forget rate scales linearly: more real time per virtual day = forget more.
    forget_rate: Math.round(clampNum(baseline.forget_rate * factor, 0.01, 0.5) * 100) / 100,
    // Articles per agent: moderately scale (capped), since user-visible cost.
    articles_per_agent: clampNum(
      Math.round(baseline.articles_per_agent * Math.min(factor, 2)),
      1, 10,
    ),
    // NOT scaled (template-identity / political state / user choice):
    //   serendipity_rate, base_undecided, max_undecided, party_align_bonus,
    //   incumbency_bonus, individuality_multiplier, neutral_ratio, news_mix_*,
    //   enable_dynamic_leaning, shift_sat_threshold_low, shift_anx_threshold_high.
  };
}

/* ── component ── */

export default function EvolutionQuickStartPanel({ wsId }: { wsId: string }) {
  const router = useRouter();
  const en = useLocaleStore((s) => s.locale) === "en";
  const { template, loading: tplLoading } = useActiveTemplate(wsId);

  // Election data from template
  const election = (template as any)?.election;
  const candidates = election?.candidates ?? [];
  const cycle = election?.cycle;
  const isGeneric = election?.is_generic ?? !cycle;
  const searchKeywords = election?.default_search_keywords ?? {};
  const evolutionParams = election?.default_evolution_params ?? {};
  const evolutionWindow = election?.default_evolution_window ?? {};

  // Refs that always hold the latest election/candidates/advParams — so
  // runOneRound doesn't read a stale closure snapshot if the user clicks
  // Start before the template finishes loading.
  const electionRef = useRef<any>(election);
  const candidatesRef = useRef<any[]>(candidates);
  useEffect(() => { electionRef.current = election; }, [election]);

  // Custom candidates: null = use template. When set, each entry is a
  // {name, party} object. Legacy string[] format is upgraded on load.
  type CustomCand = { name: string; party: string };
  const [customCandidates, setCustomCandidates] = useState<CustomCand[] | null>(null);
  const [candidateInput, setCandidateInput] = useState("");
  const [candidateParty, setCandidateParty] = useState<string>("IND");
  const customCandidatesLoadedRef = useRef(false);

  // Taiwan parties — UI-level codes with their alignment bucket.
  // ``bucket`` is one of DPP/KMT/TPP/IND (the 4 the evolution engine
  // understands). Small parties map to their politically-aligned big
  // party so partisan bonuses still apply (e.g. 時代力量 and 台灣基進
  // both bucket into DPP; 親民黨 and 新黨 bucket into KMT).
  interface PartyDef {
    code: string;   // internal + UI display code
    label: string;  // 中文全名
    bucket: string; // backend alignment bucket (DPP/KMT/TPP/IND)
    color: string;
    group: string;  // UI grouping: "green" / "blue" / "white" / "other"
  }
  const TW_PARTIES: PartyDef[] = [
    // ── 綠營 ──
    { code: "DPP", label: "民進黨",   bucket: "DPP", color: "#1B9431", group: "green" },
    { code: "NPP", label: "時代力量", bucket: "DPP", color: "#FBBF24", group: "green" },
    { code: "TSP", label: "台灣基進", bucket: "DPP", color: "#7C3AED", group: "green" },
    // ── 藍營 ──
    { code: "KMT", label: "國民黨",   bucket: "KMT", color: "#000095", group: "blue" },
    { code: "PFP", label: "親民黨",   bucket: "KMT", color: "#F97316", group: "blue" },
    { code: "NP",  label: "新黨",     bucket: "KMT", color: "#EAB308", group: "blue" },
    // ── 白營 ──
    { code: "TPP", label: "民眾黨",   bucket: "TPP", color: "#28C8C8", group: "white" },
    // ── 其他／獨立 ──
    { code: "GPT", label: "綠黨",     bucket: "IND", color: "#10B981", group: "other" },
    { code: "IND", label: "無黨籍",   bucket: "IND", color: "#6B7280", group: "other" },
  ];
  const _partyByCode = (code: string): PartyDef | undefined =>
    TW_PARTIES.find((p) => p.code === code || p.bucket === code);

  // Alignment bucket inference when template/UI didn't supply an explicit party.
  const _inferParty = (name: string): string => {
    const n = (name || "").toLowerCase();
    if (n.includes("民進") || n.includes("dpp")) return "DPP";
    if (n.includes("時代力量") || n.includes("npp")) return "NPP";
    if (n.includes("台灣基進") || n.includes("tsp")) return "TSP";
    if (n.includes("國民") || n.includes("kmt")) return "KMT";
    if (n.includes("親民黨") || n.includes("pfp")) return "PFP";
    if (n.includes("新黨")) return "NP";
    if (n.includes("民眾黨") || n.includes("tpp")) return "TPP";
    if (n.includes("綠黨")) return "GPT";
    return "IND";
  };

  useEffect(() => {
    if (!wsId || customCandidatesLoadedRef.current) return;
    customCandidatesLoadedRef.current = true;
    getUiSettings(wsId, "custom-candidates").then((s: any) => {
      if (!Array.isArray(s?.candidates)) return;
      const upgraded: CustomCand[] = s.candidates.map((c: any) => {
        if (typeof c === "string") return { name: c, party: _inferParty(c) };
        return { name: String(c?.name || ""), party: c?.party || _inferParty(c?.name || "") };
      }).filter((c: CustomCand) => c.name);
      // Only restore custom candidates if they match the current template's
      // candidate list. When the user switches templates, stale custom
      // candidates from the previous template must NOT override the new one.
      const tplNameArr: string[] = (candidates || []).map((c: any) => c.name);
      const customNameArr: string[] = upgraded.map((c) => c.name);
      const customNameSet = new Set(customNameArr);
      const isMatch = tplNameArr.length === customNameArr.length && tplNameArr.every((n) => customNameSet.has(n));
      if (isMatch || tplNameArr.length === 0) {
        setCustomCandidates(upgraded);
      }
      // else: stale custom candidates discarded — template candidates will be used
    }).catch(() => {});
  }, [wsId, candidates]);

  // When the template changes (different candidate set), reset custom
  // candidates so the new template's candidates take effect immediately.
  const prevTplCandRef = useRef<string>("");
  useEffect(() => {
    const tplKey = (candidates || []).map((c: any) => c.name).sort().join("|");
    if (prevTplCandRef.current && prevTplCandRef.current !== tplKey && customCandidates !== null) {
      setCustomCandidates(null);  // clear stale custom → fall through to template
    }
    prevTplCandRef.current = tplKey;
  }, [candidates]);

  // Effective candidates: custom list overrides template candidates.
  // L/G get their own display code but are treated as "I" in scoring
  // logic downstream (see _alignmentClass in runOneRound).
  const effectiveCandidates: any[] = customCandidates !== null
    ? customCandidates.map((c) => ({ id: c.name, name: c.name, party: c.party, party_label: c.name }))
    : candidates;

  // Keep ref in sync with effective list
  useEffect(() => { candidatesRef.current = effectiveCandidates; }, [effectiveCandidates]);

  // Compute dates — dynamic "last 6 months → today" when election day is still future
  const elDate = cycle ? electionDate(cycle) : "";
  const _today = new Date().toISOString().slice(0, 10);
  const _elFuture = elDate && elDate > _today;
  const defaultStart = evolutionWindow.start_date || (_elFuture ? addDays(_today, -180) : (elDate ? addDays(elDate, -180) : addDays(_today, -180)));
  const defaultEnd = evolutionWindow.end_date || (_elFuture ? _today : (elDate ? addDays(elDate, -1) : addDays(_today, -1)));

  // Settings
  const [simDays, setSimDays] = useState(evolutionParams.sim_days ?? 30);
  const [crawlInterval, setCrawlInterval] = useState(evolutionParams.search_interval ?? 3);
  const [concurrency, setConcurrency] = useState(evolutionParams.concurrency ?? 5);
  const [startDate, setStartDate] = useState(defaultStart);
  const [endDate, setEndDate] = useState(defaultEnd);

  // Advanced parameters
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advParams, setAdvParams] = useState<AdvParams>({ ...DEFAULT_ADV_PARAMS });
  // Track the template-provided calibration defaults so we can show "modified" dot
  const [templateCalib, setTemplateCalib] = useState<AdvParams>({ ...DEFAULT_ADV_PARAMS });
  // Reference compression (template's default window ÷ default sim_days). Used
  // as the baseline for auto-scaling when the user changes days or date range.
  const [templateRefCompression, setTemplateRefCompression] = useState(1);

  // Merge template calibration_params into AdvParams shape
  const calibToAdv = useCallback((cp: Record<string, unknown>): AdvParams => {
    const merged = { ...DEFAULT_ADV_PARAMS };
    for (const k of Object.keys(DEFAULT_ADV_PARAMS) as (keyof AdvParams)[]) {
      if (cp[k] != null) (merged as any)[k] = cp[k];
    }
    return merged;
  }, []);

  // Update when template loads — sets evolution params, dates, calibration defaults,
  // then applies saved user overrides (simDays, crawlInterval, concurrency) on top.
  // advParams always come from template calibration to avoid stale overrides.
  useEffect(() => {
    if (!template) return;
    const ep = (template as any)?.election?.default_evolution_params;
    const ew = (template as any)?.election?.default_evolution_window;
    const tplSimDays = ep?.sim_days;
    const tplInterval = ep?.search_interval;
    const tplConcurrency = ep?.concurrency;
    if (tplSimDays) setSimDays(tplSimDays);
    if (tplInterval) setCrawlInterval(tplInterval);
    if (tplConcurrency) setConcurrency(tplConcurrency);
    const c = (template as any)?.election?.cycle;
    const ed = c ? electionDate(c) : "";
    // Today (dynamic, from local PC) as the latest news date — Serper can't
    // return future articles.
    const today = new Date().toISOString().slice(0, 10);
    const electionIsFuture = ed && ed > today;
    // Prefer explicit template window. If election day is still in the future
    // (e.g. 2028 cycle run in 2026), fall back to dynamic "last 6 months"
    // ending today, so Serper has real news to crawl.
    const defaultStart = electionIsFuture
      ? addDays(today, -180)
      : (ed ? addDays(ed, -180) : addDays(today, -180));
    const defaultEnd = electionIsFuture
      ? today
      : (ed ? addDays(ed, -1) : addDays(today, -1));
    const refStart = ew?.start_date || defaultStart;
    const refEnd = ew?.end_date || defaultEnd;
    setStartDate(refStart);
    setEndDate(refEnd);

    // Establish the template's reference compression so later simDays / date
    // changes can scale time-dependent params relative to this baseline.
    const refDays = tplSimDays || 30;
    setTemplateRefCompression(computeCompression(refStart, refEnd, refDays));

    // Load template calibration params as advanced parameter defaults
    const cp = (template as any)?.election?.default_calibration_params;
    if (cp) {
      const tplAdv = calibToAdv(cp);
      setTemplateCalib(tplAdv);
      setAdvParams(tplAdv);
    }

    // Apply saved user overrides AFTER template defaults (saved values take priority)
    getUiSettings(wsId, "evolution-quickstart").then((s: any) => {
      if (s?.simDays) setSimDays(s.simDays);
      if (s?.crawlInterval) setCrawlInterval(s.crawlInterval);
      if (s?.concurrency) setConcurrency(s.concurrency);
    }).catch(() => {}).finally(() => {
      settingsReadyRef.current = true; // allow persist effect to fire from now on
    });
  }, [template, calibToAdv, wsId]);

  // Gate: only persist AFTER template + saved settings have been fully loaded
  const settingsReadyRef = useRef(false);

  // ── Auto-scale time-dependent advanced params when user changes simDays or
  // the date range. Baseline is always templateCalib (NOT current advParams),
  // so repeated day-count changes don't compound. User edits to non-scaled
  // fields (news_mix / party bonuses / etc.) are preserved.
  // Skipped until templateCalib has loaded (templateRefCompression > 0).
  const autoScaleReadyRef = useRef(false);
  useEffect(() => {
    if (!templateRefCompression || templateRefCompression <= 0) return;
    // Skip the very first run (mount) so we don't immediately overwrite the
    // template-provided advParams. Only run when user actually changes days/dates.
    if (!autoScaleReadyRef.current) {
      autoScaleReadyRef.current = true;
      return;
    }
    const nowC = computeCompression(startDate, endDate, simDays);
    const factor = nowC / templateRefCompression;
    setAdvParams((prev) => {
      const scaled = scaleTimeDependentParams(templateCalib, factor);
      return {
        ...prev,            // keep user edits on non-scaled fields
        ...scaled,          // overwrite scaled fields with time-adjusted values
      };
    });
  }, [simDays, startDate, endDate, templateCalib, templateRefCompression]);

  // Compute current compression ratio for banner display (read-only).
  const currentCompression = computeCompression(startDate, endDate, simDays);
  const compressionFactor = templateRefCompression > 0
    ? currentCompression / templateRefCompression
    : 1;
  const compressionDiverges = Math.abs(compressionFactor - 1) > 0.05;

  // Persist settings when changed — but only after initial load completes
  useEffect(() => {
    if (!settingsReadyRef.current) return; // skip mount-time defaults
    saveUiSettings(wsId, "evolution-quickstart", { simDays, crawlInterval, concurrency, advParams }).catch(() => {});
  }, [wsId, simDays, crawlInterval, concurrency, advParams]);

  // Personas
  const [personaCount, setPersonaCount] = useState(0);
  const [personas, setPersonas] = useState<any[]>([]);
  useEffect(() => {
    if (!wsId) return;
    getWorkspacePersonas(wsId).then((r: any) => {
      const agents = r?.agents ?? (Array.isArray(r) ? r : []);
      setPersonas(agents);
      setPersonaCount(agents.length);
    }).catch(() => {});
  }, [wsId]);

  // Evolution state
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentRound, setCurrentRound] = useState(0);
  const [totalRounds, setTotalRounds] = useState(0);
  const [phase, setPhase] = useState<"idle" | "crawling" | "evolving" | "paused" | "done" | "error">("idle");
  const [phaseLabel, setPhaseLabel] = useState("");
  const [currentSimDate, setCurrentSimDate] = useState("");
  const [newsCount, setNewsCount] = useState(0);
  const [error, setError] = useState("");
  const abortRef = useRef(false);
  const pauseRef = useRef(false);
  const activeJobIdRef = useRef<string | null>(null);
  // Always-fresh ref to handleStart so the mount-rehydrate IIFE doesn't
  // invoke a stale closure (captured when tplLoading was still true).
  const handleStartRef = useRef<((resumeFromRound?: number, resumeNewsCount?: number) => Promise<void>) | null>(null);

  // Persist evolution progress so it survives page close
  const saveProgress = useCallback((state: Record<string, any>) => {
    saveUiSettings(wsId, "evolution-progress", state).catch(() => {});
  }, [wsId]);

  const clearProgress = useCallback(() => {
    saveUiSettings(wsId, "evolution-progress", { status: "idle" }).catch(() => {});
  }, [wsId]);

  const saveCandidates = useCallback((cands: CustomCand[]) => {
    setCustomCandidates(cands);
    saveUiSettings(wsId, "custom-candidates", { candidates: cands }).catch(() => {});
  }, [wsId]);

  // Restore evolution state on mount — detect if a job is still running
  useEffect(() => {
    (async () => {
      try {
        const saved = await getUiSettings(wsId, "evolution-progress");
        if (!saved || saved.status === "idle") return;
        // Completed run — restore the "done" completion panel so users who
        // reload the page after a full run don't see a blank Start screen
        // and think the evolution "stopped without a Resume button".
        if (saved.status === "done") {
          const { currentRound: cr, totalRounds: tr, newsCount: nc } = saved;
          if (tr) setTotalRounds(tr);
          if (cr) setCurrentRound(cr);
          if (nc) setNewsCount(nc);
          setPhase("done");
          setPhaseLabel(en ? "Evolution complete!" : "演化完成！");
          return;
        }

        // There was an active evolution plan
        const { status, currentRound: cr, totalRounds: tr, newsCount: nc, activeJobId, simDate } = saved;
        // Recover from "stuck paused at final round" — all rounds already
        // completed but the done-transition save never fired (e.g. page was
        // closed mid-completion, or user paused exactly as the last round
        // wrapped up). Promote to "done" so Prediction unlocks.
        if (status === "paused" && cr && tr && cr >= tr) {
          setCurrentRound(cr); setTotalRounds(tr); setNewsCount(nc || 0);
          setPhase("done");
          setPhaseLabel(en ? "Evolution complete!" : "演化完成！");
          saveUiSettings(wsId, "evolution-progress", { ...saved, status: "done", activeJobId: null }).catch(() => {});
          return;
        }
        if (status === "paused" || status === "error") {
          setCurrentRound(cr || 0);
          setTotalRounds(tr || 0);
          setNewsCount(nc || 0);
          setCurrentSimDate(simDate || "");
          setPaused(true);
          setPhase("paused");
          setPhaseLabel(
            status === "error"
              ? (en ? "Interrupted — click Resume to continue" : "演化中斷 — 點擊繼續")
              : (en ? "Paused — click Resume to continue" : "已暫停 — 點擊繼續")
          );
          // Normalize error → paused so next reload also shows Resume
          if (status === "error") {
            saveUiSettings(wsId, "evolution-progress", { ...saved, status: "paused" }).catch(() => {});
          }
          return;
        }

        if (status === "evolving" && activeJobId) {
          // Check if the backend job is still running
          try {
            const jobStatus = await getEvolutionStatus(activeJobId);
            if (jobStatus.status === "running" || jobStatus.status === "pending") {
              // Job still running — poll it until done, then resume from next round
              setRunning(true);
              setCurrentRound(cr || 0);
              setTotalRounds(tr || 0);
              setNewsCount(nc || 0);
              setCurrentSimDate(simDate || "");
              setPhase("evolving");
              setPhaseLabel(en ? `Evolving agents (round ${cr}/${tr})...` : `演化中（第 ${cr}/${tr} 輪）...`);
              activeJobIdRef.current = activeJobId;
              // Poll this job in background, then resume from next round
              (async () => {
                let jobDone = false;
                while (!jobDone && !abortRef.current) {
                  await new Promise((r) => setTimeout(r, 2000));
                  if (pauseRef.current) {
                    setPaused(true); setPhase("paused"); setRunning(false);
                    setPhaseLabel(en ? `Paused after round ${cr}/${tr}` : `第 ${cr}/${tr} 輪後暫停`);
                    return;
                  }
                  try {
                    const st = await getEvolutionStatus(activeJobId);
                    if (st.status === "done" || st.status === "completed") jobDone = true;
                    else if (st.status === "stopped" || st.status === "failed" || st.status === "error") { setPhase("error"); setError(st.error || "Job stopped unexpectedly"); setRunning(false); return; }
                  } catch { /* keep polling */ }
                }
                if (abortRef.current) { setRunning(false); return; }
                // Current round done — continue from next round, or mark done if final round
                setRunning(false);
                if ((cr || 0) >= (tr || 0)) {
                  // Final round just finished while we were polling — mark complete
                  setCurrentRound(tr || 0);
                  setTotalRounds(tr || 0);
                  setPhase("done");
                  setPhaseLabel(en ? "Evolution complete!" : "演化完成！");
                  saveProgress({ ...saved, status: "done", activeJobId: null });
                } else {
                  // Use the ref so we invoke the CURRENT handleStart (with
                  // fresh tplLoading/template values), not the one captured
                  // at mount when the template was still loading.
                  handleStartRef.current?.((cr || 0) + 1, nc || 0);
                }
              })();
              return;
            } else if (jobStatus.status === "done" || jobStatus.status === "completed") {
              // Job finished while page was closed. If this was the FINAL
              // round, mark the whole evolution done (unlocks Prediction)
              // rather than prompting the user to click Resume for nothing.
              if (cr && tr && cr >= tr) {
                setCurrentRound(cr); setTotalRounds(tr); setNewsCount(nc || 0);
                setPhase("done");
                setPhaseLabel(en ? "Evolution complete!" : "演化完成！");
                saveUiSettings(wsId, "evolution-progress", { ...saved, status: "done", activeJobId: null }).catch(() => {});
                return;
              }
              setCurrentRound(cr || 0);
              setTotalRounds(tr || 0);
              setNewsCount(nc || 0);
              setPaused(true);
              setPhase("paused");
              setPhaseLabel(en ? `Round ${cr}/${tr} completed while away — click Resume to continue` : `第 ${cr}/${tr} 輪已在背景完成 — 點擊繼續`);
              saveProgress({ ...saved, status: "paused", activeJobId: null });
            } else {
              // Job stopped / failed / error — clear stale progress
              clearProgress();
            }
          } catch {
            // Job not found — reset
            clearProgress();
          }
        }
      } catch { /* no saved progress */ }
    })();
  }, [wsId]);

  // Known source sites by leaning (for targeted search)
  const sourceBuckets: Record<string, { name: string; site: string }[]> = {
    "Solid Dem": [
      { name: "MSNBC", site: "msnbc.com" },
      { name: "HuffPost", site: "huffpost.com" },
    ],
    "Lean Dem": [
      { name: "CNN", site: "cnn.com" },
      { name: "The New York Times", site: "nytimes.com" },
      { name: "NPR", site: "npr.org" },
      { name: "The Washington Post", site: "washingtonpost.com" },
      { name: "NBC News", site: "nbcnews.com" },
      { name: "ABC News", site: "abcnews.go.com" },
      { name: "CBS News", site: "cbsnews.com" },
      { name: "PBS NewsHour", site: "pbs.org" },
    ],
    "Tossup": [
      { name: "Reuters", site: "reuters.com" },
      { name: "Associated Press", site: "apnews.com" },
      { name: "The Hill", site: "thehill.com" },
      { name: "USA Today", site: "usatoday.com" },
      { name: "Axios", site: "axios.com" },
    ],
    "Lean Rep": [
      { name: "Fox News", site: "foxnews.com" },
      { name: "The Wall Street Journal", site: "wsj.com" },
      { name: "New York Post", site: "nypost.com" },
      { name: "The Washington Times", site: "washingtontimes.com" },
    ],
    "Solid Rep": [
      { name: "Breitbart", site: "breitbart.com" },
      { name: "The Daily Wire", site: "dailywire.com" },
    ],
  };

  // Build search queries distributed by news category mix
  const buildQueries = useCallback(() => {
    const candidateNameList = candidates.map((c: any) => c.name as string).filter(Boolean);
    // Template stores default_search_keywords as either a list[str] (newer
    // Civatas-TW build_templates.py output) or a newline-delimited string
    // (legacy). Handle both robustly — previously calling .split on a list
    // threw TypeError and the outer try-catch silently swallowed the whole
    // crawl phase, leaving the news pool permanently empty.
    const toKwList = (val: any, fallback: string): string[] => {
      if (Array.isArray(val)) return val.filter((s: any) => !!s).map(String);
      if (typeof val === "string") return val.split("\n").filter(Boolean);
      return fallback.split("\n").filter(Boolean);
    };
    const nationalKws = toKwList(searchKeywords.national, "總統 行政院 立法院 兩岸 經濟 通膨 健保");
    const localKws = toKwList(searchKeywords.local, "縣市長 議會 捷運 治安 學校 健保 長照");
    const natPick = () => nationalKws[Math.floor(Math.random() * nationalKws.length)] || "";
    const locPick = () => localKws[Math.floor(Math.random() * localKws.length)] || "";
    // Round-robin index so each candidate gets searched in turn across queries
    let _candRRIdx = Math.floor(Math.random() * Math.max(candidateNameList.length, 1));
    const pickCandidateName = () => {
      if (!candidateNameList.length) return "";
      const name = candidateNameList[_candRRIdx % candidateNameList.length];
      _candRRIdx++;
      return name;
    };

    // Category-specific query templates (Taiwan context)
    const localStates = ["新北市", "桃園市", "臺中市", "彰化縣", "新竹縣", "宜蘭縣", "高雄市", "臺南市", "台北市", "基隆市"];
    const randomState = () => localStates[Math.floor(Math.random() * localStates.length)];
    const nationalTopics = [
      "通膨 物價 食品價格", "失業率 裁員 薪資",
      "健保 健保費 藥價", "兩岸關係 中國 軍演",
      "國防 軍購 兵役 漢光演習", "捷運 高鐵 基礎建設",
      "學貸 高教 大學學費", "勞退 勞保 退休金",
      "房價 房貸 囤房稅", "央行 升息 新台幣",
      "中央預算 超徵 補助", "社福 低收入戶 補助",
      "能源 核能 核四 綠電", "基本工資 勞動權益",
      "少子化 育兒津貼 托育", "長照 長照2.0 老人照護",
      "司改 大法官 憲法法庭", "詐騙 電信詐欺",
    ];
    const randomNatTopic = () => nationalTopics[Math.floor(Math.random() * nationalTopics.length)];
    const localTopics = [
      "縣市長簽署 條例", "縣市預算 教育經費",
      "警察 治安 犯罪報告", "市議會 都市計畫 房價",
      "學校 教師 霸凌", "縣道 高速公路 交通建設",
      "地方稅 房屋稅 地價稅", "社區 衛生所 社福",
      "鄉鎮市長 地方建設計畫", "司法 法院 判決",
    ];
    const randomLocTopic = () => localTopics[Math.floor(Math.random() * localTopics.length)];
    const intlTopics = [
      "美中貿易戰 關稅 制裁", "俄烏戰爭 歐盟 軍援",
      "中東 以巴 外交", "日本 美日安保",
      "G7 G20 峰會", "全球經濟 衰退 預測",
      "氣候 COP 減碳", "WHO WHA 台灣邦交",
      "南海 東海 航行自由", "東協 越南 菲律賓 印太戰略",
    ];
    const randomIntlTopic = () => intlTopics[Math.floor(Math.random() * intlTopics.length)];
    const categoryQueries = {
      candidate: () => {
        const n = pickCandidateName();
        if (!n) return `台灣總統大選 候選人 民調`;
        // Use quoted full name to prevent last-name collisions (e.g. "Shapiro"
        // matching Ben Shapiro instead of Josh Shapiro). Rotate suffix pools so
        // each query yields different coverage angles.
        const suffixes = [
          "新聞",
          "2028 總統",
          "政見 主張",
          "民調 支持度",
          "演講 專訪",
        ];
        const suffix = suffixes[_candRRIdx % suffixes.length];
        return `"${n}" ${suffix}`;
      },
      national: () => randomNatTopic(),
      local: () => `"${randomState()}" ${randomLocTopic()}`,
      international: () => randomIntlTopic(),
    };

    // Determine how many queries per category.
    // Candidate queries: at least 1 per candidate so every candidate gets searched
    // each round. Other categories fill the remainder up to totalQueries.
    const minCandidateQueries = Math.max(candidateNameList.length, 1);
    const total = advParams.news_mix_candidate + advParams.news_mix_national + advParams.news_mix_local + advParams.news_mix_international || 100;
    const nonCandidateQueries = 6; // fixed budget for national/local/intl
    const totalQueries = minCandidateQueries + nonCandidateQueries;
    const counts = {
      candidate: minCandidateQueries,
      national: Math.round((advParams.news_mix_national / (advParams.news_mix_national + advParams.news_mix_local + advParams.news_mix_international || 1)) * nonCandidateQueries) || 0,
      local: Math.round((advParams.news_mix_local / (advParams.news_mix_national + advParams.news_mix_local + advParams.news_mix_international || 1)) * nonCandidateQueries) || 0,
      international: Math.round((advParams.news_mix_international / (advParams.news_mix_national + advParams.news_mix_local + advParams.news_mix_international || 1)) * nonCandidateQueries) || 0,
    };
    // Ensure totals add up (rounding artifacts)
    while (counts.candidate + counts.national + counts.local + counts.international < totalQueries) {
      counts.national++;
    }

    // Source selection: ensure balanced political leaning coverage (TW 5-bucket)
    // "Must-have" sources — always searched every round for balanced coverage
    const mustHaveSources = [
      { name: "自由時報", site: "ltn.com.tw", leaning: "偏綠" },
      { name: "中時新聞網", site: "chinatimes.com", leaning: "偏藍" },
      { name: "中央通訊社", site: "cna.com.tw", leaning: "中間" },
    ];
    // Rotating pool — one from each remaining bucket per round
    const rotatingPools: { name: string; site: string; leaning: string }[][] = [
      // 偏綠 extras
      [
        { name: "三立新聞網", site: "setn.com", leaning: "偏綠" },
        { name: "民視新聞網", site: "ftvnews.com.tw", leaning: "偏綠" },
        { name: "Newtalk 新頭殼", site: "newtalk.tw", leaning: "偏綠" },
        { name: "上報", site: "upmedia.mg", leaning: "偏綠" },
      ],
      // 中間 extras
      [
        { name: "公視新聞", site: "news.pts.org.tw", leaning: "中間" },
        { name: "關鍵評論網", site: "thenewslens.com", leaning: "中間" },
        { name: "風傳媒", site: "storm.mg", leaning: "中間" },
        { name: "ETtoday 新聞雲", site: "ettoday.net", leaning: "中間" },
      ],
      // 偏藍 extras
      [
        { name: "聯合新聞網", site: "udn.com", leaning: "偏藍" },
        { name: "TVBS 新聞", site: "tvbs.com.tw", leaning: "偏藍" },
        { name: "NOWnews 今日新聞", site: "nownews.com", leaning: "偏藍" },
      ],
      // 深綠
      [
        { name: "民報", site: "peoplenews.tw", leaning: "深綠" },
        { name: "芋傳媒", site: "taronews.tw", leaning: "深綠" },
      ],
      // 深藍
      [
        { name: "中天新聞網", site: "ctinews.com", leaning: "深藍" },
        { name: "旺報", site: "want-daily.com", leaning: "深藍" },
      ],
      // 社群媒體 — 每輪抓 1 個，讓 media_habit='社群媒體'/'PTT/論壇' 的
      // agent 有 channel-matched 內容可讀。否則 feed_engine 只能 fallback
      // 用 leaning 相似度配傳統媒體，社群 agent 看起來會像讀報紙的。
      [
        { name: "PTT Gossiping",   site: "ptt.cc/bbs/Gossiping",   leaning: "中間" },
        { name: "PTT HatePolitics",site: "ptt.cc/bbs/HatePolitics",leaning: "中間" },
        { name: "Dcard 時事",       site: "dcard.tw",               leaning: "中間" },
        { name: "LINE Today",      site: "today.line.me",          leaning: "中間" },
      ],
    ];
    const pickRandom = <T,>(arr: T[]): T => arr[Math.floor(Math.random() * arr.length)];
    // Build rotating sources for this round (1 from each pool)
    const rotatingSources = rotatingPools.map((pool) => pickRandom(pool));

    // Combine: must-haves + rotating = ~8 sources per round, balanced
    const roundSources = [...mustHaveSources, ...rotatingSources];

    const queries: { query: string; sourceName: string; leaning: string }[] = [];
    // Distribute category queries across the balanced source list
    let srcIdx = 0;
    for (const [category, count] of Object.entries(counts)) {
      for (let i = 0; i < count; i++) {
        const src = roundSources[srcIdx % roundSources.length];
        srcIdx++;
        const q = categoryQueries[category as keyof typeof categoryQueries]();
        queries.push({ query: `site:${src.site} ${q}`, sourceName: src.name, leaning: src.leaning });
      }
    }
    return queries;
  }, [candidates, searchKeywords, advParams.news_mix_candidate, advParams.news_mix_national, advParams.news_mix_local, advParams.news_mix_international]);

  // Run a single round: crawl news + evolve
  const runOneRound = useCallback(async (roundNum: number, rounds: number, windowDays: number, daysPerRound: number, cumNewsCount: number): Promise<{ newsCount: number; jobId: string | null }> => {
    const roundStart = addDays(startDate, (roundNum - 1) * daysPerRound);
    const roundEnd = addDays(startDate, Math.min(roundNum * daysPerRound, windowDays));
    setCurrentSimDate(roundStart);

    // Phase 1: Crawl news
    setPhase("crawling");
    setPhaseLabel(en ? `Fetching news for ${fmtDate(roundStart, en)}...` : `抓取 ${fmtDate(roundStart, false)} 的新聞...`);
    let roundNewsCount = 0;
    try {
      const queries = buildQueries();
      for (const { query, sourceName } of queries) {
        if (abortRef.current || pauseRef.current) break;
        try {
          const searchRes = await apiFetch("/api/pipeline/serper-news-raw", {
            method: "POST",
            body: JSON.stringify({ query, start_date: roundStart, end_date: roundEnd, max_results: 3 }),
          });
          for (const art of (searchRes?.results ?? [])) {
            await injectNewsArticle(art.title || art.snippet || "", art.snippet || art.title || "", sourceName, wsId);
            roundNewsCount++;
          }
        } catch (e: any) { console.warn(`Crawl ${sourceName} failed:`, e); }
      }
    } catch (e: any) { console.warn("Crawl round failed:", e); }
    const newTotal = cumNewsCount + roundNewsCount;
    setNewsCount(newTotal);

    if (abortRef.current || pauseRef.current) {
      // Save paused state so page-reload recovery can show the Resume button
      if (pauseRef.current && !abortRef.current) {
        saveProgress({ status: "paused", currentRound: roundNum, totalRounds: rounds, newsCount: newTotal, activeJobId: null, simDate: roundStart, startDate, endDate, simDays, crawlInterval, concurrency });
      }
      return { newsCount: newTotal, jobId: null };
    }

    // Phase 2: Evolve
    setPhase("evolving");
    setPhaseLabel(en ? `Evolving agents (round ${roundNum}/${rounds})...` : `演化中（第 ${roundNum}/${rounds} 輪）...`);
    // Read latest template data via refs (avoids stale-closure when user
    // clicks Start before template finished loading).
    const _cands = candidatesRef.current || [];
    const _elec = electionRef.current || {};
    const candidateNames = _cands.map((c: any) => c.name).filter(Boolean);
    const candDescs: Record<string, string> = {};
    const candPartyMap: Record<string, string> = {};
    const candIncumbentMap: Record<string, boolean> = {};
    for (const c of _cands) {
      if (c.name && c.description) candDescs[c.name] = c.description;
      // Authoritative alignment bucket for the evolver (DPP/KMT/TPP/IND).
      // Small parties (NPP/TSP/PFP/NP/GPT) map to their aligned big bucket
      // so partisan bonuses still apply. Falls through to raw code if
      // not recognised.
      if (c.name && c.party) {
        const code = String(c.party).toUpperCase();
        const matched = _partyByCode(code);
        candPartyMap[c.name] = matched?.bucket || code;
      }
      // Authoritative incumbent flag from template (camelCase from frontend
      // hydration, snake_case from raw JSON). Evolver uses this to award the
      // incumbency bonus — without it, zh-TW descriptions ("時任總統尋求連任")
      // never matched the English-only keyword check, so 賴清德 lost his
      // incumbency advantage and bled support across every round.
      if (c.name) {
        candIncumbentMap[c.name] = Boolean((c as any).is_incumbent ?? (c as any).isIncumbent);
      }
    }
    const partyDetection = _elec?.party_detection ?? undefined;
    // Fetch all configured agent vendors (non-system) so newly-added vendors are included
    let enabledVendors: string[] | undefined;
    try {
      const settingsRes = await apiFetch("/api/settings");
      const allVendors: any[] = settingsRes?.llm_vendors || [];
      // The `system_vendor_id` slot is reserved for system-level tasks (AI
      // analysis, prompt repair). Using it for per-agent diary generation
      // was a mistake — it caused 50% of agents to be assigned to e.g.
      // `system-llm` (o4-mini), whose reasoning-token budget routinely
      // truncated before emitting JSON, triggering fallback to openai-1
      // with doubled latency and duplicate token spend. Exclude it here so
      // `enabled_vendors` mirrors the user's agent-vendor whitelist only.
      const systemVendorId: string | null = settingsRes?.system_vendor_id || null;
      const activeVendorIds: string[] = Array.isArray(settingsRes?.active_vendors)
        ? settingsRes.active_vendors
        : [];
      const agentVendorIds = allVendors
        .filter((v: any) => v.role !== "system" && v.id && v.id !== systemVendorId)
        .map((v: any) => v.id as string)
        // If the user has explicitly narrowed `active_vendors`, honour that;
        // otherwise fall through to the full agent-vendor list.
        .filter((id: string) => activeVendorIds.length === 0 || activeVendorIds.includes(id));
      if (agentVendorIds.length) enabledVendors = agentVendorIds;
    } catch { /* ignore — backend will auto-derive from agents */ }
    // Pass round's real-date range so the backend can fetch real TAIEX data
    // for that period. Agents who actually follow the stock market (decided
    // by income / age / occupation in tw_market_data._should_see_market) will
    // see the market summary in their macro_context.
    const res = await startEvolution(personas, crawlInterval, concurrency, candidateNames, advParams as Record<string, unknown>, candDescs, partyDetection, wsId, enabledVendors, candPartyMap, roundStart, roundEnd, candIncumbentMap);
    const jobId = res?.job_id || null;
    activeJobIdRef.current = jobId;

    // Save progress so it survives page close
    saveProgress({ status: "evolving", currentRound: roundNum, totalRounds: rounds, newsCount: newTotal, activeJobId: jobId, simDate: roundStart, startDate, endDate, simDays, crawlInterval, concurrency });

    if (jobId) {
      let done = false;
      while (!done && !abortRef.current) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        if (pauseRef.current) {
          saveProgress({ status: "paused", currentRound: roundNum, totalRounds: rounds, newsCount: newTotal, activeJobId: jobId, simDate: roundStart, startDate, endDate, simDays, crawlInterval, concurrency });
          return { newsCount: newTotal, jobId };
        }
        try {
          const st = await getEvolutionStatus(jobId);
          if (st.status === "done" || st.status === "completed") done = true;
          else if (st.status === "stopped") throw new Error("Evolution job was stopped unexpectedly");
          else if (st.status === "failed" || st.status === "error") throw new Error(st.error || "Evolution failed");
        } catch (e: any) { if (e.message?.includes("stopped") || e.message?.includes("failed")) throw e; }
      }
    }
    return { newsCount: newTotal, jobId };
  }, [personas, crawlInterval, concurrency, startDate, endDate, simDays, buildQueries, en, saveProgress]);

  // Main evolution loop
  const handleStart = useCallback(async (resumeFromRound = 0, resumeNewsCount = 0) => {
    if (running) return;
    // Skip persona check on resume — personas existed when the run started.
    // On fresh start (resumeFromRound === 0), enforce the check.
    if (resumeFromRound === 0 && !personas.length) {
      setError(en ? "No personas found. Generate personas first." : "找不到 Persona，請先生成。");
      return;
    }
    if (tplLoading) {
      setError(en ? "Template is still loading — please wait a moment." : "模板尚未載入完成，請稍候再試。");
      return;
    }
    if (!template) {
      setError(en ? "No active template. Go to Population Setup to select one." : "尚未選定模板，請至 Population Setup 挑選模板。");
      return;
    }
    setRunning(true);
    setPaused(false);
    setError("");
    abortRef.current = false;
    pauseRef.current = false;

    const rounds = Math.ceil(simDays / crawlInterval);  // effective simDays snap handled in derived section
    setTotalRounds(rounds);
    const windowDays = daysBetween(startDate, endDate);
    const daysPerRound = Math.max(1, Math.floor(windowDays / rounds));

    // Show "starting" state immediately so the UI is responsive before async ops
    setPhase("crawling");
    setPhaseLabel(en ? "Preparing..." : "準備中...");

    // Fresh start: stop ALL running backend jobs, then reset all state
    // Resume: skip reset — continue from where we left off
    if (resumeFromRound === 0) {
      // Stop all running/pending jobs to avoid race conditions
      try {
        const jobsRes = await apiFetch("/api/pipeline/evolution/evolve/jobs");
        const runningJobs = (jobsRes?.jobs || []).filter((j: any) => j.status === "running" || j.status === "pending");
        for (const rj of runningJobs) {
          try { await apiFetch(`/api/pipeline/evolution/evolve/stop/${rj.job_id}`, { method: "POST" }); } catch {}
        }
        if (runningJobs.length > 0) {
          // Wait for jobs to fully stop and flush any pending state writes
          await new Promise((r) => setTimeout(r, 2000));
        }
      } catch {}
      activeJobIdRef.current = null;
      // Now reset — all jobs stopped, safe to clear states
      try { await apiFetch(`/api/pipeline/evolution/evolve/reset?workspace_id=${encodeURIComponent(wsId)}`, { method: "POST" }); } catch {}
      try { await apiFetch(`/api/pipeline/evolution/news-pool/clear?workspace_id=${encodeURIComponent(wsId)}`, { method: "POST" }); } catch {}
      // Write reset timestamp so Dashboard discards stale AI analysis cache on next mount
      try {
        sessionStorage.setItem(`evo_reset_${wsId}`, String(Date.now()));
        sessionStorage.removeItem(`evo_analysis_${wsId}`);
      } catch {}
    }

    let nc = resumeNewsCount;
    const startRound = resumeFromRound > 0 ? resumeFromRound : 1;

    for (let r = startRound; r <= rounds; r++) {
      if (abortRef.current) break;
      setCurrentRound(r);
      try {
        const result = await runOneRound(r, rounds, windowDays, daysPerRound, nc);
        nc = result.newsCount;
        if (pauseRef.current) {
          setPhase("paused");
          setPhaseLabel(en ? `Paused after round ${r}/${rounds}` : `第 ${r}/${rounds} 輪後暫停`);
          setRunning(false);
          return;
        }
      } catch (e: any) {
        setError(e.message || "Evolution failed");
        setPhase("error");
        setRunning(false);
        saveProgress({ status: "error", currentRound: r, totalRounds: rounds, newsCount: nc });
        return;
      }
    }

    if (!abortRef.current) {
      setPhase("done");
      setPhaseLabel(en ? "Evolution complete!" : "演化完成！");
      // Mark evolution as fully done (not idle) so sidebar shows ✓.
      // Persist the round + news counts too so a page reload can show the
      // completion summary (rounds / news crawled / agents) instead of a
      // blank Start screen that looks like "evolution stopped".
      saveUiSettings(wsId, "evolution-progress", {
        status: "done",
        currentRound: rounds,
        totalRounds: rounds,
        newsCount: nc,
      }).catch(() => {});
      // Auto-create a snapshot so Prediction can run without an extra click.
      // Only on a clean full-completion path (no abort / no error earlier in loop).
      try {
        const tplName = (template as any)?.name || (en ? "Evolution" : "演化結果");
        const snapName = `${tplName} — ${en ? "auto" : "自動"} ${new Date().toLocaleString(undefined, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}`;
        const _effDays = Math.ceil(simDays / crawlInterval) * crawlInterval;
        const snapDesc = en
          ? `Auto-created on evolution completion. ${_effDays} simulated days, ${personas.length} agents.`
          : `演化完成時自動建立。模擬 ${_effDays} 天、${personas.length} 位 agents。`;
        // Embed template's election ground truth so predictor can redistribute
        // leanings without requiring a separate calibration pack.
        const baseAlign = (template as any)?.election?.default_alignment || null;
        const partyDet = (template as any)?.election?.party_detection || null;
        const alignTarget = baseAlign
          ? { ...baseAlign, ...(partyDet ? { party_detection: partyDet } : {}) }
          : (partyDet ? { party_detection: partyDet } : null);
        await saveSnapshot(snapName, snapDesc, undefined, wsId, alignTarget);
      } catch (e) {
        console.warn("auto-snapshot failed:", e);
      }
    }
    setRunning(false);
  }, [running, personas, simDays, crawlInterval, concurrency, startDate, endDate, runOneRound, en, clearProgress, tplLoading, template, isGeneric, wsId]);

  useEffect(() => {
    handleStartRef.current = handleStart;
  }, [handleStart]);

  // Pause — finish current evolve job, then stop
  const handlePause = () => {
    pauseRef.current = true;
    setPaused(true);
    setPhaseLabel(en ? "Pausing after current round..." : "當前輪次完成後暫停...");
  };

  // Resume from paused state
  const handleResume = () => {
    setPaused(false);
    pauseRef.current = false;
    handleStart(currentRound + 1, newsCount);
  };

  // Stop — abort immediately and reset UI state
  const handleStop = async () => {
    abortRef.current = true;
    pauseRef.current = false;
    setPaused(false);
    setRunning(false);
    setPhase("idle");
    setCurrentRound(0);
    setTotalRounds(0);
    setNewsCount(0);
    setCurrentSimDate("");
    setPhaseLabel("");
    clearProgress();
    // Stop the backend job if one is active
    if (activeJobIdRef.current) {
      try { await apiFetch(`/api/pipeline/evolution/evolve/stop/${activeJobIdRef.current}`, { method: "POST" }); } catch {}
      activeJobIdRef.current = null;
    }
  };

  // Derived
  // simDays must be a multiple of crawlInterval — each round covers exactly
  // crawlInterval days, so a non-multiple would silently round up at the
  // `Math.ceil(simDays / crawlInterval)` step and give the user more days
  // than they typed. We snap here and surface the adjustment in the UI.
  const effectiveSimDays = Math.ceil(simDays / crawlInterval) * crawlInterval;
  const simDaysAdjusted = effectiveSimDays !== simDays;
  const rounds = effectiveSimDays / crawlInterval;
  const windowSpan = daysBetween(startDate, endDate);
  const progressPct = totalRounds > 0 ? Math.round((currentRound / totalRounds) * 100) : 0;

  // Taiwan party color palette, derived from TW_PARTIES at the top of
  // this component. Matches build_templates.py PARTY_PALETTE for the big
  // 4 buckets; small parties get their own distinctive colours.
  const candidateColors: Record<string, string> = (() => {
    const m: Record<string, string> = {};
    for (const p of TW_PARTIES) m[p.code] = p.color;
    // Legacy US codes (older persisted state may still have these)
    m.D = "#1B9431"; m.R = "#000095"; m.I = "#6B7280";
    m.L = "#F59E0B"; m.G = "#22C55E";
    return m;
  })();
  const candidatePartyLabels: Record<string, string> = (() => {
    const m: Record<string, string> = {};
    for (const p of TW_PARTIES) m[p.code] = p.label;
    return m;
  })();

  if (tplLoading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ width: 32, height: 32, border: "3px solid rgba(233,69,96,0.3)", borderTopColor: "#e94560", borderRadius: "50%", animation: "spin 1s linear infinite" }} />
        <style jsx>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "auto" }}>
      <div style={{ padding: "24px clamp(16px, 3vw, 40px)", maxWidth: Math.max(800, 200 + (effectiveCandidates.length || 2) * 160), width: "100%" }}>

        {/* Header */}
        <h2 style={{ color: "var(--text-primary)", fontSize: 22, fontWeight: 700, margin: "0 0 4px" }}>
          {en ? "⚡ Evolution Quick Start" : "⚡ 快速演化"}
        </h2>
        <p style={{ color: "var(--text-tertiary)", fontSize: 13, margin: "0 0 24px" }}>
          {en
            ? "Run the full evolution pipeline with one click — news crawling and agent opinion evolution are automated."
            : "一鍵啟動完整演化流程 — 新聞抓取和 Agent 觀點演化全自動執行。"}
        </p>

        {/* ── Election Info Card ── */}
        <div style={{
          background: "var(--bg-card)", border: "1px solid var(--border-subtle)",
          borderRadius: 12, padding: 20, marginBottom: 20,
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 1 }}>
              {en ? "Election" : "選舉"}
            </div>
            {template && (
              <span style={{ fontSize: 11, color: "var(--text-muted)", padding: "2px 8px", borderRadius: 4, background: "var(--bg-card)" }}>
                {(template as any)?.name || ""}
              </span>
            )}
          </div>

          {/* Candidates — editable */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 1 }}>
                {en ? "Candidates" : "候選人"}
              </span>
              {customCandidates !== null && candidates.length > 0 && (
                <button
                  onClick={() => { setCustomCandidates(null); saveUiSettings(wsId, "custom-candidates", { candidates: null }).catch(() => {}); }}
                  style={{ fontSize: 11, color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", textDecoration: "underline", padding: 0 }}
                >
                  {en ? "Reset to template" : "還原為模板預設"}
                </button>
              )}
            </div>

            {/* Tag list */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10, minHeight: 34 }}>
              {effectiveCandidates.map((c: any) => (
                <div key={c.name} style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "5px 10px", borderRadius: 20,
                  background: `${candidateColors[c.party] || "#6b7280"}15`,
                  border: `1px solid ${candidateColors[c.party] || "#6b7280"}40`,
                }}>
                  <span style={{ color: candidateColors[c.party] || "#6b7280", fontSize: 10, fontWeight: 700 }}>{c.party}</span>
                  <span style={{ color: "var(--text-primary)", fontSize: 13 }}>{c.name}</span>
                  {!running && (
                    <button
                      onClick={() => {
                        const base: CustomCand[] = customCandidates !== null
                          ? customCandidates
                          : candidates.map((x: any) => ({ name: x.name, party: x.party || "I" }));
                        saveCandidates(base.filter((cc) => cc.name !== c.name));
                      }}
                      style={{ color: "var(--text-muted)", background: "none", border: "none", cursor: "pointer", fontSize: 16, lineHeight: 1, padding: 0, marginLeft: 2 }}
                    >×</button>
                  )}
                </div>
              ))}
              {effectiveCandidates.length === 0 && (
                <span style={{ color: "var(--text-muted)", fontSize: 12, fontStyle: "italic", alignSelf: "center" }}>
                  {en ? "No candidates — awareness tracking disabled" : "無候選人 — 不追蹤知名度"}
                </span>
              )}
            </div>

            {/* Add input */}
            {!running && (() => {
              const addCandidate = () => {
                const name = candidateInput.trim();
                if (!name) return;
                const base: CustomCand[] = customCandidates !== null
                  ? customCandidates
                  : candidates.map((x: any) => ({ name: x.name, party: x.party || "I" }));
                if (base.some((cc) => cc.name === name)) return;
                saveCandidates([...base, { name, party: candidateParty }]);
                setCandidateInput("");
                setCandidateParty("IND");
              };
              return (
              <div style={{ display: "flex", gap: 8 }}>
                <select
                  value={candidateParty}
                  onChange={(e) => setCandidateParty(e.target.value)}
                  title={en
                    ? "Party — small parties inherit their aligned bucket (NPP/TSP→DPP, PFP/NP→KMT, GPT→IND)"
                    : "政黨 — 小黨會歸屬到對應陣營：時代力量/台灣基進 → 綠營；親民黨/新黨 → 藍營；綠黨 → 獨立"}
                  style={{
                    padding: "6px 10px", borderRadius: 6,
                    border: `1px solid ${candidateColors[candidateParty] || "#6b7280"}60`,
                    background: "var(--bg-input)",
                    color: candidateColors[candidateParty] || "var(--text-primary)",
                    fontWeight: 700, fontSize: 13, outline: "none", cursor: "pointer",
                  }}
                >
                  <optgroup label="🟢 綠營">
                    {TW_PARTIES.filter(p => p.group === "green").map(p => (
                      <option key={p.code} value={p.code}>{p.code} · {p.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="🔵 藍營">
                    {TW_PARTIES.filter(p => p.group === "blue").map(p => (
                      <option key={p.code} value={p.code}>{p.code} · {p.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="⚪ 白營">
                    {TW_PARTIES.filter(p => p.group === "white").map(p => (
                      <option key={p.code} value={p.code}>{p.code} · {p.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="其他／獨立">
                    {TW_PARTIES.filter(p => p.group === "other").map(p => (
                      <option key={p.code} value={p.code}>{p.code} · {p.label}</option>
                    ))}
                  </optgroup>
                </select>
                <input
                  value={candidateInput}
                  onChange={(e) => setCandidateInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") { e.preventDefault(); addCandidate(); }
                  }}
                  placeholder={en ? "Add candidate…" : "新增候選人…"}
                  style={{
                    flex: 1, padding: "6px 10px", borderRadius: 6,
                    border: "1px solid var(--border-input)", background: "var(--bg-input)",
                    color: "var(--text-primary)", fontSize: 13, outline: "none",
                  }}
                />
                <button
                  onClick={addCandidate}
                  style={{
                    padding: "6px 14px", borderRadius: 6,
                    border: "1px solid var(--border-subtle)", background: "var(--bg-card)",
                    color: "var(--text-secondary)", cursor: "pointer", fontSize: 13,
                  }}
                >
                  {en ? "+ Add" : "+ 新增"}
                </button>
              </div>
              );
            })()}
          </div>

          {/* Date range */}
          <div style={{ display: "flex", gap: 24, fontSize: 13 }}>
            <div>
              <span style={{ color: "var(--text-muted)" }}>{en ? "Window: " : "期間："}</span>
              <span style={{ color: "var(--text-primary)" }}>{fmtDate(startDate, en)} → {fmtDate(endDate, en)}</span>
            </div>
            {elDate && (
              <div>
                <span style={{ color: "var(--text-muted)" }}>{en ? "Election Day: " : "選舉日："}</span>
                <span style={{ color: "#e94560" }}>{fmtDate(elDate, en)}</span>
              </div>
            )}
            <div>
              <span style={{ color: "var(--text-muted)" }}>Personas: </span>
              <span style={{ color: "#86efac" }}>{personaCount}</span>
            </div>
          </div>
        </div>

        {/* ── Settings Card ── */}
        <div style={{
          background: "var(--bg-card)", border: "1px solid var(--border-subtle)",
          borderRadius: 12, padding: 20, marginBottom: 20,
        }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>
            {en ? "Settings" : "設定"}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
            <label style={{ color: "var(--text-secondary)", fontSize: 12 }}>
              {en ? "Simulation days" : "模擬天數"}
              <input type="number" min={1} max={365} value={simDays}
                onChange={(e) => setSimDays(Number(e.target.value) || 30)}
                disabled={running}
                style={{ display: "block", width: "100%", marginTop: 4, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border-input)", background: "var(--bg-input)", color: "var(--text-primary)", fontSize: 14 }}
              />
              {simDaysAdjusted && (
                <div style={{ marginTop: 6, fontSize: 10, color: "#f59e0b", lineHeight: 1.5 }}>
                  {en
                    ? `Adjusted: ${simDays} → ${effectiveSimDays} days (must be a multiple of the ${crawlInterval}-day crawl interval; ${rounds} rounds × ${crawlInterval} days).`
                    : `已自動調整：${simDays} → ${effectiveSimDays} 天（需為抓取間隔 ${crawlInterval} 天的倍數；${rounds} 輪 × ${crawlInterval} 天）。`}
                </div>
              )}
            </label>
            <label style={{ color: "var(--text-secondary)", fontSize: 12 }}>
              {en ? "News crawl interval" : "新聞抓取間隔"}
              <select value={crawlInterval}
                onChange={(e) => setCrawlInterval(Number(e.target.value))}
                disabled={running}
                style={{ display: "block", width: "100%", marginTop: 4, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border-input)", background: "var(--bg-input)", color: "var(--text-primary)", fontSize: 14 }}
              >
                {[1, 2, 3, 5, 7, 10].map((d) => (
                  <option key={d} value={d}>{d} {en ? "days" : "天"}</option>
                ))}
              </select>
            </label>
            <label style={{ color: "var(--text-secondary)", fontSize: 12 }}>
              {en ? "Concurrency" : "並行數"}
              <select value={concurrency}
                onChange={(e) => setConcurrency(Number(e.target.value))}
                disabled={running}
                style={{ display: "block", width: "100%", marginTop: 4, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--border-input)", background: "var(--bg-input)", color: "var(--text-primary)", fontSize: 14 }}
              >
                {[1, 3, 5, 8, 10].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
          </div>
          <div style={{ marginTop: 12, fontSize: 11, color: "var(--text-muted)" }}>
            {en
              ? `${rounds} rounds × ${crawlInterval} days = ${effectiveSimDays} simulated days, covering ${windowSpan} days of real time`
              : `${rounds} 輪 × ${crawlInterval} 天 = ${effectiveSimDays} 模擬天數，涵蓋 ${windowSpan} 天的真實時間`}
          </div>
        </div>

        {/* ── Start / Progress ── */}
        {/* ── Start button (idle) ── */}
        {phase === "idle" && (
          <button
            onClick={() => handleStart()}
            disabled={running || !personaCount || tplLoading}
            style={{
              width: "100%", padding: "14px 24px", borderRadius: 12, border: "none",
              background: (personaCount && !tplLoading) ? "linear-gradient(135deg, #e94560, #c62368)" : "rgba(100,100,100,0.3)",
              color: "var(--text-primary)", fontSize: 16, fontWeight: 700, cursor: (personaCount && !tplLoading) ? "pointer" : "not-allowed",
              transition: "opacity 0.2s",
            }}
          >
            {tplLoading
              ? (en ? "⏳ Loading template..." : "⏳ 載入模板中...")
              : (en ? "🚀 Start Evolution" : "🚀 開始演化")}
          </button>
        )}

        {/* ── Paused state ── */}
        {phase === "paused" && (
          <div style={{
            background: "rgba(251,191,36,0.06)", border: "1px solid rgba(251,191,36,0.2)",
            borderRadius: 12, padding: 20,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#fbbf24", marginBottom: 12 }}>
              ⏸ {phaseLabel}
            </div>
            <div style={{ display: "flex", gap: 24, fontSize: 12, color: "var(--text-tertiary)", marginBottom: 16 }}>
              <span>{en ? "Round" : "輪次"}: <strong style={{ color: "var(--text-primary)" }}>{currentRound}/{totalRounds}</strong></span>
              <span>{en ? "News crawled" : "已抓新聞"}: <strong style={{ color: "var(--text-primary)" }}>{newsCount}</strong></span>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <button
                onClick={handleResume}
                disabled={tplLoading}
                style={{
                  flex: 1, padding: "10px 20px", borderRadius: 8, border: "none",
                  background: tplLoading ? "rgba(100,100,100,0.3)" : "linear-gradient(135deg, #e94560, #c62368)",
                  color: "var(--text-primary)",
                  fontSize: 14, fontWeight: 700, cursor: tplLoading ? "not-allowed" : "pointer",
                }}
              >
                {tplLoading
                  ? (en ? "⏳ Loading template..." : "⏳ 載入模板中...")
                  : (en ? "▶ Resume" : "▶ 繼續")}
              </button>
              <button onClick={async () => { await handleStop(); handleStart(); }} style={{
                padding: "10px 20px", borderRadius: 8, fontSize: 14,
                background: "rgba(59,130,246,0.1)", color: "#60a5fa",
                border: "1px solid rgba(59,130,246,0.2)", cursor: "pointer",
              }}>
                {en ? "🔄 Restart" : "🔄 重新開始"}
              </button>
              <button onClick={handleStop} style={{
                padding: "10px 20px", borderRadius: 8, fontSize: 14,
                background: "rgba(255,107,107,0.1)", color: "#ff6b6b",
                border: "1px solid rgba(255,107,107,0.2)", cursor: "pointer",
              }}>
                {en ? "⏹ Stop" : "⏹ 停止"}
              </button>
            </div>
          </div>
        )}

        {/* ── Running state (crawling / evolving) ── */}
        {(phase === "crawling" || phase === "evolving") && (
          <div style={{
            background: "var(--bg-card)", border: "1px solid var(--border-subtle)",
            borderRadius: 12, padding: 20,
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: 6 }}>
                {paused && phase === "evolving" && (
                  <span style={{ display: "inline-block", width: 12, height: 12, border: "2px solid #60a5fa", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                )}
                {phaseLabel}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  onClick={handlePause}
                  disabled={paused}
                  style={{
                    padding: "6px 16px", borderRadius: 8, fontSize: 12,
                    background: "rgba(59,130,246,0.15)", color: "#60a5fa",
                    border: "1px solid rgba(59,130,246,0.3)", cursor: paused ? "not-allowed" : "pointer",
                    opacity: paused ? 0.6 : 1,
                    display: "flex", alignItems: "center", gap: 4,
                  }}
                >
                  {paused && phase === "evolving" && (
                    <span style={{ display: "inline-block", width: 10, height: 10, border: "2px solid #60a5fa", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                  )}
                  {paused ? (en ? "Pausing..." : "暫停中...") : (en ? "⏸ Pause" : "⏸ 暫停")}
                </button>
                <button
                  onClick={handleStop}
                  style={{
                    padding: "6px 16px", borderRadius: 8, fontSize: 12,
                    background: "rgba(255,107,107,0.1)", color: "#ff6b6b",
                    border: "1px solid rgba(255,107,107,0.2)", cursor: "pointer",
                  }}
                >
                  {en ? "⏹ Stop" : "⏹ 停止"}
                </button>
              </div>
            </div>

            {paused && phase === "evolving" && (
              <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(59,130,246,0.08)", border: "1px solid rgba(59,130,246,0.25)", color: "#93c5fd", fontSize: 12, marginBottom: 12, display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-cjk)" }}>
                <span style={{ fontSize: 16 }}>⏳</span>
                <span>
                  {en
                    ? `Pause requested. Evolution will complete the current round (${currentRound}/${totalRounds}) first, then save state. Safe to close the tab after "Paused after round ${currentRound}" appears.`
                    : `已請求暫停。演化會先完成當前第 ${currentRound}/${totalRounds} 輪，儲存狀態後才真正停下。看到「第 ${currentRound} 輪後暫停」後即可關閉分頁。`}
                </span>
              </div>
            )}

            {/* Progress bar */}
            <div style={{ background: "var(--bg-input)", borderRadius: 6, height: 8, marginBottom: 12, overflow: "hidden" }}>
              <div style={{
                height: "100%", borderRadius: 6,
                background: phase === "crawling" ? "#60a5fa" : "#e94560",
                width: `${progressPct}%`,
                transition: "width 0.5s ease",
              }} />
            </div>

            {/* Stats row */}
            <div style={{ display: "flex", gap: 24, fontSize: 12, color: "var(--text-tertiary)" }}>
              <span>{en ? "Round" : "輪次"}: <strong style={{ color: "var(--text-primary)" }}>{currentRound}/{totalRounds}</strong></span>
              <span>{en ? "Sim date" : "模擬日期"}: <strong style={{ color: "var(--text-primary)" }}>{currentSimDate}</strong></span>
              <span>{en ? "News crawled" : "已抓新聞"}: <strong style={{ color: "var(--text-primary)" }}>{newsCount}</strong></span>
              <span>
                {phase === "crawling" && <span style={{ display: "inline-block", width: 10, height: 10, border: "2px solid #60a5fa", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite", verticalAlign: "middle", marginRight: 4 }} />}
                {phase === "evolving" && <span style={{ display: "inline-block", width: 10, height: 10, border: "2px solid #e94560", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 1s linear infinite", verticalAlign: "middle", marginRight: 4 }} />}
                {phase === "crawling" ? (en ? "Fetching" : "抓取中") : (en ? "Evolving" : "演化中")}
              </span>
            </div>
          </div>
        )}

        {phase === "done" && (
          <div style={{
            background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)",
            borderRadius: 12, padding: 20, textAlign: "center",
          }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>🎉</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#86efac", marginBottom: 4 }}>
              {en ? "Evolution Complete!" : "演化完成！"}
            </div>
            <div style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 16 }}>
              {en
                ? `${rounds} rounds completed · ${newsCount} articles crawled · ${personaCount} agents evolved`
                : `${rounds} 輪完成 · ${newsCount} 篇新聞 · ${personaCount} 位 Agent 已演化`}
            </div>
            <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
              <button
                onClick={() => router.push(`/workspaces/${wsId}/evolution-dashboard`)}
                style={{
                  padding: "10px 24px", borderRadius: 8, border: "none",
                  background: "#3b82f6", color: "var(--text-primary)", fontSize: 14, fontWeight: 600, cursor: "pointer",
                }}
              >
                {en ? "📊 View Dashboard" : "📊 查看儀表板"}
              </button>
              <button
                onClick={async () => {
                  try {
                    const exportData = await apiFetch("/api/pipeline/evolution/export-playback");
                    const { generatePlaybackHTML } = await import("@/lib/export-playback");
                    const html = generatePlaybackHTML({
                      ...exportData,
                      templateName: (template as any)?.name || "",
                      locale: en ? "en" : "zh-TW",
                    });
                    const blob = new Blob([html], { type: "text/html" });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `civatas-evolution-playback-${new Date().toISOString().slice(0, 10)}.html`;
                    a.click();
                    URL.revokeObjectURL(url);
                  } catch (e: any) {
                    console.error("Export failed:", e);
                  }
                }}
                style={{
                  padding: "10px 24px", borderRadius: 8,
                  background: "rgba(168,85,247,0.15)", color: "#a855f7",
                  fontSize: 14, fontWeight: 600, cursor: "pointer",
                  border: "1px solid rgba(168,85,247,0.3)",
                }}
              >
                {en ? "📥 Download Playback" : "📥 下載回放頁面"}
              </button>
              <button
                onClick={() => { setPhase("idle"); setCurrentRound(0); setNewsCount(0); }}
                style={{
                  padding: "10px 24px", borderRadius: 8,
                  background: "var(--bg-input)", color: "var(--text-secondary)",
                  border: "1px solid var(--border-input)", fontSize: 14, cursor: "pointer",
                }}
              >
                {en ? "🔄 Run Again" : "🔄 再次執行"}
              </button>
            </div>
          </div>
        )}

        {error && (
          <div style={{
            background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.2)",
            borderRadius: 12, padding: 16, color: "#fca5a5", fontSize: 13,
          }}>
            ⚠ {error}
            <button
              onClick={() => { setPhase("idle"); setError(""); }}
              style={{
                marginLeft: 12, padding: "4px 12px", borderRadius: 6,
                background: "var(--bg-input)", color: "var(--text-tertiary)",
                border: "1px solid var(--border-input)", fontSize: 12, cursor: "pointer",
              }}
            >
              {en ? "Dismiss" : "關閉"}
            </button>
          </div>
        )}

        {/* ── Advanced Parameters ── */}
        <div style={{ marginTop: 20 }}>
          <button
            onClick={() => setShowAdvanced(!showAdvanced)}
            style={{
              width: "100%", background: "none", border: "none", color: "var(--text-muted)",
              fontSize: 12, cursor: "pointer", display: "flex", alignItems: "center",
              justifyContent: "center", gap: 6, padding: "8px 0",
            }}
          >
            <span style={{ transform: showAdvanced ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 0.2s", display: "inline-block" }}>▶</span>
            {en ? "Advanced Parameters" : "進階參數"}
          </button>

          {showAdvanced && (
            <div style={{
              background: "var(--bg-card)", border: "1px solid var(--border-subtle)",
              borderRadius: 12, padding: 20, marginTop: 8,
            }}>
              {/* ── Time-compression banner ── */}
              {compressionDiverges && (
                <div style={{
                  marginBottom: 18, padding: "10px 14px", borderRadius: 8,
                  background: "rgba(59,130,246,0.08)",
                  border: "1px solid rgba(59,130,246,0.25)",
                  fontSize: 11, color: "rgba(255,255,255,0.75)", lineHeight: 1.55,
                }}>
                  <div style={{ fontWeight: 600, marginBottom: 4, color: "#93c5fd" }}>
                    {en ? "⏱ Time-compression auto-scaled" : "⏱ 時間壓縮自動調整"}
                  </div>
                  {en ? (
                    <>
                      Each virtual day ≈ <strong>{currentCompression.toFixed(1)}</strong> real days
                      {" "}(template baseline: {(templateRefCompression).toFixed(1)} real days/day,
                      {" "}scale ×{compressionFactor.toFixed(2)}).
                      {" "}News impact, decay, shift-day threshold, forget rate, and articles/day
                      have been adjusted. You can still fine-tune any value below.
                    </>
                  ) : (
                    <>
                      每虛擬日 ≈ <strong>{currentCompression.toFixed(1)}</strong> 個真實日
                      （模板基準：{(templateRefCompression).toFixed(1)} 真實日/虛擬日、
                      係數 ×{compressionFactor.toFixed(2)}）。
                      已自動調整：新聞影響倍率、滿意度/焦慮度衰減、連續天數閾值、
                      記憶遺忘率、每日文章數。下列任何值仍可再微調。
                    </>
                  )}
                </div>
              )}

              {/* ── Section 1: Political Leaning Shifts ── */}
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ fontSize: 14 }}>🔄</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    {en ? "Political Leaning Shifts" : "政治傾向轉變"}
                  </span>
                </div>
                <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "0 0 12px", lineHeight: 1.5 }}>
                  {en
                    ? "Control when agents shift their political leaning based on satisfaction and anxiety thresholds."
                    : "控制 Agent 在滿意度和焦慮度達到閾值時如何改變政治傾向。"}
                </p>

                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                    <input type="checkbox" checked={advParams.enable_dynamic_leaning}
                      onChange={(e) => setAdvParams({ ...advParams, enable_dynamic_leaning: e.target.checked })}
                      disabled={running}
                    />
                    <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                      {en ? "Enable dynamic leaning shifts" : "啟用動態傾向轉變"}
                    </span>
                  </label>
                </div>

                {advParams.enable_dynamic_leaning && (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                    <AdvSlider label={en ? "Low satisfaction threshold" : "低滿意度閾值"}
                      hint={en ? "Below this → partisan shifts to neutral" : "低於此值 → 偏向轉中立"}
                      value={advParams.shift_sat_threshold_low} min={5} max={45} step={1}
                      onChange={(v) => setAdvParams({ ...advParams, shift_sat_threshold_low: v })}
                      disabled={running} />
                    <AdvSlider label={en ? "High anxiety threshold" : "高焦慮度閾值"}
                      hint={en ? "Above this + low satisfaction → shift to neutral" : "高於此值 + 低滿意度 → 轉中立"}
                      value={advParams.shift_anx_threshold_high} min={55} max={95} step={1}
                      onChange={(v) => setAdvParams({ ...advParams, shift_anx_threshold_high: v })}
                      disabled={running} />
                    <AdvSlider label={en ? "Consecutive days required" : "連續天數需求"}
                      hint={en ? "Days at threshold before shift triggers" : "達到閾值需連續幾天才會觸發"}
                      value={advParams.shift_consecutive_days_req} min={1} max={14} step={1}
                      onChange={(v) => setAdvParams({ ...advParams, shift_consecutive_days_req: v })}
                      disabled={running} />
                  </div>
                )}

                {advParams.enable_dynamic_leaning && (
                  <div style={{
                    marginTop: 12, padding: "10px 14px", borderRadius: 8,
                    background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.12)",
                    fontSize: 11, color: "rgba(255,255,255,0.45)", lineHeight: 1.6,
                  }}>
                    <div style={{ fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                      {en ? "Shift rules:" : "轉變規則："}
                    </div>
                    {en ? (
                      <>
                        <div>• Conservative/Republican-leaning → Neutral: local satisfaction ≤ {advParams.shift_sat_threshold_low} for {advParams.shift_consecutive_days_req} days</div>
                        <div>• Liberal/Democrat-leaning → Neutral: national satisfaction ≤ {advParams.shift_sat_threshold_low} for {advParams.shift_consecutive_days_req} days</div>
                        <div>• Either partisan → Neutral: anxiety ≥ {advParams.shift_anx_threshold_high} + satisfaction &lt; 50</div>
                        <div>• Neutral → Right-leaning: local satisfaction ≥ {100 - advParams.shift_sat_threshold_low} + national &lt; 50</div>
                        <div>• Neutral → Left-leaning: national satisfaction ≥ {100 - advParams.shift_sat_threshold_low} + local &lt; 50</div>
                      </>
                    ) : (
                      <>
                        <div>• 保守/偏右 → 中立：在地滿意度 ≤ {advParams.shift_sat_threshold_low}，連續 {advParams.shift_consecutive_days_req} 天</div>
                        <div>• 自由/偏左 → 中立：全國滿意度 ≤ {advParams.shift_sat_threshold_low}，連續 {advParams.shift_consecutive_days_req} 天</div>
                        <div>• 任一偏向 → 中立：焦慮度 ≥ {advParams.shift_anx_threshold_high} + 滿意度 &lt; 50</div>
                        <div>• 中立 → 偏右：在地滿意度 ≥ {100 - advParams.shift_sat_threshold_low} + 全國 &lt; 50</div>
                        <div>• 中立 → 偏左：全國滿意度 ≥ {100 - advParams.shift_sat_threshold_low} + 在地 &lt; 50</div>
                      </>
                    )}
                  </div>
                )}
              </div>

              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "0 0 20px" }} />

              {/* ── Section 2: News Impact & Echo Chamber ── */}
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ fontSize: 14 }}>📰</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    {en ? "News Impact & Echo Chamber" : "新聞影響 & 同溫層"}
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <AdvSlider label={en ? "News impact multiplier" : "新聞影響倍率"}
                    hint={en ? "How strongly news affects satisfaction/anxiety" : "新聞對滿意度/焦慮度的影響強度"}
                    value={advParams.news_impact} min={0.5} max={5.0} step={0.1} decimals={1}
                    onChange={(v) => setAdvParams({ ...advParams, news_impact: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Serendipity rate" : "跨同溫層機率"}
                    hint={en ? "Chance of seeing opposing viewpoint articles" : "Agent 看到對立觀點文章的機率"}
                    value={advParams.serendipity_rate} min={0} max={0.5} step={0.01} decimals={2} pct
                    onChange={(v) => setAdvParams({ ...advParams, serendipity_rate: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Articles per agent per day" : "每位 Agent 每日文章數"}
                    hint={en ? "Max news articles shown to each agent daily" : "每天給每位 Agent 看的最大新聞數"}
                    value={advParams.articles_per_agent} min={1} max={10} step={1}
                    onChange={(v) => setAdvParams({ ...advParams, articles_per_agent: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Memory forget rate" : "記憶遺忘率"}
                    hint={en ? "How fast agents forget old news" : "Agent 遺忘舊新聞的速度"}
                    value={advParams.forget_rate} min={0.01} max={0.5} step={0.01} decimals={2}
                    onChange={(v) => setAdvParams({ ...advParams, forget_rate: v })}
                    disabled={running} />
                </div>
              </div>

              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "0 0 20px" }} />

              {/* ── Section 3: Emotional Response ── */}
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ fontSize: 14 }}>💭</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    {en ? "Emotional Response" : "情緒反應"}
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                  <AdvSlider label={en ? "Max daily change" : "每日最大變化"}
                    hint={en ? "Multiplier on max daily satisfaction/anxiety change" : "每日滿意度/焦慮度最大變化倍率"}
                    value={advParams.delta_cap_mult} min={0.5} max={3.0} step={0.1} decimals={1}
                    onChange={(v) => setAdvParams({ ...advParams, delta_cap_mult: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Satisfaction decay" : "滿意度衰減率"}
                    hint={en ? "Daily pull toward neutral (50)" : "每天向中性值 (50) 回歸的速度"}
                    value={advParams.satisfaction_decay} min={0} max={0.1} step={0.005} decimals={3}
                    onChange={(v) => setAdvParams({ ...advParams, satisfaction_decay: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Anxiety decay" : "焦慮度衰減率"}
                    hint={en ? "Daily pull toward neutral (50)" : "每天向中性值 (50) 回歸的速度"}
                    value={advParams.anxiety_decay} min={0} max={0.15} step={0.005} decimals={3}
                    onChange={(v) => setAdvParams({ ...advParams, anxiety_decay: v })}
                    disabled={running} />
                </div>
              </div>

              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "0 0 20px" }} />

              {/* ── Section 4: Undecided & Party Effects ── */}
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ fontSize: 14 }}>🗳️</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    {en ? "Undecided Voters & Party Effects" : "未決定選民 & 政黨效應"}
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <AdvSlider label={en ? "Base undecided ratio" : "基礎未決定比例"}
                    hint={en ? "Starting proportion of undecided agents" : "未決定 Agent 的起始比例"}
                    value={advParams.base_undecided} min={0} max={0.3} step={0.01} decimals={2} pct
                    onChange={(v) => setAdvParams({ ...advParams, base_undecided: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Max undecided ratio" : "最大未決定比例"}
                    hint={en ? "Ceiling for undecided voters" : "未決定選民的上限"}
                    value={advParams.max_undecided} min={0.1} max={0.7} step={0.01} decimals={2} pct
                    onChange={(v) => setAdvParams({ ...advParams, max_undecided: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Party alignment bonus" : "政黨一致加分"}
                    hint={en ? "Score bonus for same-party candidate" : "候選人與 Agent 同黨時的加分"}
                    value={advParams.party_align_bonus} min={0} max={30} step={1}
                    onChange={(v) => setAdvParams({ ...advParams, party_align_bonus: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Incumbency bonus" : "現任者加分"}
                    hint={en ? "Score bonus for incumbent candidates" : "現任候選人的加分"}
                    value={advParams.incumbency_bonus} min={0} max={25} step={1}
                    onChange={(v) => setAdvParams({ ...advParams, incumbency_bonus: v })}
                    disabled={running} />
                </div>
              </div>

              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "0 0 20px" }} />

              {/* ── Section 5: Life Events ── */}
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ fontSize: 14 }}>🎲</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    {en ? "Life Events" : "生活事件"}
                  </span>
                </div>
                <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "0 0 12px", lineHeight: 1.5 }}>
                  {en
                    ? "Random life events (layoffs, promotions, medical bills, etc.) that directly impact agent satisfaction and anxiety."
                    : "隨機生活事件（裁員、升職、醫療帳單等）直接影響 Agent 的滿意度和焦慮度。"}
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <AdvSlider label={en ? "Individuality multiplier" : "個體差異倍率"}
                    hint={en ? "Global scale for per-agent personality effects" : "Agent 個人特質效果的全域倍率"}
                    value={advParams.individuality_multiplier} min={0} max={3.0} step={0.1} decimals={1}
                    onChange={(v) => setAdvParams({ ...advParams, individuality_multiplier: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Neutral reassign ratio" : "中立重新分配比例"}
                    hint={en ? "Fraction of partisans reassigned to neutral at start" : "開始時將部分黨派 Agent 重新分配為中立"}
                    value={advParams.neutral_ratio} min={0} max={0.4} step={0.01} decimals={2} pct
                    onChange={(v) => setAdvParams({ ...advParams, neutral_ratio: v })}
                    disabled={running} />
                </div>
              </div>

              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "0 0 20px" }} />

              {/* ── Section 6: News Category Mix ── */}
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ fontSize: 14 }}>📰</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    {en ? "News Category Mix" : "新聞類別比例"}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: "auto" }}>
                    {en ? `Total: ${advParams.news_mix_candidate + advParams.news_mix_national + advParams.news_mix_local + advParams.news_mix_international}%` : `合計: ${advParams.news_mix_candidate + advParams.news_mix_national + advParams.news_mix_local + advParams.news_mix_international}%`}
                    {(advParams.news_mix_candidate + advParams.news_mix_national + advParams.news_mix_local + advParams.news_mix_international) !== 100 && (
                      <span style={{ color: "#ef4444", marginLeft: 4 }}>({en ? "should be 100%" : "應為 100%"})</span>
                    )}
                  </span>
                </div>
                <p style={{ fontSize: 11, color: "var(--text-muted)", margin: "0 0 12px", lineHeight: 1.5 }}>
                  {en
                    ? "Control the proportion of each news category in the crawled news mix."
                    : "控制抓取新聞中各類別的比例。"}
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <AdvSlider label={en ? "Candidate news" : "候選人新聞"}
                    hint={en ? "News about specific candidates and campaigns" : "特定候選人、政見、民調、造勢活動"}
                    value={advParams.news_mix_candidate} min={0} max={60} step={5}
                    onChange={(v) => setAdvParams({ ...advParams, news_mix_candidate: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "National / Election" : "全國/中央"}
                    hint={en ? "Central government, Legislative Yuan, cross-strait, economy" : "總統、行政院、立法院、司法院、兩岸、國防、央行經濟"}
                    value={advParams.news_mix_national} min={0} max={60} step={5}
                    onChange={(v) => setAdvParams({ ...advParams, news_mix_national: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "Local news" : "地方新聞"}
                    hint={en ? "County / city governance, local elections, infrastructure" : "縣市長、議會、地方建設、交通、治安、學校"}
                    value={advParams.news_mix_local} min={0} max={60} step={5}
                    onChange={(v) => setAdvParams({ ...advParams, news_mix_local: v })}
                    disabled={running} />
                  <AdvSlider label={en ? "International" : "國際"}
                    hint={en ? "Foreign affairs, US-China-Taiwan, global events" : "美中台關係、俄烏、日韓、WHA、全球局勢"}
                    value={advParams.news_mix_international} min={0} max={60} step={5}
                    onChange={(v) => setAdvParams({ ...advParams, news_mix_international: v })}
                    disabled={running} />
                </div>
              </div>

              <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", margin: "0 0 20px" }} />

              {/* ── Section 7: Feed Stratification ── */}
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                  <span style={{ fontSize: 14 }}>🎯</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
                    {en ? "Feed Stratification" : "新聞曝光分層"}
                  </span>
                </div>

                <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 8 }}>
                  <input
                    type="checkbox"
                    id="use_exposure_mix"
                    checked={!!advParams.use_exposure_mix}
                    onChange={(e) => setAdvParams({ ...advParams, use_exposure_mix: e.target.checked })}
                    disabled={running}
                    style={{ marginTop: 2, cursor: running ? "not-allowed" : "pointer" }}
                  />
                  <label htmlFor="use_exposure_mix" style={{ fontSize: 12, color: "var(--text-secondary)", cursor: running ? "not-allowed" : "pointer", lineHeight: 1.5 }}>
                    {en
                      ? "Use media habit exposure mix (depth-aware feed)"
                      : "使用新聞曝光混合矩陣（depth-aware feed）"}
                  </label>
                </div>
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.45)", marginBottom: 12, lineHeight: 1.6, paddingLeft: 20 }}>
                  {en
                    ? "When enabled, each agent's daily news pool is pre-filtered by MEDIA_HABIT_EXPOSURE_MIX before select_feed runs — stratifying coverage by 深綠/偏綠/中間/偏藍/深藍 leaning depth. Improves research reproducibility."
                    : "啟用後，每位 Agent 每日新聞池在 select_feed 前先依 MEDIA_HABIT_EXPOSURE_MIX 按 深綠/偏綠/中間/偏藍/深藍 傾向深度分層採樣，提高研究可重現性。"}
                </div>

                {advParams.use_exposure_mix && (
                  <div style={{ paddingLeft: 20 }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      <label style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                        {en ? "Replication seed (0 = random)" : "複現種子（0 = 每次隨機）"}
                      </label>
                      <input
                        type="number"
                        min={0}
                        step={1}
                        value={advParams.replication_seed ?? 0}
                        onChange={(e) => setAdvParams({ ...advParams, replication_seed: Number(e.target.value) || 0 })}
                        disabled={running}
                        style={{
                          width: 120,
                          background: "rgba(255,255,255,0.06)",
                          border: "1px solid rgba(255,255,255,0.12)",
                          borderRadius: 6,
                          color: "var(--text-primary)",
                          fontSize: 12,
                          padding: "4px 8px",
                        }}
                      />
                      <div style={{ fontSize: 11, color: "rgba(255,255,255,0.35)", lineHeight: 1.5 }}>
                        {en
                          ? "Set a non-zero seed to reproduce identical article selections across runs."
                          : "設定非零種子可在多次跑演化時得到完全相同的文章選取，方便實驗比較。"}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* ── Reset to defaults ── */}
              <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <button
                    onClick={() => setAdvParams({ ...templateCalib })}
                    disabled={running}
                    style={{
                      background: "none", border: "1px solid var(--border-subtle)",
                      color: "var(--text-muted)", fontSize: 11, padding: "4px 12px",
                      borderRadius: 6, cursor: "pointer",
                    }}
                  >
                    {en ? "Reset to template defaults" : "恢復模板預設值"}
                  </button>
                  {JSON.stringify(advParams) !== JSON.stringify(templateCalib) && (
                    <span style={{ fontSize: 10, color: "#fbbf24" }}>
                      {en ? "● Modified" : "● 已修改"}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => router.push(`/workspaces/${wsId}/evolution`)}
                  style={{
                    background: "none", border: "none", color: "var(--text-muted)",
                    fontSize: 11, cursor: "pointer", textDecoration: "underline",
                  }}
                >
                  {en ? "News Sources & Memory Explorer →" : "新聞來源 & 記憶探索 →"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <style jsx>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

/* ── Slider sub-component ── */

function AdvSlider({ label, hint, value, min, max, step, onChange, disabled, decimals = 0, pct = false }: {
  label: string; hint: string; value: number; min: number; max: number; step: number;
  onChange: (v: number) => void; disabled?: boolean; decimals?: number; pct?: boolean;
}) {
  const display = pct ? `${(value * 100).toFixed(0)}%` : value.toFixed(decimals);
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{label}</span>
        <span style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{display}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        style={{ width: "100%", accentColor: "#e94560" }}
      />
      <div style={{ fontSize: 10, color: "rgba(255,255,255,0.25)", marginTop: 2 }}>{hint}</div>
    </div>
  );
}
