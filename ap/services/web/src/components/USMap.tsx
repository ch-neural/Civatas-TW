"use client";

import { useState, useEffect, useRef, useMemo, useCallback } from "react";

/**
 * USMap — SVG choropleth map of Taiwan counties / townships.
 *
 * (The component name is kept as USMap for backward compat with existing
 * panel imports; internally it draws Taiwan's 22 縣市 and 368 鄉鎮市區.)
 *
 * Data keying:
 *   mode === "states"    (alias "counties"):  key = county name   (e.g. "臺北市")
 *   mode === "counties"  (alias "townships"): key = admin_key     (e.g. "臺北市|大安區")
 *
 * Drill-down: pass `selectedState` (a county name like "臺北市") and the component
 * renders only that county's townships from tw-townships.geojson, scaled to fill
 * the canvas.
 *
 * Projection: simple equirectangular with aspect correction for Taiwan's midlat.
 * Taiwan's geographic footprint is compact enough that the simplification is
 * imperceptible; no multi-region composite (unlike AK/HI) is needed. Outlying
 * islands (澎湖/金門/馬祖) are drawn in-place but rarely fit the mainland frame
 * cleanly — caller should either accept the full extent or pre-filter.
 *
 * Loaded GeoJSON files (must be in /public/):
 *   /tw-counties.geojson       22 features, properties = { name, id }
 *   /tw-townships.geojson      ~375 features, properties = { name, id, county, admin_key }
 */

type AdminKey = string;

interface USMapProps {
  data?: Record<AdminKey, number>;
  mode?: "states" | "counties" | "townships";   // legacy + TW-native aliases
  selectedState?: string;                        // county name to drill into (e.g. "臺北市")
  selectedFeature?: string;                      // highlight a single feature
  colorScale?: [string, string];
  divergingColorScale?: [string, string, string];
  onFeatureClick?: (key: string, name: string) => void;
  onFeatureHover?: (key: string | null) => void;
  width?: number;
  height?: number;
  title?: string;
  valueLabel?: string;
  showLegend?: boolean;
  diverging?: boolean;
}

// ── Equirectangular projection with aspect correction ───────────────────
//
// Taiwan fits into a single local projection without the AK/HI insets US
// maps need. We choose a central-meridian that sits over mainland Taiwan
// so outlying islands (Penghu/Kinmen/Matsu) project slightly to the side —
// enough to visually distinguish but still in frame when padding is modest.

const D2R = Math.PI / 180;

function fitProjection(
  features: any[],
  w: number,
  h: number,
  pad = 0.05,
) {
  let minLon = Infinity, maxLon = -Infinity;
  let minLat = Infinity, maxLat = -Infinity;
  for (const f of features) {
    const geom = f?.geometry;
    if (!geom) continue;
    const walk = (coords: any) => {
      if (typeof coords[0] === "number") {
        const [lon, lat] = coords;
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        return;
      }
      coords.forEach(walk);
    };
    walk(geom.coordinates);
  }
  if (!isFinite(minLon)) {
    // Fallback to TW bounding box if features were empty
    minLon = 119.3; maxLon = 122.3; minLat = 21.8; maxLat = 25.3;
  }
  const padX = w * pad;
  const padY = h * pad;
  const plotW = w - padX * 2;
  const plotH = h - padY * 2;
  const lonRange = (maxLon - minLon) || 1;
  const latRange = (maxLat - minLat) || 1;
  const midLat = (minLat + maxLat) / 2;
  const aspectCorrect = Math.cos(midLat * D2R);
  const scale = Math.min(
    plotW / (lonRange * aspectCorrect),
    plotH / latRange,
  );
  // Centre the content within the plot area
  const actualW = lonRange * aspectCorrect * scale;
  const actualH = latRange * scale;
  const offX = padX + (plotW - actualW) / 2;
  const offY = padY + (plotH - actualH) / 2;
  return (lon: number, lat: number): [number, number] => {
    const x = offX + (lon - minLon) * aspectCorrect * scale;
    const y = offY + (maxLat - lat) * scale;
    return [x, y];
  };
}

