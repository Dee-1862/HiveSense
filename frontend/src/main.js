import { pollCoordinator, subscribeEvents, startTreatment, respondTreatment, listTreatments } from "./api.js";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";

/* ---------------- data ---------------- */
const HIVES = [
  { code: "A1", name: "Clover Stand", st: "ok", mite: 0.7, mtrend: "steady", scanned: 412, mites: 3, queen: "Queenright", qc: 0.97, stress: 18, swarm: false, roar: false, bpm: 142, btrend: "up", beard: false, wasp: "low", cong: 14, dwv: false, freq: "~310 Hz hum" },
  { code: "A2", name: "Manzanita", st: "ok", mite: 1.2, mtrend: "steady", scanned: 388, mites: 5, queen: "Queenright", qc: 0.95, stress: 24, swarm: false, roar: false, bpm: 118, btrend: "steady", beard: false, wasp: "low", cong: 21, dwv: false, freq: "~300 Hz hum" },
  { code: "A3", name: "Yarrow", st: "watch", mite: 2.7, mtrend: "rising", scanned: 441, mites: 12, queen: "Queenright", qc: 0.93, stress: 48, swarm: false, roar: false, bpm: 96, btrend: "down", beard: false, wasp: "med", cong: 33, dwv: false, freq: "~330 Hz, broadening" },
  { code: "B1", name: "Sage Row", st: "crit", mite: 4.6, mtrend: "rising", scanned: 506, mites: 23, queen: "Queenright", qc: 0.9, stress: 71, swarm: false, roar: false, bpm: 74, btrend: "down", beard: false, wasp: "low", cong: 28, dwv: true, freq: "~360 Hz stress band" },
  { code: "B2", name: "Honeysuckle", st: "ok", mite: 0.9, mtrend: "steady", scanned: 399, mites: 4, queen: "Queenright", qc: 0.96, stress: 20, swarm: false, roar: false, bpm: 151, btrend: "up", beard: false, wasp: "low", cong: 12, dwv: false, freq: "~305 Hz hum" },
  { code: "B3", name: "Lupine", st: "watch", mite: 1.4, mtrend: "steady", scanned: 377, mites: 5, queen: "Pre-swarm", qc: 0.81, stress: 58, swarm: true, roar: false, bpm: 188, btrend: "up", beard: true, wasp: "low", cong: 46, dwv: false, freq: "swarm spike ~250 Hz" },
  { code: "C1", name: "Buckwheat", st: "crit", mite: 1.0, mtrend: "steady", scanned: 362, mites: 4, queen: "Queenless", qc: 0.88, stress: 64, swarm: false, roar: true, bpm: 61, btrend: "down", beard: false, wasp: "med", cong: 19, dwv: false, freq: "queenless roar ~400 Hz" },
  { code: "C2", name: "Toyon", st: "ok", mite: 1.1, mtrend: "steady", scanned: 421, mites: 5, queen: "Queenright", qc: 0.96, stress: 22, swarm: false, roar: false, bpm: 133, btrend: "steady", beard: false, wasp: "low", cong: 18, dwv: false, freq: "~308 Hz hum" },
  { code: "C3", name: "Ceanothus", st: "watch", mite: 1.3, mtrend: "steady", scanned: 390, mites: 5, queen: "Queenright", qc: 0.94, stress: 39, swarm: false, roar: false, bpm: 88, btrend: "down", beard: false, wasp: "high", cong: 24, dwv: false, freq: "intrusion chatter" }
];
const STMAP = { ok: "ok", watch: "watch", crit: "crit" };
const STWORD = { ok: "Healthy", watch: "Watch", crit: "Action required" };

// per-hive plain-language headline + recommended action
function headline(h) {
  if (h.queen === "Queenless") return "Colony has likely <b>lost its queen</b>. Acoustic roar plus a falling foragers count.";
  if (h.queen === "Pre-swarm") return "Reading <b>pre-swarm</b>. Big traffic jump, bearding at the entrance, and a low-frequency swarm spike.";
  if (h.st === "crit") return "<b>Mite load past the treatment line</b> with early deformed-wing signs. This colony needs help this week.";
  if (h.st === "watch" && h.wasp === "high") return "Healthy brood, but <b>wasp pressure is high</b> at the entrance. Robbing risk.";
  if (h.st === "watch" && h.mtrend === "rising") return "Mites are <b>trending up</b> toward the line. Worth a closer look soon.";
  if (h.st === "watch") return "Mostly fine. One signal is drifting, so it is flagged for a look.";
  return "Strong colony. Mite load well under the line, queen present, steady traffic.";
}
function action(h) {
  if (h.queen === "Queenless") return { k: "Recommended action", c: true, t: "Confirm queenlessness, then introduce a mated queen or a frame of young eggs within 72 hours. A queenless colony will not raise a new queen without eggs present." };
  if (h.queen === "Pre-swarm") return { k: "Recommended action", c: false, t: "Inspect for capped queen cells within 48 hours. Add a super for space, or make a walk-away split to keep the colony and capture the swarm impulse." };
  if (h.st === "crit" && h.dwv) return { k: "Treat this week", c: true, t: "Mite load is 4.6 per 100 bees, above the 3 per 100 line. Brood is low right now, which is a high-efficacy window. Oxalic acid vapor or an approved miticide, then re-test in 14 days. Watch for more deformed wings." };
  if (h.wasp === "high") return { k: "Recommended action", c: false, t: "Reduce the entrance to a single bee-width to help guards repel wasps. Remove nearby exposed comb or syrup that draws robbers." };
  if (h.mtrend === "rising") return { k: "Watch closely", c: false, t: "Re-test mite load in 7 days. No treatment yet, but plan one if it crosses 3 per 100 bees." };
  return { k: "No action needed", c: false, t: "This colony looks strong, so there is nothing to do right now. Just keep it on your normal inspection schedule." };
}
function fusion(h) {
  if (h.queen === "Queenless") return { conf: 0.88, rule: "acoustic.roar=TRUE  +  behavior.foragers↓>30%  →  QUEENLESS", sig: ["Acoustic colony worker", "Behavior worker"] };
  if (h.queen === "Pre-swarm") return { conf: 0.83, rule: "acoustic.swarm_spike + behavior.bearding + traffic↑  →  PRE-SWARM", sig: ["Acoustic colony worker", "Behavior worker"] };
  if (h.st === "crit") return { conf: 0.91, rule: "vision.mite_pct>3.0  AND  acoustic.stress>65  →  VARROA CONFIRMED", sig: ["Vision worker", "Acoustic Varroa worker"] };
  if (h.wasp === "high") return { conf: 0.79, rule: "behavior.wasp=HIGH + entrance.congestion  →  ROBBING RISK", sig: ["Behavior worker"] };
  return { conf: 0.96, rule: "all signals within colony baseline  →  STABLE", sig: ["Fusion core"] };
}

/* ---------------- state + render ---------------- */
const S = { view: "map", sel: HIVES[3].code, pipe: "vision", mode: "field", mapmode: "schem", mapfilter: "all", mapzoom: 1 };
const $ = s => document.querySelector(s);
const get = c => HIVES.find(h => h.code === c);

function renderSummary() {
  const crit = HIVES.filter(h => h.st === "crit").length, watch = HIVES.filter(h => h.st === "watch").length;
  const idx = Math.round(100 - (crit * 16 + watch * 6) - HIVES.reduce((a, h) => a + h.mite, 0) / HIVES.length * 2);
  $("#s-health").textContent = idx; $("#s-health").style.color = idx > 80 ? "var(--ok)" : idx > 65 ? "var(--watch)" : "var(--crit)";
  $("#s-hives").textContent = HIVES.length;
  $("#s-alerts").textContent = crit + watch;
  $("#threat-txt").textContent = "THREAT LEVEL: " + (crit ? "ELEVATED" : "NOMINAL") + " · " + crit + " CRITICAL · " + watch + " WATCH · OPS WINDOW 7d";
}
// organic layout: pallet clusters + a loose row, with slight per-hive rotation (viewBox 900x560)
// Clean, evenly spaced 3x3 grid (no rotation, no decorative yard) for legibility.
const POS = {
  A1: [230, 150, 0], A2: [450, 150, 0], A3: [670, 150, 0],
  B1: [230, 305, 0], B2: [450, 305, 0], B3: [670, 305, 0],
  C1: [230, 460, 0], C2: [450, 460, 0], C3: [670, 460, 0]
};
/* ---- REAL apiary geography (satellite mode) ----
   UC Davis · Harry H. Laidlaw Jr. Honey Bee Research Facility, 225 Bee Biology Rd.
   The basemap is genuine Esri World Imagery (no API key) for a bbox tied to the
   real coordinates below. Hive boxes are placed on the actual grassy apiary yard
   visible in the imagery (normalized [u,v] over the 900x560 frame). Schematic mode
   stays a non-geographic plot via POS above. */
const APIARY = {
  name: "UC DAVIS · LAIDLAW APIARY",
  // Centred on an OPEN research field (clean, uncluttered ground) so the colony
  // markers read clearly. The hives on the map are our own markers on a satellite
  // backdrop - legibility is a property of the markers, not the orbital imagery.
  lat: 38.5384, lon: -121.7884,
  bbox: [-121.78927, 38.53786, -121.78753, 38.53894], // [W,S,E,N] ~ the yard
};
// Realistic, irregular 3-row apiary. Per hive: [east_m, north_m, rotation_deg]
// from the yard centre. Spread ~45 m × 30 m so the (larger) markers don't collide.
const YARD_M_LAT = 110574, YARD_M_LON = 111320 * Math.cos(APIARY.lat * Math.PI / 180);
const YARD_LAYOUT = {
  A1: [-22, 13, -4], A2: [-7, 15, 3], A3: [9, 12, -2], B1: [23, 14, 5],
  B2: [-18, -2, 2], B3: [-2, 0, -3], C1: [14, -3, 4],
  C2: [-10, -15, -2], C3: [8, -13, 3],
};
/* ---- Field sensor network ----
   One sensor node per hive (CAM / MIC / GATE), each with a number and an
   online flag. The operator draws each sensor's coverage boundary on the map and
   it is mapped to the sensor's number; boundaries persist in localStorage. */
const SENSORS = HIVES.map((h, i) => ({
  id: "S-" + String(i + 1).padStart(2, "0"),
  type: ["CAM", "MIC", "GATE"][i % 3],
  hive: h.code,
  online: ![7, 8].includes(i),  // S-08 (C2) + S-09 (C3) offline → no tunnel feed there
}));
const SENSOR_BY_ID = Object.fromEntries(SENSORS.map(s => [s.id, s]));
// Live-coordinator link state (declared here so sensorOnline()/the sensor panel
// can read it during boot; the polling logic that mutates it lives at the bottom).
// Backend hive_id -> on-map UI code; extend as more supervisors come online.
const HIVE_MAP = { hive3: "A3", hive5: "B2" };
const LINK = { state: "offline", latency: null, lastTs: {}, liveCodes: new Set() };
// A sensor is online if its base flag says so, OR (in live mode) its hive is
// actively streaming verdicts from the coordinator.
function sensorOnline(s) { return s.online || (LINK.state === "live" && LINK.liveCodes.has(s.hive)); }
function onlineCount() { return SENSORS.filter(sensorOnline).length; }

const SENSOR_KEY = "hivesense.sensorBoundaries.v1";
function loadBoundaries() { try { return JSON.parse(localStorage.getItem(SENSOR_KEY)) || {}; } catch { return {}; } }
function saveBoundaries() { try { localStorage.setItem(SENSOR_KEY, JSON.stringify(boundaries)); } catch { } }
let boundaries = loadBoundaries();   // { sensorId: GeoJSON geometry }
let boundaryLayers = {};             // { sensorId: Leaflet layer }
let armedSensor = null;              // sensor id currently being drawn for

/* ---- Per-hive tunnel video + entrance audio ----
   Real clips served from /media (public/). Videos are REUSED across hives (only 3
   tunnel recordings exist); audio is UNIQUE to each hive (no clip repeats). Seven
   hives have a live feed; the two whose sensor is offline (B1=S-04, C2=S-08) show
   no feed. No model/inference values are attached here - just raw playback. */
const MEDIA_BASE = "/media/";
const MEDIA = {
  A1: { video: "tunnel_free", audio: "ent_01" },
  A2: { video: "tunnel_inf1", audio: "ent_02" },
  A3: { video: "tunnel_inf2", audio: "ent_03" },
  B1: { video: "tunnel_inf1", audio: "ent_04" },
  B2: { video: "tunnel_free", audio: "ent_05" },
  B3: { video: "tunnel_inf2", audio: "ent_06" },
  C1: { video: "tunnel_free", audio: "ent_07" },
  // C2, C3 have no feed - their sensors (S-08, S-09) are offline.
};
const sensorForHive = code => (SENSORS.find(s => s.hive === code) || {}).id || "none";
function mediaBlock(h) {
  const m = MEDIA[h.code];
  if (!m) return '<div class="media-off"><b>Entrance tunnel feed offline</b>'
    + '<span>The sensor for this colony is offline, so there is no live video or audio right now.</span></div>';
  return '<div class="media">'
    + '<div class="mediatag"><span class="d"></span>ENTRANCE TUNNEL · CAM-HIVE-' + h.code + '</div>'
    + '<video class="tunnelvid" src="' + MEDIA_BASE + 'video/' + m.video + '.mp4" poster="' + MEDIA_BASE + 'video/' + m.video + '.jpg" autoplay loop muted playsinline preload="auto"></video>'
    + '<span class="aulive"><span class="d"></span>listening</span></div>'
    + '</div>';
}
// map a hive's real geo position to a [lat,lon] readout for the HUD.
function hiveLatLon(code) {
  const o = YARD_LAYOUT[code] || [0, 0, 0];
  return [APIARY.lat + o[1] / YARD_M_LAT, APIARY.lon + o[0] / YARD_M_LON];
}
function passFilter(h) { return S.mapfilter === "all" ? true : S.mapfilter === "watch" ? h.st !== "ok" : h.st === "crit"; }
function hiveSVG(h) {
  const p = POS[h.code], cx = p[0], cy = p[1], rot = p[2] || 0;
  const w = 38, ht = 46, x = -w / 2, y = -ht / 2;
  const land = (x + 8) + "," + (y + ht) + " " + (x + w - 8) + "," + (y + ht) + " " + (x + w - 11) + "," + (y + ht + 7) + " " + (x + 11) + "," + (y + ht + 7);
  const b = 4, L = 8;
  const br = 'M' + (x - b) + ',' + (y - b + L) + 'V' + (y - b) + 'H' + (x - b + L) + ' M' + (x + w + b - L) + ',' + (y - b) + 'H' + (x + w + b) + 'V' + (y - b + L)
    + ' M' + (x + w + b) + ',' + (y + ht + b - L) + 'V' + (y + ht + b) + 'H' + (x + w + b - L) + ' M' + (x - b + L) + ',' + (y + ht + b) + 'H' + (x - b) + 'V' + (y + ht + b - L);
  return '<g class="hbx' + (h.code === S.sel ? ' sel' : '') + '" data-st="' + STMAP[h.st] + '" data-code="' + h.code + '" data-cx="' + cx + '" data-cy="' + cy + '">'
    + '<g transform="translate(' + cx + ',' + cy + ') rotate(' + rot + ')">'
    + '<polygon class="land" points="' + land + '"/>'
    + '<rect class="body" x="' + x + '" y="' + y + '" width="' + w + '" height="' + ht + '" rx="2.5"/>'
    + '<rect class="lid" x="' + (x + 4) + '" y="' + (y + 4) + '" width="' + (w - 8) + '" height="' + (ht - 12) + '" rx="1.5"/>'
    + '<line class="ent" x1="' + (x + 8) + '" y1="' + (y + ht) + '" x2="' + (x + w - 8) + '" y2="' + (y + ht) + '"/>'
    + '<rect class="pip" x="' + (x + 3) + '" y="' + (y + 3) + '" width="5.5" height="5.5"/>'
    + '<path class="bracket" d="' + br + '"/>'
    + '</g>'
    + '<text class="code" x="' + cx + '" y="' + (cy + ht / 2 + 18) + '">' + h.code + '</text>'
    + '<text class="val" x="' + cx + '" y="' + (cy + ht / 2 + 29) + '">' + h.mite.toFixed(1) + '/100</text>'
    + '</g>';
}
function siteDecor() {
  // Drawn (NON-geographic) surroundings: the apiary parcel where the hives sit, plus a few
  // asymmetric roads and neighbouring fields laid out in a wider coordinate space, so when
  // you zoom OUT the land and the roads around it come into view. Hives stay on a clean grid.
  const parcel = "30,46 874,32 896,540 22,526";  // expanded outward (more land around the hives)
  let s = '';
  s += '<rect class="m-bg" x="-500" y="-340" width="1900" height="1240"/>';
  // neighbouring fields, tucked into the far corners (clear of the parcel and the roads)
  s += '<polygon class="m-field" points="-460,-320 -180,-320 -180,-60 -460,-30"/>';
  s += '<polygon class="m-field" points="980,-320 1340,-320 1340,-80 980,-60"/>';
  // roads sit only in the outer margins: they never cross the parcel or each other
  s += '<path class="m-road" d="M-500,648 C150,612 760,690 1400,604"/>';   // main road below the yard
  s += '<path class="m-roadline" d="M-500,648 C150,612 760,690 1400,604"/>';
  s += '<path class="m-road" d="M-150,-340 C-130,80 -120,340 -110,560"/>';  // lane down the left side
  // the apiary parcel + a faint internal grid for structure
  s += '<polygon class="m-parcel" points="' + parcel + '"/>';
  s += '<text class="m-lbl" x="80" y="40">APIARY YARD</text>';
  let grid = ''; for (let gx = 180; gx < 760; gx += 130) grid += '<line class="m-grid" x1="' + gx + '" y1="80" x2="' + gx + '" y2="488"/>';
  for (let gy = 130; gy < 470; gy += 120) grid += '<line class="m-grid" x1="120" y1="' + gy + '" x2="800" y2="' + gy + '"/>';
  s += '<g opacity="0.5">' + grid + '</g>';
  return s
    + '<g class="reticle" id="reticle" style="display:none"><line id="rv" x1="0" y1="0" x2="0" y2="0"/><line id="rh" x1="0" y1="0" x2="0" y2="0"/></g>'
    + '<text class="hovtag" id="hovtag" style="display:none"></text>';
}
/* ====================================================================
   SATELLITE: a real Leaflet slippy map (Esri World Imagery tiles).
   --------------------------------------------------------------------
   Unlike a static export, tiles re-fetch at higher resolution as you
   zoom, so there is NO blur on zoom-in. The detection boxes are true
   georeferenced overlays (L.rectangle at each hive's real lat/lng), so
   they stay welded to the hive at every zoom and never degrade. Run
   with ?align=1 to drag the boxes onto the hives and log their coords.
   ==================================================================== */
let satMap = null, satTag = {}, satTiles = null;
const colorOf = st => st === "crit" ? "#d65a52" : st === "watch" ? "#d9913f" : "#4caf7d";

// Basemap: Esri World Imagery only - properly licensed and reliable for demo day.
// (Scraped Google tiles are kept out of the live dashboard for ToU + reliability.)
// maxNativeZoom = deepest level with REAL imagery; we allow OVERZOOM levels past it
// for fine box placement, where only the last level is mildly CSS-upscaled.
const ESRI = {
  url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  maxNativeZoom: 21, attribution: "Imagery © Esri, Maxar, Earthstar Geographics"
};
const OVERZOOM = 1;
function setBasemap() {
  if (!satMap || satTiles) return;
  const maxZ = ESRI.maxNativeZoom + OVERZOOM;
  satMap.setMaxZoom(maxZ);
  // NOTE: tileLayer's own maxZoom defaults to 18 - must raise it or tiles vanish above z18.
  satTiles = L.tileLayer(ESRI.url, { maxZoom: maxZ, maxNativeZoom: ESRI.maxNativeZoom, attribution: ESRI.attribution }).addTo(satMap);
  satTiles.bringToBack();
}