// ── Geometry → SVG path string ──────────────────────────────────────────

function ringToPath(
  ring: number[][],
  project: (lon: number, lat: number) => [number, number],
): string {
  if (!ring || ring.length === 0) return "";
  return ring
    .map((pt, i) => {
      const [x, y] = project(pt[0], pt[1]);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join("") + "Z";
}

function featureToPath(
  feature: any,
  project: (lon: number, lat: number) => [number, number],
): string {
  const geom = feature.geometry;
  if (geom.type === "Polygon") {
    return geom.coordinates
      .map((ring: number[][]) => ringToPath(ring, project))
      .join(" ");
  }
  if (geom.type === "MultiPolygon") {
    return geom.coordinates
      .map((polygon: number[][][]) =>
        polygon.map((ring: number[][]) => ringToPath(ring, project)).join(" "),
      )
      .join(" ");
  }
  return "";
}

// ── Colour interpolation ────────────────────────────────────────────────

function parseHex(c: string): [number, number, number] {
  const hex = c.replace("#", "");
  return [
    parseInt(hex.slice(0, 2), 16),
    parseInt(hex.slice(2, 4), 16),
    parseInt(hex.slice(4, 6), 16),
  ];
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function rgbToHex(r: number, g: number, b: number): string {
  const h = (n: number) =>
    Math.round(Math.max(0, Math.min(255, n))).toString(16).padStart(2, "0");
  return `#${h(r)}${h(g)}${h(b)}`;
}

function colourFor(
  val: number | undefined,
  min: number,
  max: number,
  scale: [string, string],
  diverging: boolean,
  divergingScale?: [string, string, string],
): string {
  if (val === undefined || Number.isNaN(val)) return "#222b38";
  if (diverging && divergingScale) {
    const [negHex, midHex, posHex] = divergingScale;
    const n = parseHex(negHex);
    const m = parseHex(midHex);
    const p = parseHex(posHex);
    // Map val in [-absMax, +absMax] to colour.
    const absMax = Math.max(Math.abs(min), Math.abs(max)) || 1;
    const t = Math.max(-1, Math.min(1, val / absMax));
    if (t >= 0) {
      const u = t;
      return rgbToHex(lerp(m[0], p[0], u), lerp(m[1], p[1], u), lerp(m[2], p[2], u));
    }
    const u = -t;
    return rgbToHex(lerp(m[0], n[0], u), lerp(m[1], n[1], u), lerp(m[2], n[2], u));
  }
  const a = parseHex(scale[0]);
  const b = parseHex(scale[1]);
  const t = max === min ? 0.5 : (val - min) / (max - min);
  return rgbToHex(lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t));
}

// ── Component ───────────────────────────────────────────────────────────

export function USMap({
  data = {},
  mode = "states",
  selectedState,
  selectedFeature,
  colorScale = ["#1e293b", "#38bdf8"],
  divergingColorScale = ["#dc2626", "#f1f5f9", "#2563eb"],
  onFeatureClick,
  onFeatureHover,
  width = 800,
  height = 500,
  title,
  valueLabel,
  showLegend = true,
  diverging = false,
}: USMapProps) {
  // Normalise mode aliases. "states" ⇒ 縣市層，"counties"|"townships" ⇒ 鄉鎮層
  const effectiveMode: "counties" | "townships" =
    mode === "townships" || (mode === "counties" && !selectedState)
      ? (mode === "townships" ? "townships" : selectedState ? "townships" : "counties")
      : mode === "counties"
        ? "townships"
        : "counties";

  const [rawFeatures, setRawFeatures] = useState<any[] | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const loadedRef = useRef<string>("");

  useEffect(() => {
    const url =
      effectiveMode === "counties" ? "/tw-counties.geojson" : "/tw-townships.geojson";
    if (loadedRef.current === url) return;
    loadedRef.current = url;
    fetch(url)
      .then((r) => r.json())
      .then((geo) => setRawFeatures(geo.features || []))
      .catch((err) => {
        console.error("TaiwanMap: failed to fetch geojson", err);
        setRawFeatures([]);
      });
  }, [effectiveMode]);

  // When drilling into a county, filter townships to that county's set.
  const features = useMemo(() => {
    if (!rawFeatures) return null;
    if (effectiveMode === "townships" && selectedState) {
      return rawFeatures.filter(
        (f) => f?.properties?.county === selectedState,
      );
    }
    return rawFeatures;
  }, [rawFeatures, effectiveMode, selectedState]);

  const project = useMemo(() => {
    if (!features || features.length === 0) {
      return (lon: number, lat: number): [number, number] => [width / 2, height / 2];
    }
    return fitProjection(features, width, height);
  }, [features, width, height]);

  // Value extents for colour scaling
  const [minV, maxV] = useMemo(() => {
    const vs = Object.values(data).filter((v) => typeof v === "number" && !Number.isNaN(v));
    if (vs.length === 0) return [0, 1];
    return [Math.min(...vs), Math.max(...vs)];
  }, [data]);

  const keyOf = useCallback((feat: any): string => {
    const p = feat?.properties || {};
    if (effectiveMode === "counties") return p.name || p.id || "";
    // township: prefer admin_key, fall back to "{county}|{name}"
    return p.admin_key || (p.county && p.name ? `${p.county}|${p.name}` : p.name || "");
  }, [effectiveMode]);

  const handleEnter = (key: string) => {
    setHovered(key);
    onFeatureHover?.(key);
  };
  const handleLeave = () => {
    setHovered(null);
    onFeatureHover?.(null);
  };

  if (!features) {
    return (
      <div
        style={{
          width,
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0f172a",
          color: "#94a3b8",
          fontSize: 13,
        }}
      >
        載入地圖中…
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      {title ? (
        <div
          style={{
            position: "absolute",
            top: 8,
            left: 12,
            color: "#e2e8f0",
            fontSize: 13,
            fontWeight: 600,
            pointerEvents: "none",
          }}
        >
          {title}
        </div>
      ) : null}
      <svg width={width} height={height} style={{ background: "#0b1220", borderRadius: 6 }}>
        {features.map((feat: any, i: number) => {
          const key = keyOf(feat);
          const name = feat.properties?.name || key;
          const v = data[key];
          const fill = colourFor(v, minV, maxV, colorScale, diverging, divergingColorScale);
          const isHover = hovered === key;
          const isSel = selectedFeature === key;
          const stroke = isSel ? "#fbbf24" : isHover ? "#f472b6" : "#334155";
          const sw = isSel ? 1.8 : isHover ? 1.4 : 0.4;
          return (
            <path
              key={`${key}-${i}`}
              d={featureToPath(feat, project)}
              fill={fill}
              stroke={stroke}
              strokeWidth={sw}
              style={{ cursor: onFeatureClick ? "pointer" : "default", transition: "stroke 120ms" }}
              onMouseEnter={() => handleEnter(key)}
              onMouseLeave={handleLeave}
              onClick={() => onFeatureClick?.(key, name)}
            >
              <title>{v !== undefined ? `${name}: ${v}` : name}</title>
            </path>
          );
        })}
      </svg>
      {showLegend && Object.keys(data).length > 0 ? (
        <div
          style={{
            position: "absolute",
            right: 12,
            bottom: 12,
            background: "rgba(15,23,42,0.85)",
            color: "#e2e8f0",
            padding: "6px 10px",
            borderRadius: 4,
            fontSize: 11,
            lineHeight: 1.4,
            pointerEvents: "none",
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 2 }}>{valueLabel || "值"}</div>
          <div>
            {diverging
              ? `${minV.toFixed(2)} — 0 — ${maxV.toFixed(2)}`
              : `${minV.toFixed(2)} — ${maxV.toFixed(2)}`}
          </div>
        </div>
      ) : null}
    </div>
  );
}

// Backward compatibility aliases (some panels may import TaiwanMap directly).
export const TaiwanMap = USMap;
export default USMap;