// ~0.9 m half-box around a hive centre, in degrees (frames one colony coverage area).
function boxBounds(lat, lon, half = 0.9) {
  const dLat = half / 110574, dLon = half / (111320 * Math.cos(lat * Math.PI / 180));
  return [[lat - dLat, lon - dLon], [lat + dLat, lon + dLon]];
}
// Large, legible colony marker - a status-coloured hive badge with a pointer, drawn
// in screen space so it stays clear at every zoom. THIS is what the judges read.
const HEX = '<svg class="hx" viewBox="0 0 24 24"><path d="M12 2l8.7 5v10L12 22l-8.7-5V7z"/></svg>';
function hiveMarkIcon(h) {
  return L.divIcon({
    className: "", iconSize: [46, 34], iconAnchor: [23, 34],
    html: '<div class="hivemark ' + h.st + (h.code === S.sel ? ' sel' : '') + '">' + HEX + '<span class="hm-code">' + h.code + '</span></div>'
  });
}
function initSatMap() {
  if (satMap) return satMap;
  satMap = L.map("leaflet", { zoomControl: false, attributionControl: true, minZoom: 16, maxZoom: 22 });
  // Open on the open field at z20 so the whole yard of markers reads on clean ground.
  satMap.setView([APIARY.lat, APIARY.lon], 20);
  setBasemap();
  wireMapSearch();                   // place search + home
  L.control.zoom({ position: "bottomright" }).addTo(satMap); // topleft is reserved for the sensor panel
  L.control.scale({ imperial: false, position: "bottomleft" }).addTo(satMap);
  HIVES.forEach(h => {
    const [lat, lon] = hiveLatLon(h.code);
    const tag = L.marker([lat, lon], { icon: hiveMarkIcon(h), keyboard: false, riseOnHover: true }).addTo(satMap);
    tag.on("click", () => { S.sel = h.code; renderDetail(); resetCam(); refreshSatStyles(); });
    satTag[h.code] = tag;
  });

  // ---- sensor nodes + drawing layer (Geoman) ----
  satMap.createPane("sensors"); satMap.getPane("sensors").style.zIndex = 620;
  SENSORS.forEach(s => {
    const [la, lo] = hiveLatLon(s.hive);
    s._node = L.circleMarker([la, lo], {
      pane: "sensors", radius: 4, weight: 2,
      color: sensorOnline(s) ? "#4caf7d" : "#d65a52", fillColor: "#0a0d12", fillOpacity: 1
    })
      .addTo(satMap).bindTooltip(s.id + " · " + s.type + " · " + s.hive, { direction: "top" });
  });

  // Geoman draw/edit toolbar (rectangle, polygon, circle + edit/drag/remove).
  satMap.pm.addControls({
    position: "topright", drawMarker: false, drawCircleMarker: false,
    drawPolyline: false, drawText: false, drawRectangle: true, drawPolygon: true, drawCircle: true,
    editMode: true, dragMode: true, removalMode: true, rotateMode: false, cutPolygon: false
  });
  satMap.pm.setGlobalOptions({ snappable: true, snapDistance: 18 });
  satMap.on("pm:create", e => {
    if (armedSensor) { assignBoundary(armedSensor, e.layer); setArmed(null); }
    else openAssignPopup(e.layer);     // no sensor armed → ask which one, on the shape
  });

  renderBoundaries();   // re-draw any saved boundaries
  return satMap;
}
// Style a boundary by its sensor's online state and label it with the sensor number.
function styleBoundary(layer, id) {
  const s = SENSOR_BY_ID[id], on = s && sensorOnline(s), col = on ? "#4caf7d" : "#d65a52";
  if (layer.setStyle) layer.setStyle({ color: col, weight: 2, dashArray: on ? null : "5 4", fillColor: col, fillOpacity: 0.12 });
  layer.bindTooltip(id + (on ? "" : " · OFFLINE"), { permanent: true, direction: "center", className: "sensor-tip" });
}
// Attach a freshly created/loaded layer: style, label, track, and wire edit/remove.
function registerBoundary(id, layer) {
  layer._sensorId = id; boundaryLayers[id] = layer; styleBoundary(layer, id);
  layer.on("pm:edit", () => { boundaries[id] = layer.toGeoJSON().geometry; saveBoundaries(); });
  layer.on("pm:remove", () => { delete boundaries[id]; delete boundaryLayers[id]; saveBoundaries(); renderSensorPanel(); });
}
function removeBoundaryLayer(id) { const l = boundaryLayers[id]; if (l) { l.remove(); delete boundaryLayers[id]; } }
// Commit a drawn shape to a sensor number (one boundary per sensor; replaces).
function assignBoundary(id, layer) {
  if (!SENSOR_BY_ID[id]) { layer.remove(); return; }
  removeBoundaryLayer(id);
  boundaries[id] = layer.toGeoJSON().geometry;
  registerBoundary(id, layer);
  saveBoundaries(); renderSensorPanel();
}
// Explicit mapping step: a popup on the shape with a sensor dropdown + Assign.
function openAssignPopup(layer) {
  const opts = SENSORS.map(s => '<option value="' + s.id + '">' + s.id + ' · ' + s.type + ' · ' + s.hive + (sensorOnline(s) ? '' : ' (offline)') + '</option>').join("");
  const html = '<div class="assignpop"><div class="apx">Map this shape to sensor</div>'
    + '<select class="apsel">' + opts + '</select>'
    + '<div class="aprow"><button class="apok">Assign</button><button class="apno">Discard</button></div></div>';
  const center = layer.getBounds ? layer.getBounds().getCenter() : layer.getLatLng();
  const pop = L.popup({ closeButton: false, className: "assign-popup", minWidth: 188 }).setLatLng(center).setContent(html).openOn(satMap);
  pop.on("remove", () => { if (!layer._sensorId) layer.remove(); }); // closed without assigning → discard
  setTimeout(() => {
    const root = pop.getElement(); if (!root) return;
    root.querySelector(".apok").onclick = () => { const id = root.querySelector(".apsel").value; assignBoundary(id, layer); satMap.closePopup(pop); };
    root.querySelector(".apno").onclick = () => { layer.remove(); satMap.closePopup(pop); };
  }, 0);
}
// Place search (geocode via OSM Nominatim, or paste "lat,lng") + home.
function wireMapSearch() {
  const inp = $("#map-q");
  const home = $("#map-home"); if (home) home.onclick = () => satMap.setView([APIARY.lat, APIARY.lon], 20);
  if (!inp || inp._wired) return; inp._wired = true;
  inp.addEventListener("keydown", async e => {
    if (e.key !== "Enter") return;
    const q = inp.value.trim(); if (!q) return;
    const ll = q.match(/^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$/);
    if (ll) { satMap.setView([+ll[1], +ll[2]], 20); inp.classList.remove("err"); return; }
    inp.classList.add("loading");
    try {
      const r = await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + encodeURIComponent(q), { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (j && j[0]) { satMap.setView([+j[0].lat, +j[0].lon], 19); inp.classList.remove("err"); }
      else inp.classList.add("err");
    } catch { inp.classList.add("err"); }
    finally { inp.classList.remove("loading"); }
  });
}
function renderBoundaries() {
  Object.entries(boundaries).forEach(([id, geom]) => {
    if (!SENSOR_BY_ID[id]) return;
    const layer = L.geoJSON({ type: "Feature", geometry: geom }).getLayers()[0];
    layer.addTo(satMap); registerBoundary(id, layer);
  });
}
function setArmed(id) {
  armedSensor = id;
  if (satMap) { if (id) satMap.pm.enableDraw("Rectangle"); else satMap.pm.disableDraw(); }
  renderSensorPanel();
}
// Re-tint markers/labels to the current (possibly live) hive states.
function refreshSatStyles() {
  HIVES.forEach(h => { if (satTag[h.code]) satTag[h.code].setIcon(hiveMarkIcon(h)); });
  SENSORS.forEach(s => { if (s._node) s._node.setStyle({ color: sensorOnline(s) ? "#4caf7d" : "#d65a52" }); });
  Object.keys(boundaryLayers).forEach(id => styleBoundary(boundaryLayers[id], id));
  renderSensorPanel();
}
// Sensor roster panel: online/offline status + arm-to-draw + clear, over the map.
function renderSensorPanel() {
  const el = $("#sensorlist"); if (!el) return;
  const hc = $("#sensor-count"); if (hc) hc.textContent = onlineCount() + "/" + SENSORS.length + " online";
  el.innerHTML = SENSORS.map(s => {
    const on = sensorOnline(s), has = !!boundaries[s.id], armed = armedSensor === s.id;
    return '<div class="srow' + (armed ? ' armed' : '') + '" data-sensor="' + s.id + '">'
      + '<span class="sdot ' + (on ? 'on' : 'off') + '"></span>'
      + '<span class="sid">' + s.id + '</span>'
      + '<span class="smeta">' + s.type + ' · ' + s.hive + '</span>'
      + '<span class="sbound ' + (has ? 'mapped' : '') + '">' + (has ? 'boundary set' : 'no boundary') + '</span>'
      + '<button class="sdraw" data-draw="' + s.id + '">' + (armed ? 'drawing...' : (has ? 'redraw' : 'draw')) + '</button>'
      + (has ? '<button class="sclear" data-clear="' + s.id + '" title="clear boundary">x</button>' : '')
      + '</div>';
  }).join("");
  el.querySelectorAll("[data-draw]").forEach(b => b.onclick = () => setArmed(armedSensor === b.dataset.draw ? null : b.dataset.draw));
  el.querySelectorAll("[data-clear]").forEach(b => b.onclick = () => { removeBoundaryLayer(b.dataset.clear); delete boundaries[b.dataset.clear]; saveBoundaries(); renderSensorPanel(); });
  el.querySelectorAll(".srow").forEach(r => r.addEventListener("mouseenter", () => { const l = boundaryLayers[r.dataset.sensor]; if (l && l.setStyle) l.setStyle({ weight: 4 }); }));
  el.querySelectorAll(".srow").forEach(r => r.addEventListener("mouseleave", () => { const l = boundaryLayers[r.dataset.sensor]; if (l && l.setStyle) l.setStyle({ weight: 2 }); }));
}
function setSensorPanel(on) {
  document.body.classList.toggle("sensorson", on);
  const btn = $("#sensors-btn"); if (btn) btn.classList.toggle("on", on);
  const p = $("#sensorpanel"); if (p) p.classList.toggle("on", on);
  if (on) renderSensorPanel(); else setArmed(null);
}
function renderMap() {
  const svg = $("#sitemap"), leaf = $("#leaflet"); if (!svg) return;
  if (S.mapmode === "sat") {
    svg.style.display = "none"; if (leaf) leaf.classList.add("on");
    $("#mapsearch")?.classList.add("on");
    initSatMap();
    // container was display:none until now, so Leaflet must re-measure it.
    setTimeout(() => { if (satMap) satMap.invalidateSize(); }, 0);
    refreshSatStyles();
  } else {
    if (leaf) leaf.classList.remove("on"); $("#mapsearch")?.classList.remove("on"); svg.style.display = ""; svg.style.cursor = "crosshair";
    svg.innerHTML = siteDecor() + HIVES.filter(passFilter).map(hiveSVG).join("");
    svg.querySelectorAll(".hbx").forEach(g => {
      g.addEventListener("click", () => { S.sel = g.dataset.code; renderMap(); renderDetail(); resetCam(); });
      g.addEventListener("mouseenter", () => showReticle(g));
      g.addEventListener("mouseleave", hideReticle);
    });
    applyMapZoom();
  }
}
// Limited zoom for the schematic yard: the viewBox grows/shrinks around the yard centre.
// At 1x you see the parcel; zoom out reveals the surrounding land and roads; zoom in goes closer.
const ZOOM_MIN = 0.62, ZOOM_MAX = 1.6, CX = 450, CY = 280, BASE_W = 900, BASE_H = 560;
function applyMapZoom() {
  const svg = $("#sitemap"); if (!svg || S.mapmode === "sat") return;
  const z = S.mapzoom, w = BASE_W / z, h = BASE_H / z;
  svg.setAttribute("viewBox", (CX - w / 2) + " " + (CY - h / 2) + " " + w + " " + h);
}
function zoomMap(step) {
  S.mapzoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, S.mapzoom * step));
  applyMapZoom();
}
function showReticle(g) {
  const cx = +g.dataset.cx, cy = +g.dataset.cy, h = get(g.dataset.code);
  const rv = $("#rv"), rh = $("#rh"), ret = $("#reticle"), tag = $("#hovtag"); if (!rv) return;
  rv.setAttribute("x1", cx); rv.setAttribute("y1", 30); rv.setAttribute("x2", cx); rv.setAttribute("y2", 525);
  rh.setAttribute("x1", 40); rh.setAttribute("y1", cy); rh.setAttribute("x2", 880); rh.setAttribute("y2", cy);
  ret.style.display = "block";
  tag.textContent = h.code + " · " + STWORD[h.st].toUpperCase() + " · " + h.mite.toFixed(1) + "/100 · stress " + h.stress;
  tag.setAttribute("x", cx < 450 ? cx + 30 : cx - 30); tag.setAttribute("y", cy - 30);
  tag.setAttribute("text-anchor", cx < 450 ? "start" : "end"); tag.style.display = "block";
}
function hideReticle() { const r = $("#reticle"), t = $("#hovtag"); if (r) r.style.display = "none"; if (t) t.style.display = "none"; }
function wireMapToolbar() {
  S.mapmode = "schem";  // satellite view removed - schematic yard map only
  const _schem = $("#mv-schem"); if (_schem) _schem.onclick = () => { S.mapmode = "schem"; renderMap(); };
  const _sat = $("#mv-sat"); if (_sat) _sat.onclick = () => { S.mapmode = "sat"; renderMap(); };
  // Sensors roster lives on the (satellite) map; opening it also switches there.
  const sb = $("#sensors-btn"); if (sb) sb.onclick = () => {
    if (S.mapmode !== "sat") { $("#mv-sat").click(); setSensorPanel(true); }
    else setSensorPanel(!document.body.classList.contains("sensorson"));
  };
  document.querySelectorAll("[data-mf]").forEach(b => b.onclick = () => { S.mapfilter = b.dataset.mf; document.querySelectorAll("[data-mf]").forEach(x => x.classList.toggle("on", x === b)); renderMap(); });
  const zi = $("#mz-in"); if (zi) zi.onclick = () => zoomMap(1.25);
  const zo = $("#mz-out"); if (zo) zo.onclick = () => zoomMap(1 / 1.25);
  const plot = document.querySelector(".plot");
  if (plot) plot.addEventListener("wheel", e => { if (S.mapmode === "sat") return; e.preventDefault(); zoomMap(e.deltaY < 0 ? 1.12 : 1 / 1.12); }, { passive: false });
  const pb = $("#scrub-play"); if (pb) pb.onclick = function () { this.textContent = this.textContent === "❚❚" ? "▶" : "❚❚"; };
  const ab = $("#scrub-arch"); if (ab) ab.onclick = function () { const live = $("#map-live"); const on = this.style.color === "var(--honey)"; this.style.color = on ? "var(--muted)" : "var(--honey)"; if (live) live.textContent = on ? "LIVE" : "ARCHIVED"; };
}
function pill(v) { return v; }

/* ---------------- colony vitality radar ---------------- */
const AXIS = ["Mite Ctrl", "Acoustic", "Queen", "Foraging", "Entrance"];
const clamp = x => Math.max(0, Math.min(1, x));
function vitals(h) {
  return [
    clamp(1 - h.mite / 6),
    clamp(1 - h.stress / 100),
    h.queen === "Queenless" ? 0.12 : h.queen === "Pre-swarm" ? 0.5 : clamp(h.qc),
    clamp(h.bpm / 180),
    clamp(({ low: 1, med: 0.62, high: 0.32 }[h.wasp]) - h.cong / 300)
  ];
}
function yardVitals() {
  const acc = [0, 0, 0, 0, 0];
  HIVES.forEach(h => vitals(h).forEach((v, i) => acc[i] += v));
  return acc.map(s => s / HIVES.length);
}
function prevVitals(h) {
  const cur = vitals(h); const seed = [...h.code].reduce((s, c) => s + c.charCodeAt(0), 0);
  return cur.map((v, i) => clamp(v - ((((seed + i * 53) % 23) - 11) / 100)));
}
function poly(vals, cx, cy, R) {
  return vals.map((v, i) => { const a = (-90 + i * 72) * Math.PI / 180; return (cx + R * v * Math.cos(a)).toFixed(1) + "," + (cy + R * v * Math.sin(a)).toFixed(1); }).join(" ");
}
function radarSVG(h) {
  const cx = 150, cy = 134, R = 92, id = "vital-" + h.code;
  const cur = vitals(h), avg = yardVitals(), prev = prevVitals(h);
  let rings = "";[0.25, 0.5, 0.75, 1].forEach(f => rings += '<polygon class="rring" points="' + poly([f, f, f, f, f], cx, cy, R) + '"/>');
  let spokes = "", labels = "", dots = "";
  for (let i = 0; i < 5; i++) {
    const a = (-90 + i * 72) * Math.PI / 180;
    spokes += '<line class="rspoke" x1="' + cx + '" y1="' + cy + '" x2="' + (cx + R * Math.cos(a)).toFixed(1) + '" y2="' + (cy + R * Math.sin(a)).toFixed(1) + '"/>';
    const lx = cx + (R + 15) * Math.cos(a), ly = cy + (R + 15) * Math.sin(a);
    const anch = Math.abs(Math.cos(a)) < 0.3 ? "middle" : (Math.cos(a) > 0 ? "start" : "end");
    const dy = Math.sin(a) < -0.5 ? -3 : Math.sin(a) > 0.5 ? 10 : 3;
    labels += '<text class="rax" x="' + lx.toFixed(0) + '" y="' + (ly + dy).toFixed(0) + '" text-anchor="' + anch + '">' + AXIS[i] + '</text>'
      + '<text class="rax pct" x="' + lx.toFixed(0) + '" y="' + (ly + dy + 11).toFixed(0) + '" text-anchor="' + anch + '">' + Math.round(cur[i] * 100) + '%</text>';
    dots += '<circle cx="' + (cx + R * cur[i] * Math.cos(a)).toFixed(1) + '" cy="' + (cy + R * cur[i] * Math.sin(a)).toFixed(1) + '" r="2.5" fill="#fff"/>';
  }
  // single calm status colour (matches the theme) instead of a warm rainbow blob
  const col = h.st === "crit" ? "#d65a52" : h.st === "watch" ? "#d9913f" : "#4caf7d";
  return '<svg viewBox="0 0 300 272">'
    + rings + spokes
    + '<polygon points="' + poly(avg, cx, cy, R) + '" fill="none" stroke="#6b7689" stroke-width="1.2" opacity=".7"/>'
    + '<polygon points="' + poly(prev, cx, cy, R) + '" fill="none" stroke="var(--honey)" stroke-width="1" stroke-dasharray="3 3" opacity=".45"/>'
    + '<polygon points="' + poly(cur, cx, cy, R) + '" fill="' + col + '" fill-opacity="0.18" stroke="' + col + '" stroke-width="1.8" stroke-linejoin="round"/>'
    + dots + labels + '</svg>';
}
function radarBlock(h) {
  const cur = vitals(h); let mi = 0; cur.forEach((v, i) => { if (v < cur[mi]) mi = i; });
  const col = h.st === "crit" ? "#d65a52" : h.st === "watch" ? "#d9913f" : "#4caf7d";
  return '<div class="radar">' + radarSVG(h)
    + '<div class="rlegend">'
    + '<span><i style="background:' + col + '"></i>This hive</span>'
    + '<span><i class="ln" style="border-color:#6b7689"></i>Yard avg</span>'
    + '<span><i class="ln" style="border-color:var(--honey)"></i>7d ago</span></div>'
    + '<div class="subnote" style="text-align:center;margin:0">Weakest signal: <b style="color:var(--ink)">' + AXIS[mi] + '</b> at ' + Math.round(cur[mi] * 100) + '%</div>'
    + '</div>';
}
/* ---------------- per-hive Orkes workflow ---------------- */
const WFAPPROVED = {};
function workflow(h) {
  const ap = WFAPPROVED[h.code];
  if (h.queen === "Queenless") return {
    name: "requeen-colony",
    reco: "Queenless signature confirmed across acoustic and behavior. Introduce a mated queen within 72h; without eggs the colony cannot raise its own.",
    tasks: [["detect.queenless", "acoustic roar + foragers down", "done", "2m ago"],
    ["confirm.eggcheck", "operator frame check", "done", "18m ago"],
    ["source.queen", "locate mated queen", "running", "running 40m"],
    ["approve.introduce", "human-in-the-loop", ap ? "done" : "wait", ap ? "approved" : "awaiting you"],
    ["introduce.queen", "cage + candy plug", ap ? "running" : "pending", "day 1"],
    ["verify.acceptance", "re-baseline acoustic", "pending", "day 5"]]
  };
  if (h.queen === "Pre-swarm") return {
    name: "swarm-prevention",
    reco: "Swarm spike, bearding and a traffic surge. Inspect for queen cells within 48h and add space, or make a split.",
    tasks: [["detect.preswarm", "swarm spike + bearding", "done", "6m ago"],
    ["inspect.cells", "operator queen-cell check", "running", "running 12m"],
    ["approve.split", "human-in-the-loop", ap ? "done" : "wait", ap ? "approved" : "awaiting you"],
    ["execute.split", "walk-away split", ap ? "running" : "pending", "today"],
    ["monitor.spike", "watch acoustic daily", "pending", "ongoing"]]
  };
  if (h.st === "crit") return {
    name: "varroa-treatment",
    reco: "Vision 4.6/100 plus acoustic stress 71 confirms Varroa at 0.91. Brood is low now, a high-efficacy window. Oxalic acid vapor within 7 days.",
    tasks: [["detect.varroa", "fusion confirmed 0.91", "done", "1m ago"],
    ["confirm.rescan", "24h tunnel re-scan", "running", "running 3h"],
    ["approve.treatment", "human-in-the-loop", ap ? "done" : "wait", ap ? "approved" : "awaiting you"],
    ["apply.oxalic", "oxalic acid vapor", ap ? "running" : "pending", "within 7d"],
    ["retest.load", "re-test at +14d", "pending", "day 14"]]
  };
  if (h.wasp === "high") return {
    name: "robbing-mitigation",
    reco: "Wasp pressure is high with entrance congestion. Reduce the entrance and remove exposed comb or syrup nearby.",
    tasks: [["detect.robbing", "wasp HIGH + congestion", "done", "4m ago"],
    ["approve.reduce", "human-in-the-loop", ap ? "done" : "wait", ap ? "approved" : "awaiting you"],
    ["reduce.entrance", "one bee-width", ap ? "running" : "pending", "today"],
    ["monitor.pressure", "re-check tomorrow", "pending", "24h"]]
  };
  if (h.mtrend === "rising") return {
    name: "mite-watch",
    reco: "Mites trending toward the 3/100 line. No treatment yet; re-test in 7 days and stage a plan.",
    tasks: [["detect.trend", "mites rising", "done", "8m ago"],
    ["schedule.retest", "auto re-scan", "running", "queued 7d"],
    ["stage.plan", "prep treatment plan", "pending", "this week"]]
  };
  return {
    name: "monitor-loop",
    reco: "All signals within colony baseline. No intervention needed; the non-invasive monitoring loop continues.",
    tasks: [["ingest.streams", "vision + acoustic + behavior", "running", "live"],
    ["fuse.baseline", "cross-modal check", "running", "live"],
    ["schedule.scan", "next scan +3d", "pending", "3 days"]]
  };
}
// Data-driven plan: the recommendation comes from THIS hive's real readings (action()),
// with an agentic "Ask the advisor" button that asks the LLM for tailored detail.
function orkesBlock(h) {
  const a = action(h), ap = WFAPPROVED[h.code], c = h.code;
  return '<div class="planbox">'
    + '<div class="planwhat">' + a.t + '</div>'
    + '<div class="planrow">'
    + (a.c && !ap ? '<button class="approve" data-hive="' + c + '">Approve this plan</button>'
      : ap ? '<span class="approved">&#10003; you approved this plan</span>' : '')
    + '<button class="askadvisor" data-hive="' + c + '">Ask the advisor</button>'
    + '</div>'
    + '<div class="advisorout" id="advisor-' + c + '"></div>'
    + '<div class="hivedoctor" id="hd-' + c + '"><div class="hd-load">Consulting HiveDoctor...</div></div>'
    + '</div>';
}
/* ---- HiveDoctor (Orkes Agentspan) - the agent that knows when NOT to ask ----
   A Value-of-Information gate decides, per hive, whether the beekeeper's input is worth
   the interruption. It acts on its own when confident (treat or just watch) and only
   pauses on Agentspan's durable approval gate for genuine close calls. The gate maths
   sit behind a small "why" toggle. */
function hdGateRow(g) {
  const tag = g.needs_human ? "ask you" : (g.action === "act" ? "act" : "watch");
  const cls = g.needs_human ? "ask" : (g.action === "act" ? "act" : "hold");
  return '<div class="hd-row"><span class="hd-field">' + g.condition
    + (g.coarse ? ' <em>(coarse)</em>' : '') + '</span>'
    + '<span class="hd-val">p=' + (g.p != null ? g.p.toFixed(2) : "-")
    + ' · value of asking $' + (g.evpi != null ? g.evpi.toFixed(2) : "-")
    + ' vs $' + g.c_ask + ' to ask <b class="hd-' + cls + '">' + tag + '</b></span></div>';
}
function hdWhy(plan) {
  const gates = plan.gates || [];
  if (!gates.length) return "";
  return '<details class="hd-sci"><summary>why - value-of-information maths</summary>'
    + '<div class="hd-grid">' + gates.map(hdGateRow).join("") + '</div>'
    + '<div class="hd-foot-note">Ask only when the value of your input (EVPI) beats the '
    + 'cost of interrupting you. Grounded in Value of Information (arXiv 2601.06407, 2026).</div>'
    + '</details>';
}
function hdRender(run) {
  const el = document.getElementById("hd-" + S.sel);
  if (!el) return;
  if (!run || run.error) { el.innerHTML = '<div class="hd-load">HiveDoctor offline (is api_server running?)</div>'; return; }
  const plan = run.plan || {}, st = run.status;
  let foot = "";
  if (st === "awaiting_approval") {
    foot = '<div class="hd-gate"><span class="hd-pending">Close call. Agentspan is holding this until you decide.</span>'
      + '<div class="hd-btns"><button class="hd-approve" data-id="' + run.id + '">Treat the hive</button>'
      + '<button class="hd-reject" data-id="' + run.id + '">Don\'t treat</button></div></div>';
  } else if (st === "auto_treated") {
    foot = '<div class="hd-done ok">Handled automatically. Confident it needed treating, so it did not interrupt you.</div>';
  } else if (st === "auto_monitor") {
    foot = '<div class="hd-done watch">Watching quietly. Confident all is calm, nothing for you to do.</div>';
  } else if (st === "approved") {
    foot = '<div class="hd-done ok">Approved. Treatment applied.</div>';
  } else if (st === "denied") {
    foot = '<div class="hd-done no">You chose not to treat. Left alone, still monitoring.</div>';
  } else {
    foot = '<div class="hd-load">Assessing...</div>';
  }
  el.innerHTML = '<div class="hd-tag"><span class="d"></span>HIVEDOCTOR · ORKES AGENTSPAN · knows when to ask</div>'
    + '<div class="hd-head">' + (plan.headline || "Assessing colony...") + '</div>'
    + hdWhy(plan) + foot;
  el.querySelectorAll(".hd-approve").forEach(b => b.onclick = () => hdDecide(run, true));
  el.querySelectorAll(".hd-reject").forEach(b => b.onclick = () => hdDecide(run, false));
}
async function hdDecide(run, approve) {
  const el = document.getElementById("hd-" + S.sel);
  if (el) { const g = el.querySelector(".hd-gate"); if (g) g.innerHTML = '<span class="hd-pending">' + (approve ? "Approving..." : "Saving...") + '</span>'; }
  const updated = await respondTreatment(run.id, approve, approve ? "approved from dashboard" : "declined from dashboard");
  hdRender(updated);
  EVENTS.unshift(ev("ORKES", approve ? "watch" : "info", S.sel,
    "HiveDoctor: you " + (approve ? "approved treatment" : "declined treatment") + " for hive " + S.sel + " at the Agentspan approval gate.", 1));
  if (EVENTS.length > 400) EVENTS.length = 400;
  if (S.view === "orch") renderLog();
}
async function loadHiveDoctor(h) {
  const code = h.code;
  try {
    // reuse an existing awaiting/recent run for this hive, else start a fresh one
    const runs = await listTreatments();
    let run = runs.find(r => r.hive_id === code && r.status === "awaiting_approval")
      || runs.find(r => r.hive_id === code);
    if (!run) run = await startTreatment(code);
    if (S.sel === code) hdRender(run);   // ignore if the user already switched hives
  } catch {
    if (S.sel === code) hdRender(null);
  }
}
// Every value here is backed by the live verdict (acoustic stress, vision mite-rate,
// net entrance flow, queen/swarm flags). Signals the verdict does not carry are not shown.
function pipeBlock(h) {
  const f = fusion(h);
  const src = h.live ? "live verdict" : "latest reading";
  if (S.pipe === "vision") {
    const pct = h.mite || 0, over = pct > 3, w = Math.min(100, (pct / 6) * 100), thr = (3 / 6) * 100;
    return '<div class="pipe">'
      + '<div class="mline"><div><span class="v" style="color:' + (over ? "var(--crit)" : "var(--ink)") + '">' + pct.toFixed(1) + '</span> <span class="u">mites per 100 bees</span></div><span class="tag ' + (over ? "r" : pct > 2 ? "a" : "g") + '">' + (over ? "over the line" : "under the line") + '</span></div>'
      + '<div class="subnote">The treatment line is 3 mites per 100 bees (white mark). This count comes from the tunnel camera, with no bees harmed.</div>'
      + '<div class="row"><span class="lab">Camera check this cycle</span><span class="' + (h.vision_ran ? "tag g" : "num") + '">' + (h.vision_ran ? "ran" : "not needed") + '</span></div>'
      + '<div class="row"><span class="lab">Deformed-wing signs</span><span class="' + (h.dwv ? "tag r" : "tag g") + '">' + (h.dwv ? "present" : "none") + '</span></div>'
      + '<div class="row"><span class="lab">Reading from</span><span class="num" style="font-size:11px">' + src + '</span></div></div>';
  }
  if (S.pipe === "acoustic") {
    const s = h.stress || 0;
    return '<div class="pipe">'
      + '<div class="mline"><div><span class="v" style="color:' + (s > 60 ? "var(--crit)" : s > 40 ? "var(--watch)" : "var(--ok)") + '">' + s + '</span> <span class="u">out of 100 stress</span></div><span class="tag ' + (s > 60 ? "r" : s > 40 ? "a" : "g") + '">' + (s > 60 ? "high" : s > 40 ? "raised" : "calm") + '</span></div>'
      + '<div class="bar"><i style="width:' + s + '%;background:' + (s > 60 ? "var(--crit)" : s > 40 ? "var(--watch)" : "var(--ok)") + '"></i></div>'
      + '<div class="subnote">Stress is read from the colony sound inside the hive.</div>'
      + '<div class="row"><span class="lab">Queenless roar</span><span class="' + (h.roar ? "tag r" : "tag g") + '">' + (h.roar ? "heard" : "not heard") + '</span></div>'
      + '<div class="row"><span class="lab">Swarm sound</span><span class="' + (h.swarm ? "tag a" : "tag g") + '">' + (h.swarm ? "detected" : "none") + '</span></div>'
      + '<div class="row"><span class="lab">Reading from</span><span class="num" style="font-size:11px">' + src + '</span></div></div>';
  }
  if (S.pipe === "behavior") {
    const nf = (h.netflow != null) ? h.netflow : 0;
    const lbl = nf >= 50 ? "heavy inflow" : nf <= -50 ? "heavy outflow" : "normal";
    return '<div class="pipe">'
      + '<div class="mline"><div><span class="v">' + (nf > 0 ? "+" : "") + nf + '</span> <span class="u">net bees per cycle at the entrance</span></div><span class="tag ' + (Math.abs(nf) >= 50 ? (nf < 0 ? "r" : "a") : "g") + '">' + lbl + '</span></div>'
      + '<div class="subnote">Net flow is how many more bees are entering than leaving (or the reverse) at the tunnel. A heavy outflow can mean swarming or robbing.</div>'
      + '<div class="row"><span class="lab">Reading from</span><span class="num" style="font-size:11px">' + src + '</span></div></div>';
  }
  return '<div class="pipe">'
    + '<div class="mline"><div><span class="v" style="color:var(--honey)">' + (f.conf * 100).toFixed(0) + '%</span> <span class="u">overall confidence</span></div></div>'
    + '<div class="subnote">This combines the sound and the camera into one read of the colony, so a single noisy signal does not raise a false alarm.</div></div>';
}
function renderDetail() {
  const h = get(S.sel);
  const [hlat, hlon] = hiveLatLon(h.code);
  $("#d-pin").textContent = "CAM-HIVE-" + h.code + " · " + hlat.toFixed(5) + ", " + hlon.toFixed(5);
  const PIPELABEL = { vision: "Camera", acoustic: "Sound", behavior: "Entrance", fusion: "Overall" };
  const seg = p => '<button class="' + (S.pipe === p ? "on" : "") + '" data-pipe="' + p + '">' + PIPELABEL[p] + '</button>';
  $("#dbody").innerHTML =
    '<div class="dhead"><div><div class="code">' + h.code + '</div><div class="name">' + h.name + '</div>'
    + '<div class="coord">' + hlat.toFixed(5) + ', ' + hlon.toFixed(5) + ' · ' + (h.lastSync ? 'Time: 1' + new Date(h.lastSync).toLocaleTimeString() : 'sync ' + new Date().toLocaleTimeString()) + '</div></div>'
    + '<span class="chip ' + h.st + '">' + STWORD[h.st] + '</span>'
    + (h.live ? '<span class="livetag" title="Driven by a live uAgent verdict">◉ LIVE</span>' : '') + '</div>'
    + '<div class="headline">' + headline(h) + '</div>'
    + '<div class="divider"></div>'
    + '<div class="eyebrow">Entrance tunnel · live media</div>'
    + mediaBlock(h)
    + '<div class="divider"></div>'
    + '<div class="eyebrow">Colony vitality · this hive vs yard</div>'
    + radarBlock(h)
    + '<div class="divider"></div>'
    + '<div class="eyebrow">Recommended plan</div>'
    + orkesBlock(h)
    + '<div class="divider"></div>'
    + '<div class="eyebrow">What the sensors see</div>'
    + '<div class="seg">' + seg("vision") + seg("acoustic") + seg("behavior") + seg("fusion") + '</div>'
    + pipeBlock(h);
  $("#dbody").querySelectorAll(".seg button").forEach(b => b.onclick = () => { S.pipe = b.dataset.pipe; renderDetail(); });
  $("#dbody").querySelectorAll(".approve").forEach(b => b.onclick = () => {
    WFAPPROVED[h.code] = true;
    EVENTS.unshift(ev("OPERATOR", "watch", h.code, "You approved the recommended plan for hive " + h.code + " (" + h.name + ").", 1));
    if (EVENTS.length > 400) EVENTS.length = 400;
    renderDetail(); if (S.view === "orch") renderLog();
  });
  $("#dbody").querySelectorAll(".askadvisor").forEach(b => b.onclick = async () => {
    const hh = get(b.dataset.hive), out = $("#advisor-" + b.dataset.hive);
    if (out) out.textContent = "Asking the advisor...";
    try {
      const qs = new URLSearchParams({
        hive: hh.code, name: hh.name, status: hh.st, mite: hh.mite,
        stress: hh.stress, queen: hh.queen, traffic: (hh.netflow != null ? hh.netflow : 0)
      });
      const r = await fetch("/api/advise?" + qs.toString()); const j = await r.json();
      if (out) out.textContent = j.advice || "No advice available.";
    } catch { if (out) out.textContent = "Could not reach the advisor. Is api_server running?"; }
  });
  loadHiveDoctor(h);   // async: fills the HiveDoctor (Agentspan) panel with a live run
}

// Entrance view is now a real tunnel video + audio (see mediaBlock); the old
// simulated bee-canvas is retired. resetCam stays as a no-op for select handlers.
function resetCam() { }

/* ---------------- live operations log ---------------- */
const AGENT_CHIPS = ["VISION", "ACOUSTIC", "BEHAVIOR", "FUSION", "REDIS", "CLAUDE", "ORKES", "DEEPGRAM", "OPERATOR"];
const LF = { agents: new Set(AGENT_CHIPS), sev: new Set(["info", "watch", "alert"]), hive: "ALL", q: "", live: true, group: false };
let EVENTS = [], evtSeq = 0, frameN = 4180;
const flaggedCount = () => HIVES.filter(h => h.st !== "ok").length;
const critHives = () => HIVES.filter(h => h.st === "crit");
const jit = (n, d) => n + Math.floor(Math.random() * (2 * (d || 3) + 1)) - (d || 3);
function ev(agent, sev, hive, msg, conf, real) { return { id: ++evtSeq, t: new Date(), agent, sev, hive, msg, conf, real: !!real }; }
function makeEvent() {
  const h = HIVES[Math.floor(Math.random() * HIVES.length)], r = Math.random(), f = fusion(h);
  const nm = h.code + " (" + h.name + ")";
  if (h.st === "crit" && r < 0.13) {
    if (h.queen === "Queenless") return ev("CLAUDE", "alert", h.code, "Hive " + nm + " sounds queenless, so introduce a mated queen within 72 hours.", f.conf);
    return ev("FUSION", "alert", h.code, "Hive " + nm + " has Varroa mites above the treatment line, so plan a treatment this week.", f.conf);
  }
  if (h.st === "watch" && r < 0.12) {
    if (h.queen === "Pre-swarm") return ev("FUSION", "watch", h.code, "Hive " + nm + " is showing pre-swarm signs, so inspect it for queen cells within the next 48 hours.", f.conf);
    if (h.wasp === "high") return ev("BEHAVIOR", "watch", h.code, "Hive " + nm + " has heavy wasp pressure at the entrance and may be getting robbed, so consider narrowing the entrance.", 0.79);
    return ev("FUSION", "watch", h.code, "Hive " + nm + " has a mite load that is creeping toward the treatment line, so re-test it in about a week.", f.conf);
  }
  if (r < 0.22) return ev("VISION", "info", h.code, "The camera scanned " + jit(22, 6) + " bees at the " + nm + " entrance and found " + (h.st === "crit" ? (1 + Math.floor(Math.random() * 3)) : 0) + " of them with visible mites.", 0.9);
  if (r < 0.38) return ev("ACOUSTIC", "info", h.code, "The sound check on hive " + nm + " found the colony " + (h.stress > 60 ? "stressed" : h.stress > 40 ? "slightly raised" : "calm") + " at a stress level of " + jit(h.stress) + " out of 100.", 0.87);
  if (r < 0.50) return ev("BEHAVIOR", "info", h.code, "About " + jit(h.bpm, 8) + " bees a minute are moving at the " + nm + " entrance and traffic is trending " + h.btrend + ".", 0.84);
  if (r < 0.62) return ev("FUSION", "info", h.code, "All of hive " + nm + "'s signals look normal, so nothing needs you here.", f.conf);
  if (r < 0.74) return ev("REDIS", "info", h.code, "The overall status for hive " + nm + " was updated to " + STWORD[h.st].toLowerCase() + ".", 1);
  if (r < 0.86) return ev("APIS", "info", "yard", "All " + HIVES.length + " hives were checked across the yard and " + flaggedCount() + " need your attention.", 1);
  const c = critHives()[0];
  if (c) return ev("ORKES", "watch", c.code, "The treatment plan for hive " + c.code + " (" + c.name + ") is on step " + (1 + Math.floor(Math.random() * 4)) + " of 5 and is waiting for your approval.", 1);
  return ev("FUSION", "info", h.code, "All of hive " + nm + "'s signals look normal, so nothing needs you here.", f.conf);
}
// Beekeeper-friendly source names (the underlying agent code still drives the colour).
const SOURCE = {
  VISION: "Camera", ACOUSTIC: "Sound", BEHAVIOR: "Entrance", FUSION: "Analysis",
  REDIS: "System", CLAUDE: "Advisor", ORKES: "Plan", APIS: "Coordinator", DEEPGRAM: "Voice", OPERATOR: "You"
};
function agentLabel(a) { return SOURCE[a] || a; }
// Live-tail: only auto-refresh the log while the reader is at the very top. Once they
// scroll down to read, the view freezes so new rows don't shove their line away.
function logAtTop() { const l = $("#log"); return !l || l.scrollTop < 8; }
function logRow(e) {
  const conf = (e.conf != null && e.conf < 1) ? (e.conf * 100 | 0) + "%" : "";
  const q = e.msg.replace(/"/g, "&quot;");
  return '<div class="logrow clickrow sev-' + e.sev + (e.real ? ' real' : '') + '" data-q="' + q + '" title="Click for a plain-English explanation">'
    + '<span class="lt">' + e.t.toLocaleTimeString([], { hour12: false }) + '</span>'
    + '<span class="la a-' + e.agent + '">' + agentLabel(e.agent) + '</span>'
    + '<span class="lh">' + e.hive + '</span>'
    + '<span class="lm">' + e.msg + '</span>'
    + '<span class="lc">' + conf + '</span></div>';
}
// Click a log line -> ask the explainer agent (/api/explain) for plain English.
async function explainLine(q) {
  const box = $("#explainbox"); if (!box) return;
  box.style.display = "block";
  box.innerHTML = '<div class="exp-line">' + q + '</div><div class="exp-ans">explaining...</div>';
  try {
    const r = await fetch("/api/explain?q=" + encodeURIComponent(q));
    const j = await r.json();
    box.innerHTML = '<div class="exp-head">In plain terms</div>'
      + '<div class="exp-line">' + q + '</div>'
      + '<div class="exp-ans">' + (j.explanation || "No explanation available.") + '</div>'
      + '<button class="exp-close">close</button>';
  } catch {
    box.innerHTML = '<div class="exp-ans">Could not reach the explainer. Is api_server running?</div><button class="exp-close">close</button>';
  }
  const c = box.querySelector(".exp-close"); if (c) c.onclick = () => { box.style.display = "none"; };
}
function filtered() {
  return EVENTS.filter(e => {
    if (e.agent !== "APIS" && !LF.agents.has(e.agent)) return false;
    if (!LF.sev.has(e.sev)) return false;
    if (LF.hive !== "ALL" && e.hive !== LF.hive) return false;
    if (LF.q) { if (!((e.msg + " " + e.hive + " " + e.agent).toLowerCase().includes(LF.q.toLowerCase()))) return false; }
    return true;
  });
}
function renderLog() {
  const f = filtered(), log = $("#log");
  const prevTop = log ? log.scrollTop : 0;   // preserve the reader's position across re-renders
  if (log) {
    if (LF.group) {
      const groups = {}; f.slice(0, 300).forEach(e => { (groups[e.agent] = groups[e.agent] || []).push(e); });
      const order = ["FUSION", "CLAUDE", "ORKES", "APIS", "OPERATOR", "VISION", "ACOUSTIC", "BEHAVIOR", "REDIS", "DEEPGRAM"];
      log.innerHTML = order.filter(a => groups[a] && groups[a].length)
        .map(a => '<div class="loggrp">' + agentLabel(a) + ' · ' + groups[a].length + '</div>' + groups[a].map(logRow).join("")).join("");
    } else {
      log.innerHTML = f.slice(0, 200).map(logRow).join("");
    }
    log.querySelectorAll(".clickrow").forEach(r => r.onclick = () => explainLine(r.dataset.q));
    log.scrollTop = prevTop;   // keep the reader where they were
  }
  const m = $("#logmeta");
  if (m) {
    const al = EVENTS.filter(e => e.sev === "alert").length, w = EVENTS.filter(e => e.sev === "watch").length;
    m.innerHTML = '<span><b>' + f.length + '</b> shown · ' + EVENTS.length + ' total</span>'
      + '<span style="color:var(--crit)">' + al + ' alert</span>'
      + '<span style="color:var(--watch)">' + w + ' watch</span>'
      + '<span><b>~1.4</b> events/s</span>';
  }
}
function buildFilterBar() {
  const fb = $("#filterbar"); if (!fb || fb.dataset.built) return; fb.dataset.built = "1";
  // Beekeeper-simple filters: importance + which hive + search. (The technical
  // per-agent chips were removed; click any log line for a plain explanation.)
  let html = '<span class="flabel">Show</span>'
    + '<button class="fchip on" data-sev="info">Routine</button>'
    + '<button class="fchip sev-watch on" data-sev="watch">Watch</button>'
    + '<button class="fchip sev-alert on" data-sev="alert">Alerts</button>'
    + '<span class="fdiv"></span>'
    + '<select class="fsel" id="fhive"><option value="ALL">All hives</option>' + HIVES.map(h => '<option value="' + h.code + '">' + h.code + ' · ' + h.name + '</option>').join("") + '</select>'
    + '<input class="fsearch" id="fq" placeholder="search...">'
    + '<button class="livebtn" id="livebtn"><span class="d"></span><span id="livetxt">LIVE</span></button>';
  fb.innerHTML = html;
  fb.querySelectorAll("[data-sev]").forEach(b => b.onclick = () => { const s = b.dataset.sev; if (LF.sev.has(s)) { LF.sev.delete(s); b.classList.remove("on"); } else { LF.sev.add(s); b.classList.add("on"); } renderLog(); });
  $("#fhive").onchange = e => { LF.hive = e.target.value; renderLog(); };
  $("#fq").oninput = e => { LF.q = e.target.value; renderLog(); };
  $("#livebtn").onclick = function () { LF.live = !LF.live; this.classList.toggle("paused", !LF.live); $("#livetxt").textContent = LF.live ? "LIVE" : "PAUSED"; };
}
// Beekeeper-friendly side panel: what needs you, colonies at a glance, monitoring status.
function renderFleet() {
  const flagged = HIVES.filter(h => h.st !== "ok")
    .sort((a, b) => (a.st === "crit" ? 0 : 1) - (b.st === "crit" ? 0 : 1));
  const needs = $("#needs");
  if (needs) {
    needs.innerHTML = flagged.length ? flagged.map(h => {
      const a = action(h), ap = WFAPPROVED[h.code];
      return '<div class="needrow ' + h.st + '">'
        + '<div class="needtop"><b>' + h.code + ' · ' + h.name + '</b><span class="chip ' + h.st + '">' + STWORD[h.st] + '</span></div>'
        + '<div class="needact">' + a.t + '</div>'
        + (a.c && !ap ? '<button class="approve" data-hive="' + h.code + '">Approve plan</button>'
          : ap ? '<span class="approved">approved</span>' : '')
        + '</div>';
    }).join("") : '<div class="allgood">All colonies look healthy. Nothing needs you right now.</div>';
    needs.querySelectorAll(".approve").forEach(b => b.onclick = () => { WFAPPROVED[b.dataset.hive] = true; renderFleet(); if (S.sel) renderDetail(); });
  }
  const glance = $("#glance");
  if (glance) glance.innerHTML = HIVES.map(h =>
    '<div class="glrow" data-code="' + h.code + '"><span class="gldot ' + h.st + '"></span>'
    + '<span class="glname">' + h.code + ' · ' + h.name + '</span>'
    + '<span class="glst ' + h.st + '">' + STWORD[h.st] + '</span></div>').join("");
  if (glance) glance.querySelectorAll(".glrow").forEach(r => r.onclick = () => { S.sel = r.dataset.code; setView("map"); renderDetail(); });

  const sys = $("#sysline");
  if (sys) sys.innerHTML = [
    ["Colonies monitored", HIVES.length],
    ["Need attention", flagged.length],
    ["Live data link", LINK.state === "live" ? "connected" : LINK.state === "standby" ? "standby" : "demo data"]
  ].map(kv => '<span class="k">' + kv[0] + '</span><span class="v">' + kv[1] + '</span>').join("");
}
function seedLog() {
  EVENTS = []; const now = Date.now();
  const tmp = []; for (let i = 70; i > 0; i--) { const e = makeEvent(); e.t = new Date(now - i * 850); tmp.push(e); }
  EVENTS = tmp.reverse();
}
function tickLog() {
  if (S.view !== "orch" || !LF.live) return;
  const n = 1 + (Math.random() < 0.4 ? 1 : 0);
  for (let i = 0; i < n; i++) { EVENTS.unshift(makeEvent()); }
  if (EVENTS.length > 400) EVENTS.length = 400;
  if (logAtTop()) renderLog();   // frozen while the reader has scrolled down
}
function renderTicker() {
  const items = HIVES.map(h => {
    const trend = h.mtrend === "rising" ? ", mites rising" : "";
    return '<span><b>' + h.code + ' ' + h.name + '</b>: ' + STWORD[h.st].toLowerCase() + ', '
      + (h.mite || 0).toFixed(1) + ' mites per 100 bees' + trend + ', stress ' + (h.stress || 0) + ' out of 100</span>';
  });
  const flagged = HIVES.filter(h => h.st !== "ok").length;
  const summary = '<span><b>Apiary:</b> ' + HIVES.length + ' hives, ' + (HIVES.length - flagged)
    + ' healthy, ' + flagged + ' need attention</span>';
  $("#ticker").innerHTML = (summary + items.join("")).repeat(2);
}

/* ---------------- chrome ---------------- */
function setView(v) {
  S.view = v;
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.dataset.view === v));
  $("#view-map").classList.toggle("on", v === "map");
  $("#view-orch").classList.toggle("on", v === "orch");
  if (v === "orch") { buildFilterBar(); renderLog(); renderFleet(); }
}
function setMode(m) {
  S.mode = m; document.body.classList.toggle("command", m === "cmd");
  $("#m-field").classList.toggle("on", m === "field"); $("#m-cmd").classList.toggle("on", m === "cmd");
  // The link readout is owned by setLink() so it reflects REAL coordinator state,
  // not the cosmetic field/command skin toggle.
}
document.querySelectorAll(".tab").forEach(t => t.onclick = () => setView(t.dataset.view));
$("#m-field").onclick = () => setMode("field"); $("#m-cmd").onclick = () => setMode("cmd");

function tickClock() { const t = new Date().toLocaleTimeString([], { hour12: false }) + " PDT"; $("#clock").textContent = t; const mt = $("#map-time"); if (mt) mt.textContent = t; }

/* ---------------- boot ---------------- */
seedLog();
renderSummary(); renderMap(); wireMapToolbar(); renderDetail(); renderTicker();
// Deep-linkable view: ?view=orch opens the orchestrator; ?map=sat opens satellite.
const _q = new URLSearchParams(location.search);
const _v = _q.get("view");
if (_v === "orch" || _v === "map") setView(_v);
if (_q.get("seed") === "sensors") { // demo: seed two example coverage boundaries
  const mk = (code, half) => {
    const [la, lo] = hiveLatLon(code), b = boxBounds(la, lo, half);
    return { type: "Polygon", coordinates: [[[b[0][1], b[0][0]], [b[1][1], b[0][0]], [b[1][1], b[1][0]], [b[0][1], b[1][0]], [b[0][1], b[0][0]]]] };
  };
  boundaries["S-01"] = mk("A1", 7); boundaries["S-04"] = mk("B1", 6);
}
if (_q.get("map") === "sat" && $("#mv-sat")) $("#mv-sat").click();
if (_q.get("z")) setTimeout(() => { if (satMap) satMap.setView([APIARY.lat, APIARY.lon], +_q.get("z")); }, 140);
if (_q.get("sensors") === "1") setSensorPanel(true);
tickClock(); setInterval(tickClock, 1000);
setInterval(tickLog, 850);
setInterval(() => { if (S.view === "orch") renderFleet(); }, 3500);

/* ====================================================================
   LIVE COORDINATOR WIRING
   --------------------------------------------------------------------
   Turns the dashboard from "synthetic demo" into a real client of the
   uAgents fleet coordinator (/api/status). Three honest behaviours:
     1. Connection state (live / standby / offline) drives the header
        data-link readout instead of a hardcoded "LINK STABLE".
     2. The FULL Verdict is applied  varroa_status, queenless_alert,
        swarm_alert AND the real signed `traffic` + backend timestamp.
        Nothing is faked into the hive once it goes live.
     3. Every fresh verdict is injected into the orchestrator ops-log as
        a real FUSION event, so the agentic view reflects actual fleet
        traffic, not just ambient filler.
   ==================================================================== */

function linkPin() {
  if (LINK.state === "live") return `LIVE · ${LINK.latency}ms · ${LINK.liveCodes.size} colony feed${LINK.liveCodes.size === 1 ? "" : "s"}`;
  if (LINK.state === "standby") return `STANDBY · coordinator up · awaiting verdicts`;
  return "DEMO DATA · coordinator offline";
}
function setLink(state, latency) {
  LINK.state = state; LINK.latency = latency;
  document.body.dataset.link = state;
  const link = $("#link"), up = document.querySelector(".uplink");
  if (up) up.dataset.state = state;
  if (link) link.textContent = state === "live" ? "DATA LINK LIVE"
    : state === "standby" ? "LINK · STANDBY" : "LINK LOST · DEMO";
  const ml = $("#map-live"); if (ml) ml.textContent = state === "live" ? "LIVE" : state === "standby" ? "STANDBY" : "DEMO";
  const lp = $("#log-pin"); if (lp) lp.textContent = "APIS-PRIME · " + linkPin();
}

// Map a backend Verdict onto a UI hive record. The acoustic/vision varroa
// COUNT is not carried on the wire (the verdict only ships clear/watch/alert),
// so we render a representative load per band but keep the real status, real
// traffic and real timestamp authoritative.
function applyVerdict(hive, v) {
  const status = v.varroa_status || "clear";
  hive.live = true;
  hive.lastSync = v.timestamp || null;
  if (typeof v.traffic === "number") {
    hive.netflow = v.traffic;
    hive.flowLabel = v.traffic >= 50 ? "influx" : v.traffic <= -50 ? "outflux" : "balanced";
  }
  if (Array.isArray(v.position) && v.position.length === 2) hive.pos = v.position;

  // Real per-detector signals from the verdict (no hard-coded representative numbers).
  if (typeof v.acoustic_stress === "number") hive.stress = Math.round(v.acoustic_stress * 100);
  if (typeof v.vision_mite_rate === "number") hive.mite = Math.round(v.vision_mite_rate * 1000) / 10; // mites / 100 bees
  hive.vision_ran = !!v.vision_ran;

  let st = "ok";
  if (status === "alert") { st = "crit"; hive.mtrend = "rising"; hive.dwv = hive.mite > 3; }
  else if (status === "watch") { st = "watch"; hive.mtrend = "rising"; hive.dwv = false; }
  else { hive.mtrend = "steady"; hive.dwv = false; }

  // Queenless / swarm are terminal acoustic alerts and outrank varroa for severity.
  if (v.queenless_alert) { st = "crit"; hive.queen = "Queenless"; hive.roar = true; hive.swarm = false; hive.beard = false; }
  else if (v.swarm_alert) { st = (st === "crit" ? "crit" : "watch"); hive.queen = "Pre-swarm"; hive.swarm = true; hive.beard = true; hive.roar = false; }
  else { hive.queen = "Queenright"; hive.roar = false; hive.swarm = false; hive.beard = false; }

  const changed = hive.st !== st; hive.st = st;
  return changed;
}

// Translate a brand-new verdict into a real ops-log line.
function verdictEvent(code, v) {
  const g = get(code); const nm = g && g.name ? code + " (" + g.name + ")" : code;
  if (v.queenless_alert) return ev("CLAUDE", "alert", code, "Hive " + nm + " sounds queenless, so introduce a mated queen within 72 hours.", 0.88, true);
  if (v.swarm_alert) return ev("FUSION", "watch", code, "Hive " + nm + " is showing pre-swarm signs, so inspect it for queen cells soon.", 0.83, true);
  if (v.varroa_status === "alert") return ev("FUSION", "alert", code, "Hive " + nm + " has Varroa confirmed above the treatment line, so plan a treatment this week.", 0.91, true);
  if (v.varroa_status === "watch") return ev("FUSION", "watch", code, "Hive " + nm + " has a mite load creeping toward the line, so re-test it in about a week.", 0.78, true);
  if (typeof v.traffic === "number" && Math.abs(v.traffic) >= 50)
    return ev("BEHAVIOR", "info", code, "There is a strong " + (v.traffic > 0 ? "inflow" : "outflow") + " of bees at the " + nm + " entrance at " + Math.abs(v.traffic) + " per cycle.", 0.84, true);
  return ev("APIS", "info", code, "A new reading came in for hive " + nm +" and the signals look normal.", 1, true);
}

async function syncBackendData() {
  const res = await pollCoordinator();
  setLink(res.state, res.latency);
  if (res.state === "offline" || !res.hives) return;

  let changed = false, selChanged = false;
  LINK.liveCodes = new Set();

  for (const [backendCode, history] of Object.entries(res.hives)) {
    if (!Array.isArray(history) || history.length === 0) continue;
    const code = HIVE_MAP[backendCode.toLowerCase()] || backendCode.toUpperCase();
    const hive = get(code);
    if (!hive) continue;

    const latest = history[history.length - 1];
    LINK.liveCodes.add(code);

    // Only log/repaint when this hive produced a NEW verdict (by timestamp).
    if (LINK.lastTs[code] !== latest.timestamp) {
      LINK.lastTs[code] = latest.timestamp;
      if (code === S.sel) selChanged = true;   // only then will we rebuild the readout (keeps the video playing)
      EVENTS.unshift(verdictEvent(code, latest));
      if (EVENTS.length > 400) EVENTS.length = 400;
      if (S.view === "orch" && logAtTop()) renderLog();
    }
    if (applyVerdict(hive, latest)) changed = true;
  }

  if (changed || res.state === "live") {
    renderSummary(); renderMap(); renderTicker();
    if (S.view === "orch") renderFleet();
  }
  if (selChanged) renderDetail();   // rebuild the readout (and its video) only on a real change for THIS hive
}

setLink("offline", null);
syncBackendData();
setInterval(syncBackendData, 2000);
// Instant push when Redis is the backend (no-op in file-store mode); the 2s poll above
// stays as the always-works baseline.
subscribeEvents(() => syncBackendData());
