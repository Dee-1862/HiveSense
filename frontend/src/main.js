import { pollCoordinator } from "./api.js";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";

/* ---------------- data ---------------- */
const HIVES = [
  {code:"A1", name:"Clover Stand", st:"ok",   mite:0.7, mtrend:"steady", scanned:412, mites:3,  queen:"Queenright", qc:0.97, stress:18, swarm:false, roar:false, bpm:142, btrend:"up", beard:false, wasp:"low",  cong:14, dwv:false, freq:"~310 Hz hum"},
  {code:"A2", name:"Manzanita",    st:"ok",   mite:1.2, mtrend:"steady", scanned:388, mites:5,  queen:"Queenright", qc:0.95, stress:24, swarm:false, roar:false, bpm:118, btrend:"steady", beard:false, wasp:"low", cong:21, dwv:false, freq:"~300 Hz hum"},
  {code:"A3", name:"Yarrow",       st:"watch",mite:2.7, mtrend:"rising", scanned:441, mites:12, queen:"Queenright", qc:0.93, stress:48, swarm:false, roar:false, bpm:96,  btrend:"down", beard:false, wasp:"med", cong:33, dwv:false, freq:"~330 Hz, broadening"},
  {code:"B1", name:"Sage Row",     st:"crit", mite:4.6, mtrend:"rising", scanned:506, mites:23, queen:"Queenright", qc:0.9,  stress:71, swarm:false, roar:false, bpm:74,  btrend:"down", beard:false, wasp:"low", cong:28, dwv:true,  freq:"~360 Hz stress band"},
  {code:"B2", name:"Honeysuckle",  st:"ok",   mite:0.9, mtrend:"steady", scanned:399, mites:4,  queen:"Queenright", qc:0.96, stress:20, swarm:false, roar:false, bpm:151, btrend:"up", beard:false, wasp:"low", cong:12, dwv:false, freq:"~305 Hz hum"},
  {code:"B3", name:"Lupine",       st:"watch",mite:1.4, mtrend:"steady", scanned:377, mites:5,  queen:"Pre-swarm",  qc:0.81, stress:58, swarm:true,  roar:false, bpm:188, btrend:"up", beard:true,  wasp:"low", cong:46, dwv:false, freq:"swarm spike ~250 Hz"},
  {code:"C1", name:"Buckwheat",    st:"crit", mite:1.0, mtrend:"steady", scanned:362, mites:4,  queen:"Queenless",  qc:0.88, stress:64, swarm:false, roar:true,  bpm:61,  btrend:"down", beard:false, wasp:"med", cong:19, dwv:false, freq:"queenless roar ~400 Hz"},
  {code:"C2", name:"Toyon",        st:"ok",   mite:1.1, mtrend:"steady", scanned:421, mites:5,  queen:"Queenright", qc:0.96, stress:22, swarm:false, roar:false, bpm:133, btrend:"steady", beard:false, wasp:"low", cong:18, dwv:false, freq:"~308 Hz hum"},
  {code:"C3", name:"Ceanothus",    st:"watch",mite:1.3, mtrend:"steady", scanned:390, mites:5,  queen:"Queenright", qc:0.94, stress:39, swarm:false, roar:false, bpm:88,  btrend:"down", beard:false, wasp:"high",cong:24, dwv:false, freq:"intrusion chatter"}
];
const STMAP={ok:"ok",watch:"watch",crit:"crit"};
const STWORD={ok:"Healthy",watch:"Watch",crit:"Action required"};

// per-hive plain-language headline + recommended action
function headline(h){
  if(h.queen==="Queenless") return "Colony has likely <b>lost its queen</b>. Acoustic roar plus a falling foragers count.";
  if(h.queen==="Pre-swarm")  return "Reading <b>pre-swarm</b>. Big traffic jump, bearding at the entrance, and a low-frequency swarm spike.";
  if(h.st==="crit")          return "<b>Mite load past the treatment line</b> with early deformed-wing signs. This colony needs help this week.";
  if(h.st==="watch" && h.wasp==="high") return "Healthy brood, but <b>wasp pressure is high</b> at the entrance. Robbing risk.";
  if(h.st==="watch" && h.mtrend==="rising") return "Mites are <b>trending up</b> toward the line. Worth a closer look soon.";
  if(h.st==="watch")         return "Mostly fine. One signal is drifting, so it is flagged for a look.";
  return "Strong colony. Mite load well under the line, queen present, steady traffic.";
}
function action(h){
  if(h.queen==="Queenless") return {k:"Recommended action",c:true,t:"Confirm queenlessness, then introduce a mated queen or a frame of young eggs within 72 hours. A queenless colony will not raise a new queen without eggs present."};
  if(h.queen==="Pre-swarm")  return {k:"Recommended action",c:false,t:"Inspect for capped queen cells within 48 hours. Add a super for space, or make a walk-away split to keep the colony and capture the swarm impulse."};
  if(h.st==="crit" && h.dwv) return {k:"Treat this week",c:true,t:"Mite load is 4.6 per 100 bees, above the 3 per 100 line. Brood is low right now, which is a high-efficacy window. Oxalic acid vapor or an approved miticide, then re-test in 14 days. Watch for more deformed wings."};
  if(h.wasp==="high")        return {k:"Recommended action",c:false,t:"Reduce the entrance to a single bee-width to help guards repel wasps. Remove nearby exposed comb or syrup that draws robbers."};
  if(h.mtrend==="rising")    return {k:"Watch closely",c:false,t:"Re-test mite load in 7 days. No treatment yet, but plan one if it crosses 3 per 100 bees."};
  return {k:"No action needed",c:false,t:"Keep on the normal inspection cadence. Next acoustic re-baseline in 3 days."};
}
function fusion(h){
  if(h.queen==="Queenless") return {conf:0.88, rule:"acoustic.roar=TRUE  +  behavior.foragers↓>30%  →  QUEENLESS", sig:["Acoustic colony worker","Behavior worker"]};
  if(h.queen==="Pre-swarm")  return {conf:0.83, rule:"acoustic.swarm_spike + behavior.bearding + traffic↑  →  PRE-SWARM", sig:["Acoustic colony worker","Behavior worker"]};
  if(h.st==="crit")          return {conf:0.91, rule:"vision.mite_pct>3.0  AND  acoustic.stress>65  →  VARROA CONFIRMED", sig:["Vision worker","Acoustic Varroa worker"]};
  if(h.wasp==="high")        return {conf:0.79, rule:"behavior.wasp=HIGH + entrance.congestion  →  ROBBING RISK", sig:["Behavior worker"]};
  return {conf:0.96, rule:"all signals within colony baseline  →  STABLE", sig:["Fusion core"]};
}

/* ---------------- state + render ---------------- */
const S={view:"map", sel:HIVES[3].code, pipe:"vision", mode:"field", mapmode:"schem", mapfilter:"all"};
const $=s=>document.querySelector(s);
const get=c=>HIVES.find(h=>h.code===c);

function renderSummary(){
  const crit=HIVES.filter(h=>h.st==="crit").length, watch=HIVES.filter(h=>h.st==="watch").length;
  const idx=Math.round(100 - (crit*16 + watch*6) - HIVES.reduce((a,h)=>a+h.mite,0)/HIVES.length*2);
  $("#s-health").textContent=idx; $("#s-health").style.color = idx>80?"var(--ok)":idx>65?"var(--watch)":"var(--crit)";
  $("#s-hives").textContent=HIVES.length;
  $("#s-alerts").textContent=crit+watch;
  $("#threat-txt").textContent="THREAT LEVEL: "+(crit?"ELEVATED":"NOMINAL")+" · "+crit+" CRITICAL · "+watch+" WATCH · OPS WINDOW 7d";
}
// organic layout: pallet clusters + a loose row, with slight per-hive rotation (viewBox 900x560)
const POS={
  A1:[235,180,-5], A2:[300,222,4], A3:[372,182,-3],
  B1:[610,205,6],  B2:[678,250,-4],
  B3:[470,320,2],
  C1:[240,408,-6], C2:[318,440,5], C3:[404,406,-2]
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
  // backdrop — legibility is a property of the markers, not the orbital imagery.
  lat: 38.5384, lon: -121.7884,
  bbox: [-121.78927, 38.53786, -121.78753, 38.53894], // [W,S,E,N] ~ the yard
};
// Realistic, irregular 3-row apiary. Per hive: [east_m, north_m, rotation_deg]
// from the yard centre. Spread ~45 m × 30 m so the (larger) markers don't collide.
const YARD_M_LAT = 110574, YARD_M_LON = 111320 * Math.cos(APIARY.lat * Math.PI / 180);
const YARD_LAYOUT = {
  A1:[-22,13,-4], A2:[-7,15,3], A3:[9,12,-2], B1:[23,14,5],
  B2:[-18,-2,2],  B3:[-2,0,-3], C1:[14,-3,4],
  C2:[-10,-15,-2], C3:[8,-13,3],
};
/* ---- Field sensor network ----
   One sensor node per hive (CAM / MIC / GATE), each with a number and an
   online flag. The operator draws each sensor's coverage boundary on the map and
   it is mapped to the sensor's number; boundaries persist in localStorage. */
const SENSORS = HIVES.map((h,i)=>({
  id:"S-"+String(i+1).padStart(2,"0"),
  type:["CAM","MIC","GATE"][i%3],
  hive:h.code,
  online: ![7,8].includes(i),  // S-08 (C2) + S-09 (C3) offline → no tunnel feed there
}));
const SENSOR_BY_ID = Object.fromEntries(SENSORS.map(s=>[s.id,s]));
// Live-coordinator link state (declared here so sensorOnline()/the sensor panel
// can read it during boot; the polling logic that mutates it lives at the bottom).
// Backend hive_id -> on-map UI code; extend as more supervisors come online.
const HIVE_MAP = { hive3: "A3", hive5: "B2" };
const LINK = { state: "offline", latency: null, lastTs: {}, liveCodes: new Set() };
// A sensor is online if its base flag says so, OR (in live mode) its hive is
// actively streaming verdicts from the coordinator.
function sensorOnline(s){ return s.online || (LINK.state==="live" && LINK.liveCodes.has(s.hive)); }
function onlineCount(){ return SENSORS.filter(sensorOnline).length; }

const SENSOR_KEY="hivesense.sensorBoundaries.v1";
function loadBoundaries(){ try{ return JSON.parse(localStorage.getItem(SENSOR_KEY))||{}; }catch{ return {}; } }
function saveBoundaries(){ try{ localStorage.setItem(SENSOR_KEY,JSON.stringify(boundaries)); }catch{} }
let boundaries=loadBoundaries();   // { sensorId: GeoJSON geometry }
let boundaryLayers={};             // { sensorId: Leaflet layer }
let armedSensor=null;              // sensor id currently being drawn for

/* ---- Per-hive tunnel video + entrance audio ----
   Real clips served from /media (public/). Videos are REUSED across hives (only 3
   tunnel recordings exist); audio is UNIQUE to each hive (no clip repeats). Seven
   hives have a live feed; the two whose sensor is offline (B1=S-04, C2=S-08) show
   no feed. No model/inference values are attached here — just raw playback. */
const MEDIA_BASE = "/media/";
const MEDIA = {
  A1:{video:"tunnel_free", audio:"ent_01"},
  A2:{video:"tunnel_inf1", audio:"ent_02"},
  A3:{video:"tunnel_inf2", audio:"ent_03"},
  B1:{video:"tunnel_inf1", audio:"ent_04"},
  B2:{video:"tunnel_free", audio:"ent_05"},
  B3:{video:"tunnel_inf2", audio:"ent_06"},
  C1:{video:"tunnel_free", audio:"ent_07"},
  // C2, C3 have no feed — their sensors (S-08, S-09) are offline.
};
const sensorForHive = code => (SENSORS.find(s=>s.hive===code)||{}).id || "—";
function mediaBlock(h){
  const m=MEDIA[h.code];
  if(!m) return '<div class="media-off"><b>Entrance tunnel feed offline</b>'
    +'<span>Sensor '+sensorForHive(h.code)+' is down — no video or audio stream from this colony right now.</span></div>';
  return '<div class="media">'
    +'<div class="mediatag"><span class="d"></span>ENTRANCE TUNNEL · CAM-HIVE-'+h.code+'</div>'
    +'<video class="tunnelvid" src="'+MEDIA_BASE+'video/'+m.video+'.mp4" poster="'+MEDIA_BASE+'video/'+m.video+'.jpg" controls loop muted playsinline preload="none"></video>'
    +'<div class="audiorow"><span class="aulbl">Hive acoustics · entrance mic</span>'
    +'<audio class="hiveaud" src="'+MEDIA_BASE+'audio/'+m.audio+'.mp3" controls preload="none"></audio></div>'
    +'</div>';
}
// map a hive's real geo position to a [lat,lon] readout for the HUD.
function hiveLatLon(code){
  const o=YARD_LAYOUT[code]||[0,0,0];
  return [ APIARY.lat + o[1]/YARD_M_LAT, APIARY.lon + o[0]/YARD_M_LON ];
}
function passFilter(h){ return S.mapfilter==="all" ? true : S.mapfilter==="watch" ? h.st!=="ok" : h.st==="crit"; }
function hiveSVG(h){
  const p=POS[h.code], cx=p[0], cy=p[1], rot=p[2]||0;
  const w=38, ht=46, x=-w/2, y=-ht/2;
  const land=(x+8)+","+(y+ht)+" "+(x+w-8)+","+(y+ht)+" "+(x+w-11)+","+(y+ht+7)+" "+(x+11)+","+(y+ht+7);
  const b=4,L=8;
  const br='M'+(x-b)+','+(y-b+L)+'V'+(y-b)+'H'+(x-b+L)+' M'+(x+w+b-L)+','+(y-b)+'H'+(x+w+b)+'V'+(y-b+L)
    +' M'+(x+w+b)+','+(y+ht+b-L)+'V'+(y+ht+b)+'H'+(x+w+b-L)+' M'+(x-b+L)+','+(y+ht+b)+'H'+(x-b)+'V'+(y+ht+b-L);
  return '<g class="hbx'+(h.code===S.sel?' sel':'')+'" data-st="'+STMAP[h.st]+'" data-code="'+h.code+'" data-cx="'+cx+'" data-cy="'+cy+'">'
    +'<g transform="translate('+cx+','+cy+') rotate('+rot+')">'
    +'<polygon class="land" points="'+land+'"/>'
    +'<rect class="body" x="'+x+'" y="'+y+'" width="'+w+'" height="'+ht+'" rx="2.5"/>'
    +'<rect class="lid" x="'+(x+4)+'" y="'+(y+4)+'" width="'+(w-8)+'" height="'+(ht-12)+'" rx="1.5"/>'
    +'<line class="ent" x1="'+(x+8)+'" y1="'+(y+ht)+'" x2="'+(x+w-8)+'" y2="'+(y+ht)+'"/>'
    +'<rect class="pip" x="'+(x+3)+'" y="'+(y+3)+'" width="5.5" height="5.5"/>'
    +'<path class="bracket" d="'+br+'"/>'
    +'</g>'
    +'<text class="code" x="'+cx+'" y="'+(cy+ht/2+18)+'">'+h.code+'</text>'
    +'<text class="val" x="'+cx+'" y="'+(cy+ht/2+29)+'">'+h.mite.toFixed(1)+'/100</text>'
    +'</g>';
}
function siteDecor(){
  let grid=''; for(let gx=40;gx<880;gx+=44) grid+='<line class="m-grid" x1="'+gx+'" y1="30" x2="'+gx+'" y2="525"/>';
  for(let gy=30;gy<525;gy+=44) grid+='<line class="m-grid" x1="40" y1="'+gy+'" x2="880" y2="'+gy+'"/>';
  const parcel='60,40 850,62 824,520 78,500';
  let hatch=''; for(let hx=80;hx<820;hx+=15) hatch+='<line x1="'+hx+'" y1="44" x2="'+(hx-10)+'" y2="66"/>';
  return '<g>'+grid+'</g>'
    +'<polygon class="m-parcel" points="'+parcel+'"/><polygon class="m-fence" points="'+parcel+'"/>'
    +'<g class="m-hatch">'+hatch+'</g><text class="m-lbl s" x="82" y="38">WINDBREAK / TREELINE</text>'
    +'<path class="m-path" d="M120,500 C160,430 150,360 300,320 S520,300 690,250"/>'
    +'<rect class="m-struct" x="700" y="430" width="74" height="46" rx="2"/><text class="m-lbl s" x="737" y="457" text-anchor="middle">EQUIP</text>'
    +'<rect class="m-struct" x="556" y="452" width="24" height="18" rx="2"/><text class="m-lbl s" x="568" y="484" text-anchor="middle">H2O</text>'
    +'<text class="m-lbl" x="60" y="24">UC DAVIS · LAIDLAW APIARY · SCHEMATIC · 9 colonies · 38.5367, -121.7889</text>'
    +'<g transform="translate(815,96)"><line style="stroke:var(--muted)" x1="0" y1="13" x2="0" y2="-13"/><path d="M0,-17 L5,-8 L-5,-8 Z" fill="var(--muted)"/><text class="m-lbl s" x="0" y="26" text-anchor="middle">N</text></g>'
    +'<g transform="translate(90,535)"><line x1="0" y1="0" x2="80" y2="0" stroke="var(--faint)" stroke-width="1.5"/><line x1="0" y1="-3" x2="0" y2="3" stroke="var(--faint)"/><line x1="80" y1="-3" x2="80" y2="3" stroke="var(--faint)"/><text class="m-lbl s" x="0" y="13">0</text><text class="m-lbl s" x="72" y="13">10 m</text></g>'
    +'<g class="reticle" id="reticle" style="display:none"><line id="rv" x1="0" y1="0" x2="0" y2="0"/><line id="rh" x1="0" y1="0" x2="0" y2="0"/></g>'
    +'<text class="hovtag" id="hovtag" style="display:none"></text>';
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
let satMap=null, satTag={}, satTiles=null;
const colorOf = st => st==="crit" ? "#d65a52" : st==="watch" ? "#d9913f" : "#4caf7d";

// Basemap: Esri World Imagery only — properly licensed and reliable for demo day.
// (Scraped Google tiles are kept out of the live dashboard for ToU + reliability.)
// maxNativeZoom = deepest level with REAL imagery; we allow OVERZOOM levels past it
// for fine box placement, where only the last level is mildly CSS-upscaled.
const ESRI = { url:"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
               maxNativeZoom:21, attribution:"Imagery © Esri, Maxar, Earthstar Geographics" };
const OVERZOOM = 1;
function setBasemap(){
  if(!satMap || satTiles) return;
  const maxZ=ESRI.maxNativeZoom+OVERZOOM;
  satMap.setMaxZoom(maxZ);
  // NOTE: tileLayer's own maxZoom defaults to 18 — must raise it or tiles vanish above z18.
  satTiles=L.tileLayer(ESRI.url,{maxZoom:maxZ, maxNativeZoom:ESRI.maxNativeZoom, attribution:ESRI.attribution}).addTo(satMap);
  satTiles.bringToBack();
}

// ~0.9 m half-box around a hive centre, in degrees (frames one colony coverage area).
function boxBounds(lat, lon, half=0.9){
  const dLat=half/110574, dLon=half/(111320*Math.cos(lat*Math.PI/180));
  return [[lat-dLat,lon-dLon],[lat+dLat,lon+dLon]];
}
// Large, legible colony marker — a status-coloured hive badge with a pointer, drawn
// in screen space so it stays clear at every zoom. THIS is what the judges read.
const HEX='<svg class="hx" viewBox="0 0 24 24"><path d="M12 2l8.7 5v10L12 22l-8.7-5V7z"/></svg>';
function hiveMarkIcon(h){
  return L.divIcon({className:"", iconSize:[46,34], iconAnchor:[23,34],
    html:'<div class="hivemark '+h.st+(h.code===S.sel?' sel':'')+'">'+HEX+'<span class="hm-code">'+h.code+'</span></div>'});
}
function initSatMap(){
  if(satMap) return satMap;
  satMap=L.map("leaflet",{ zoomControl:false, attributionControl:true, minZoom:16, maxZoom:22 });
  // Open on the open field at z20 so the whole yard of markers reads on clean ground.
  satMap.setView([APIARY.lat, APIARY.lon], 20);
  setBasemap();
  wireMapSearch();                   // place search + home
  L.control.zoom({position:"bottomright"}).addTo(satMap); // topleft is reserved for the sensor panel
  L.control.scale({imperial:false, position:"bottomleft"}).addTo(satMap);
  HIVES.forEach(h=>{
    const [lat,lon]=hiveLatLon(h.code);
    const tag=L.marker([lat,lon],{icon:hiveMarkIcon(h),keyboard:false,riseOnHover:true}).addTo(satMap);
    tag.on("click",()=>{ S.sel=h.code; renderDetail(); resetCam(); refreshSatStyles(); });
    satTag[h.code]=tag;
  });

  // ---- sensor nodes + drawing layer (Geoman) ----
  satMap.createPane("sensors"); satMap.getPane("sensors").style.zIndex=620;
  SENSORS.forEach(s=>{
    const [la,lo]=hiveLatLon(s.hive);
    s._node=L.circleMarker([la,lo],{pane:"sensors",radius:4,weight:2,
      color:sensorOnline(s)?"#4caf7d":"#d65a52",fillColor:"#0a0d12",fillOpacity:1})
      .addTo(satMap).bindTooltip(s.id+" · "+s.type+" · "+s.hive,{direction:"top"});
  });

  // Geoman draw/edit toolbar (rectangle, polygon, circle + edit/drag/remove).
  satMap.pm.addControls({position:"topright", drawMarker:false, drawCircleMarker:false,
    drawPolyline:false, drawText:false, drawRectangle:true, drawPolygon:true, drawCircle:true,
    editMode:true, dragMode:true, removalMode:true, rotateMode:false, cutPolygon:false});
  satMap.pm.setGlobalOptions({snappable:true, snapDistance:18});
  satMap.on("pm:create", e=>{
    if(armedSensor){ assignBoundary(armedSensor, e.layer); setArmed(null); }
    else openAssignPopup(e.layer);     // no sensor armed → ask which one, on the shape
  });

  renderBoundaries();   // re-draw any saved boundaries
  return satMap;
}
// Style a boundary by its sensor's online state and label it with the sensor number.
function styleBoundary(layer,id){
  const s=SENSOR_BY_ID[id], on=s&&sensorOnline(s), col=on?"#4caf7d":"#d65a52";
  if(layer.setStyle) layer.setStyle({color:col,weight:2,dashArray:on?null:"5 4",fillColor:col,fillOpacity:0.12});
  layer.bindTooltip(id+(on?"":" · OFFLINE"),{permanent:true,direction:"center",className:"sensor-tip"});
}
// Attach a freshly created/loaded layer: style, label, track, and wire edit/remove.
function registerBoundary(id,layer){
  layer._sensorId=id; boundaryLayers[id]=layer; styleBoundary(layer,id);
  layer.on("pm:edit",()=>{ boundaries[id]=layer.toGeoJSON().geometry; saveBoundaries(); });
  layer.on("pm:remove",()=>{ delete boundaries[id]; delete boundaryLayers[id]; saveBoundaries(); renderSensorPanel(); });
}
function removeBoundaryLayer(id){ const l=boundaryLayers[id]; if(l){ l.remove(); delete boundaryLayers[id]; } }
// Commit a drawn shape to a sensor number (one boundary per sensor; replaces).
function assignBoundary(id, layer){
  if(!SENSOR_BY_ID[id]){ layer.remove(); return; }
  removeBoundaryLayer(id);
  boundaries[id]=layer.toGeoJSON().geometry;
  registerBoundary(id, layer);
  saveBoundaries(); renderSensorPanel();
}
// Explicit mapping step: a popup on the shape with a sensor dropdown + Assign.
function openAssignPopup(layer){
  const opts=SENSORS.map(s=>'<option value="'+s.id+'">'+s.id+' · '+s.type+' · '+s.hive+(sensorOnline(s)?'':' (offline)')+'</option>').join("");
  const html='<div class="assignpop"><div class="apx">Map this shape to sensor</div>'
    +'<select class="apsel">'+opts+'</select>'
    +'<div class="aprow"><button class="apok">Assign</button><button class="apno">Discard</button></div></div>';
  const center=layer.getBounds ? layer.getBounds().getCenter() : layer.getLatLng();
  const pop=L.popup({closeButton:false, className:"assign-popup", minWidth:188}).setLatLng(center).setContent(html).openOn(satMap);
  pop.on("remove",()=>{ if(!layer._sensorId) layer.remove(); }); // closed without assigning → discard
  setTimeout(()=>{ const root=pop.getElement(); if(!root) return;
    root.querySelector(".apok").onclick=()=>{ const id=root.querySelector(".apsel").value; assignBoundary(id, layer); satMap.closePopup(pop); };
    root.querySelector(".apno").onclick=()=>{ layer.remove(); satMap.closePopup(pop); };
  },0);
}
// Place search (geocode via OSM Nominatim, or paste "lat,lng") + home.
function wireMapSearch(){
  const inp=$("#map-q");
  const home=$("#map-home"); if(home) home.onclick=()=>satMap.setView([APIARY.lat,APIARY.lon],20);
  if(!inp || inp._wired) return; inp._wired=true;
  inp.addEventListener("keydown", async e=>{
    if(e.key!=="Enter") return;
    const q=inp.value.trim(); if(!q) return;
    const ll=q.match(/^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$/);
    if(ll){ satMap.setView([+ll[1],+ll[2]],20); inp.classList.remove("err"); return; }
    inp.classList.add("loading");
    try{
      const r=await fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1&q="+encodeURIComponent(q),{headers:{Accept:"application/json"}});
      const j=await r.json();
      if(j && j[0]){ satMap.setView([+j[0].lat,+j[0].lon],19); inp.classList.remove("err"); }
      else inp.classList.add("err");
    }catch{ inp.classList.add("err"); }
    finally{ inp.classList.remove("loading"); }
  });
}
function renderBoundaries(){
  Object.entries(boundaries).forEach(([id,geom])=>{
    if(!SENSOR_BY_ID[id]) return;
    const layer=L.geoJSON({type:"Feature",geometry:geom}).getLayers()[0];
    layer.addTo(satMap); registerBoundary(id,layer);
  });
}
function setArmed(id){
  armedSensor=id;
  if(satMap){ if(id) satMap.pm.enableDraw("Rectangle"); else satMap.pm.disableDraw(); }
  renderSensorPanel();
}
// Re-tint markers/labels to the current (possibly live) hive states.
function refreshSatStyles(){
  HIVES.forEach(h=>{ if(satTag[h.code]) satTag[h.code].setIcon(hiveMarkIcon(h)); });
  SENSORS.forEach(s=>{ if(s._node) s._node.setStyle({color:sensorOnline(s)?"#4caf7d":"#d65a52"}); });
  Object.keys(boundaryLayers).forEach(id=>styleBoundary(boundaryLayers[id],id));
  renderSensorPanel();
}
// Sensor roster panel: online/offline status + arm-to-draw + clear, over the map.
function renderSensorPanel(){
  const el=$("#sensorlist"); if(!el) return;
  const hc=$("#sensor-count"); if(hc) hc.textContent=onlineCount()+"/"+SENSORS.length+" online";
  el.innerHTML=SENSORS.map(s=>{
    const on=sensorOnline(s), has=!!boundaries[s.id], armed=armedSensor===s.id;
    return '<div class="srow'+(armed?' armed':'')+'" data-sensor="'+s.id+'">'
      +'<span class="sdot '+(on?'on':'off')+'"></span>'
      +'<span class="sid">'+s.id+'</span>'
      +'<span class="smeta">'+s.type+' · '+s.hive+'</span>'
      +'<span class="sbound '+(has?'mapped':'')+'">'+(has?'boundary set':'no boundary')+'</span>'
      +'<button class="sdraw" data-draw="'+s.id+'">'+(armed?'drawing…':(has?'redraw':'draw'))+'</button>'
      +(has?'<button class="sclear" data-clear="'+s.id+'" title="clear boundary">✕</button>':'')
      +'</div>';
  }).join("");
  el.querySelectorAll("[data-draw]").forEach(b=>b.onclick=()=>setArmed(armedSensor===b.dataset.draw?null:b.dataset.draw));
  el.querySelectorAll("[data-clear]").forEach(b=>b.onclick=()=>{ removeBoundaryLayer(b.dataset.clear); delete boundaries[b.dataset.clear]; saveBoundaries(); renderSensorPanel(); });
  el.querySelectorAll(".srow").forEach(r=>r.addEventListener("mouseenter",()=>{ const l=boundaryLayers[r.dataset.sensor]; if(l&&l.setStyle) l.setStyle({weight:4}); }));
  el.querySelectorAll(".srow").forEach(r=>r.addEventListener("mouseleave",()=>{ const l=boundaryLayers[r.dataset.sensor]; if(l&&l.setStyle) l.setStyle({weight:2}); }));
}
function setSensorPanel(on){
  document.body.classList.toggle("sensorson",on);
  const btn=$("#sensors-btn"); if(btn) btn.classList.toggle("on",on);
  const p=$("#sensorpanel"); if(p) p.classList.toggle("on",on);
  if(on) renderSensorPanel(); else setArmed(null);
}
function renderMap(){
  const svg=$("#sitemap"), leaf=$("#leaflet"); if(!svg) return;
  if(S.mapmode==="sat"){
    svg.style.display="none"; if(leaf) leaf.classList.add("on");
    $("#mapsearch")?.classList.add("on");
    initSatMap();
    // container was display:none until now, so Leaflet must re-measure it.
    setTimeout(()=>{ if(satMap) satMap.invalidateSize(); },0);
    refreshSatStyles();
  }else{
    if(leaf) leaf.classList.remove("on"); $("#mapsearch")?.classList.remove("on"); svg.style.display=""; svg.style.cursor="crosshair";
    svg.innerHTML=siteDecor()+HIVES.filter(passFilter).map(hiveSVG).join("");
    svg.querySelectorAll(".hbx").forEach(g=>{
      g.addEventListener("click",()=>{ S.sel=g.dataset.code; renderMap(); renderDetail(); resetCam(); });
      g.addEventListener("mouseenter",()=>showReticle(g));
      g.addEventListener("mouseleave",hideReticle);
    });
  }
}
function showReticle(g){
  const cx=+g.dataset.cx, cy=+g.dataset.cy, h=get(g.dataset.code);
  const rv=$("#rv"), rh=$("#rh"), ret=$("#reticle"), tag=$("#hovtag"); if(!rv) return;
  rv.setAttribute("x1",cx);rv.setAttribute("y1",30);rv.setAttribute("x2",cx);rv.setAttribute("y2",525);
  rh.setAttribute("x1",40);rh.setAttribute("y1",cy);rh.setAttribute("x2",880);rh.setAttribute("y2",cy);
  ret.style.display="block";
  tag.textContent=h.code+" · "+STWORD[h.st].toUpperCase()+" · "+h.mite.toFixed(1)+"/100 · stress "+h.stress;
  tag.setAttribute("x", cx<450?cx+30:cx-30); tag.setAttribute("y", cy-30);
  tag.setAttribute("text-anchor", cx<450?"start":"end"); tag.style.display="block";
}
function hideReticle(){ const r=$("#reticle"),t=$("#hovtag"); if(r)r.style.display="none"; if(t)t.style.display="none"; }
function wireMapToolbar(){
  S.mapmode="schem";  // satellite view removed - schematic yard map only
  const _schem=$("#mv-schem"); if(_schem) _schem.onclick=()=>{ S.mapmode="schem"; renderMap(); };
  const _sat=$("#mv-sat"); if(_sat) _sat.onclick=()=>{ S.mapmode="sat"; renderMap(); };
  // Sensors roster lives on the (satellite) map; opening it also switches there.
  const sb=$("#sensors-btn"); if(sb) sb.onclick=()=>{
    if(S.mapmode!=="sat"){ $("#mv-sat").click(); setSensorPanel(true); }
    else setSensorPanel(!document.body.classList.contains("sensorson"));
  };
  document.querySelectorAll("[data-mf]").forEach(b=>b.onclick=()=>{ S.mapfilter=b.dataset.mf; document.querySelectorAll("[data-mf]").forEach(x=>x.classList.toggle("on",x===b)); renderMap(); });
  const pb=$("#scrub-play"); if(pb) pb.onclick=function(){ this.textContent=this.textContent==="❚❚"?"▶":"❚❚"; };
  const ab=$("#scrub-arch"); if(ab) ab.onclick=function(){ const live=$("#map-live"); const on=this.style.color==="var(--honey)"; this.style.color=on?"var(--muted)":"var(--honey)"; if(live) live.textContent=on?"LIVE":"ARCHIVED"; };
}
function pill(v){ return v; }

/* ---------------- colony vitality radar ---------------- */
const AXIS=["Mite Ctrl","Acoustic","Queen","Foraging","Entrance"];
const clamp=x=>Math.max(0,Math.min(1,x));
function vitals(h){
  return [
    clamp(1 - h.mite/6),
    clamp(1 - h.stress/100),
    h.queen==="Queenless"?0.12 : h.queen==="Pre-swarm"?0.5 : clamp(h.qc),
    clamp(h.bpm/180),
    clamp(({low:1,med:0.62,high:0.32}[h.wasp]) - h.cong/300)
  ];
}
function yardVitals(){
  const acc=[0,0,0,0,0];
  HIVES.forEach(h=>vitals(h).forEach((v,i)=>acc[i]+=v));
  return acc.map(s=>s/HIVES.length);
}
function prevVitals(h){
  const cur=vitals(h); const seed=[...h.code].reduce((s,c)=>s+c.charCodeAt(0),0);
  return cur.map((v,i)=>clamp(v - ((((seed+i*53)%23)-11)/100)));
}
function poly(vals,cx,cy,R){
  return vals.map((v,i)=>{const a=(-90+i*72)*Math.PI/180; return (cx+R*v*Math.cos(a)).toFixed(1)+","+(cy+R*v*Math.sin(a)).toFixed(1);}).join(" ");
}
function radarSVG(h){
  const cx=150,cy=134,R=92, id="vital-"+h.code;
  const cur=vitals(h), avg=yardVitals(), prev=prevVitals(h);
  let rings=""; [0.25,0.5,0.75,1].forEach(f=>rings+='<polygon class="rring" points="'+poly([f,f,f,f,f],cx,cy,R)+'"/>');
  let spokes="",labels="",dots="";
  for(let i=0;i<5;i++){
    const a=(-90+i*72)*Math.PI/180;
    spokes+='<line class="rspoke" x1="'+cx+'" y1="'+cy+'" x2="'+(cx+R*Math.cos(a)).toFixed(1)+'" y2="'+(cy+R*Math.sin(a)).toFixed(1)+'"/>';
    const lx=cx+(R+15)*Math.cos(a), ly=cy+(R+15)*Math.sin(a);
    const anch=Math.abs(Math.cos(a))<0.3?"middle":(Math.cos(a)>0?"start":"end");
    const dy=Math.sin(a)<-0.5?-3:Math.sin(a)>0.5?10:3;
    labels+='<text class="rax" x="'+lx.toFixed(0)+'" y="'+(ly+dy).toFixed(0)+'" text-anchor="'+anch+'">'+AXIS[i]+'</text>'
          +'<text class="rax pct" x="'+lx.toFixed(0)+'" y="'+(ly+dy+11).toFixed(0)+'" text-anchor="'+anch+'">'+Math.round(cur[i]*100)+'%</text>';
    dots+='<circle cx="'+(cx+R*cur[i]*Math.cos(a)).toFixed(1)+'" cy="'+(cy+R*cur[i]*Math.sin(a)).toFixed(1)+'" r="2.5" fill="#fff"/>';
  }
  return '<svg viewBox="0 0 300 272">'
    +'<defs><radialGradient id="'+id+'" gradientUnits="userSpaceOnUse" cx="'+cx+'" cy="'+cy+'" r="'+R+'">'
    +'<stop offset="0%" stop-color="#b3261e"/><stop offset="40%" stop-color="#ad7d2b"/><stop offset="72%" stop-color="#6f9c34"/><stop offset="100%" stop-color="#3f9a52"/></radialGradient></defs>'
    +rings+spokes
    +'<polygon points="'+poly(avg,cx,cy,R)+'" fill="none" stroke="#6b7689" stroke-width="1.2" opacity=".75"/>'
    +'<polygon points="'+poly(prev,cx,cy,R)+'" fill="none" stroke="var(--honey)" stroke-width="1" stroke-dasharray="3 3" opacity=".5"/>'
    +'<polygon points="'+poly(cur,cx,cy,R)+'" fill="url(#'+id+')" fill-opacity="0.82" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/>'
    +dots+labels+'</svg>';
}
function radarBlock(h){
  const cur=vitals(h); let mi=0; cur.forEach((v,i)=>{if(v<cur[mi])mi=i;});
  return '<div class="radar">'+radarSVG(h)
    +'<div class="rlegend">'
    +'<span><i style="background:linear-gradient(135deg,#3f9a52,#b3261e)"></i>This hive</span>'
    +'<span><i class="ln" style="border-color:#6b7689"></i>Yard avg</span>'
    +'<span><i class="ln" style="border-color:var(--honey)"></i>7d ago</span></div>'
    +'<div class="subnote" style="text-align:center;margin:0">Weakest signal: <b style="color:var(--ink)">'+AXIS[mi]+'</b> at '+Math.round(cur[mi]*100)+'%</div>'
    +'</div>';
}
/* ---------------- per-hive Orkes workflow ---------------- */
const WFAPPROVED={};
function workflow(h){
  const ap=WFAPPROVED[h.code];
  if(h.queen==="Queenless") return { name:"requeen-colony",
    reco:"Queenless signature confirmed across acoustic and behavior. Introduce a mated queen within 72h; without eggs the colony cannot raise its own.",
    tasks:[["detect.queenless","acoustic roar + foragers down","done","2m ago"],
      ["confirm.eggcheck","operator frame check","done","18m ago"],
      ["source.queen","locate mated queen","running","running 40m"],
      ["approve.introduce","human-in-the-loop", ap?"done":"wait", ap?"approved":"awaiting you"],
      ["introduce.queen","cage + candy plug", ap?"running":"pending","day 1"],
      ["verify.acceptance","re-baseline acoustic","pending","day 5"]] };
  if(h.queen==="Pre-swarm") return { name:"swarm-prevention",
    reco:"Swarm spike, bearding and a traffic surge. Inspect for queen cells within 48h and add space, or make a split.",
    tasks:[["detect.preswarm","swarm spike + bearding","done","6m ago"],
      ["inspect.cells","operator queen-cell check","running","running 12m"],
      ["approve.split","human-in-the-loop", ap?"done":"wait", ap?"approved":"awaiting you"],
      ["execute.split","walk-away split", ap?"running":"pending","today"],
      ["monitor.spike","watch acoustic daily","pending","ongoing"]] };
  if(h.st==="crit") return { name:"varroa-treatment",
    reco:"Vision 4.6/100 plus acoustic stress 71 confirms Varroa at 0.91. Brood is low now, a high-efficacy window. Oxalic acid vapor within 7 days.",
    tasks:[["detect.varroa","fusion confirmed 0.91","done","1m ago"],
      ["confirm.rescan","24h tunnel re-scan","running","running 3h"],
      ["approve.treatment","human-in-the-loop", ap?"done":"wait", ap?"approved":"awaiting you"],
      ["apply.oxalic","oxalic acid vapor", ap?"running":"pending","within 7d"],
      ["retest.load","re-test at +14d","pending","day 14"]] };
  if(h.wasp==="high") return { name:"robbing-mitigation",
    reco:"Wasp pressure is high with entrance congestion. Reduce the entrance and remove exposed comb or syrup nearby.",
    tasks:[["detect.robbing","wasp HIGH + congestion","done","4m ago"],
      ["approve.reduce","human-in-the-loop", ap?"done":"wait", ap?"approved":"awaiting you"],
      ["reduce.entrance","one bee-width", ap?"running":"pending","today"],
      ["monitor.pressure","re-check tomorrow","pending","24h"]] };
  if(h.mtrend==="rising") return { name:"mite-watch",
    reco:"Mites trending toward the 3/100 line. No treatment yet; re-test in 7 days and stage a plan.",
    tasks:[["detect.trend","mites rising","done","8m ago"],
      ["schedule.retest","auto re-scan","running","queued 7d"],
      ["stage.plan","prep treatment plan","pending","this week"]] };
  return { name:"monitor-loop",
    reco:"All signals within colony baseline. No intervention needed; the non-invasive monitoring loop continues.",
    tasks:[["ingest.streams","vision + acoustic + behavior","running","live"],
      ["fuse.baseline","cross-modal check","running","live"],
      ["schedule.scan","next scan +3d","pending","3 days"]] };
}
function orkesBlock(h){
  const wf=workflow(h);
  const ST={done:["done","var(--ok)"],running:["running","var(--watch)"],wait:["awaiting approval","var(--watch)"],pending:["pending","var(--faint)"]};
  const rows=wf.tasks.map(t=>{
    const s=t[2], info=ST[s];
    const approve = s==="wait" ? ' <button class="approve" data-hive="'+h.code+'">Approve</button>' : '';
    return '<div class="sp sp-'+s+'"><span class="spdot" style="background:'+info[1]+'"></span>'
      +'<div><div class="spn">'+t[0].replace(/[._]/g," ")+' <span class="spt" style="color:'+info[1]+'">'+info[0]+'</span>'+approve+'</div>'
      +'<div class="spnote">'+t[1]+' · '+t[3]+'</div></div></div>';
  }).join("");
  return '<div class="wfhead"><span class="wfname">'+wf.name.replace(/-/g," ")+'</span><span class="wfstat">needs your approval</span></div>'
    +'<div class="span">'+rows+'</div>'
    +'<div class="reco"><span class="recok">What we suggest</span>'+wf.reco+'</div>';
}
function pipeBlock(h){
  const f=fusion(h);
  if(S.pipe==="vision"){
    const pct=h.mite, over=pct>3, w=Math.min(100,(pct/6)*100), thr=(3/6)*100;
    return '<div class="pipe">'
      +'<div class="mline"><div><span class="v" style="color:'+(over?"var(--crit)":"var(--ink)")+'">'+pct.toFixed(1)+'</span> <span class="u">mites / 100 bees</span></div><span class="tag '+(over?"r":pct>2?"a":"g")+'">'+(over?"over line":"under line")+'</span></div>'
      +'<div class="bar"><i style="width:'+w+'%;background:'+(over?"var(--crit)":pct>2?"var(--watch)":"var(--ok)")+'"></i><span class="thr" style="left:'+thr+'%"></span></div>'
      +'<div class="subnote">Treatment line 3.0 (white mark). '+h.scanned+' bees scanned live at the tunnel. The alcohol wash kills ~300 bees for the same number.</div>'
      +'<div class="row"><span class="lab">Bees scanned</span><span class="num">'+h.scanned+'</span></div>'
      +'<div class="row"><span class="lab">Mites detected</span><span class="num">'+h.mites+'</span></div>'
      +'<div class="row"><span class="lab">Deformed-wing signs</span><span class="'+(h.dwv?"tag r":"tag g")+'">'+(h.dwv?"present":"none")+'</span></div>'
      +'<div class="row"><span class="lab">Detection confidence</span><span class="num">'+(h.st==="crit"?"91%":"94%")+'</span></div></div>';
  }
  if(S.pipe==="acoustic"){
    const s=h.stress;
    return '<div class="pipe">'
      +'<div class="mline"><div><span class="v" style="color:'+(s>60?"var(--crit)":s>40?"var(--watch)":"var(--ok)")+'">'+s+'</span> <span class="u">/ 100 stress index</span></div><span class="tag '+(s>60?"r":s>40?"a":"g")+'">'+(s>60?"high":s>40?"raised":"calm")+'</span></div>'
      +'<div class="bar"><i style="width:'+s+'%;background:'+(s>60?"var(--crit)":s>40?"var(--watch)":"var(--ok)")+'"></i></div>'
      +'<div class="row"><span class="lab">Dominant signature</span><span class="num" style="font-size:11px">'+h.freq+'</span></div>'
      +'<div class="row"><span class="lab">Queenless roar</span><span class="'+(h.roar?"tag r":"tag g")+'">'+(h.roar?"detected":"absent")+'</span></div>'
      +'<div class="row"><span class="lab">Swarm low-freq spike</span><span class="'+(h.swarm?"tag a":"tag g")+'">'+(h.swarm?"detected":"absent")+'</span></div>'
      +'<div class="row"><span class="lab">Method</span><span class="num" style="font-size:11px">colony sound analysis</span></div></div>';
  }
  if(S.pipe==="behavior"){
    return '<div class="pipe">'
      +'<div class="mline"><div><span class="v">'+h.bpm+'</span> <span class="u">bees / min · '+h.btrend+'</span></div><span class="tag '+(h.wasp==="high"?"r":h.wasp==="med"?"a":"g")+'">wasp '+h.wasp+'</span></div>'
      +'<div class="row"><span class="lab">Bearding at entrance</span><span class="'+(h.beard?"tag a":"tag g")+'">'+(h.beard?"yes":"no")+'</span></div>'
      +'<div class="row"><span class="lab">Entrance congestion</span><span class="num">'+h.cong+'%</span></div>'
      +(h.netflow!=null
        ? '<div class="row"><span class="lab">Net entrance flow <span class="livedot"></span></span><span class="'+(h.flowLabel==="outflux"?"tag r":h.flowLabel==="influx"?"tag a":"num")+'">'+(h.netflow>0?"+":"")+h.netflow+' /cycle'+(h.flowLabel!=="balanced"?" · "+h.flowLabel:"")+'</span></div>'
        : '')
      +'<div class="row"><span class="lab">Source</span><span class="num" style="font-size:11px">'+(h.live?"live sensor":"entrance camera")+'</span></div></div>';
  }
  return '<div class="pipe">'
    +'<div class="mline"><div><span class="v" style="color:var(--honey)">'+(f.conf*100).toFixed(0)+'%</span> <span class="u">overall confidence</span></div></div>'
    +'<div class="subnote">This combines the sound and camera checks into one read of the colony, so a single noisy signal does not raise a false alarm.</div>'
    +'<div class="row"><span class="lab">Based on</span><span class="num" style="font-size:11px">'+f.sig.join(" · ")+'</span></div></div>';
}
function renderDetail(){
  const h=get(S.sel);
  const [hlat,hlon]=hiveLatLon(h.code);
  $("#d-pin").textContent="CAM-HIVE-"+h.code+" · "+hlat.toFixed(5)+", "+hlon.toFixed(5);
  const seg=p=>'<button class="'+(S.pipe===p?"on":"")+'" data-pipe="'+p+'">'+p+'</button>';
  $("#dbody").innerHTML=
    '<div class="dhead"><div><div class="code">'+h.code+'</div><div class="name">'+h.name+'</div>'
      +'<div class="coord">'+hlat.toFixed(5)+', '+hlon.toFixed(5)+' · '+(h.lastSync?'verdict '+new Date(h.lastSync).toLocaleTimeString():'sync '+new Date().toLocaleTimeString())+'</div></div>'
      +'<span class="chip '+h.st+'">'+STWORD[h.st]+'</span>'
      +(h.live?'<span class="livetag" title="Driven by a live uAgent verdict">◉ LIVE</span>':'')+'</div>'
    +'<div class="headline">'+headline(h)+'</div>'
    +'<div class="divider"></div>'
    +'<div class="eyebrow">Entrance tunnel · live media</div>'
    +mediaBlock(h)
    +'<div class="divider"></div>'
    +'<div class="eyebrow">Colony vitality · this hive vs yard</div>'
    +radarBlock(h)
    +'<div class="divider"></div>'
    +'<div class="eyebrow">Recommended plan</div>'
    +orkesBlock(h)
    +'<div class="divider"></div>'
    +'<div class="eyebrow">What the sensors see</div>'
    +'<div class="seg">'+seg("vision")+seg("acoustic")+seg("behavior")+seg("fusion")+'</div>'
    +pipeBlock(h);
  $("#dbody").querySelectorAll(".seg button").forEach(b=>b.onclick=()=>{S.pipe=b.dataset.pipe; renderDetail();});
  $("#dbody").querySelectorAll(".approve").forEach(b=>b.onclick=()=>{
    WFAPPROVED[h.code]=true;
    EVENTS.unshift(ev("OPERATOR","watch",h.code,"approved · "+workflow(h).name,1));
    if(EVENTS.length>400)EVENTS.length=400;
    renderDetail(); if(S.view==="orch")renderLog();
  });
}

// Entrance view is now a real tunnel video + audio (see mediaBlock); the old
// simulated bee-canvas is retired. resetCam stays as a no-op for select handlers.
function resetCam(){}

/* ---------------- live operations log ---------------- */
const AGENT_CHIPS=["VISION","ACOUSTIC","BEHAVIOR","FUSION","REDIS","CLAUDE","ORKES","DEEPGRAM","OPERATOR"];
const LF={agents:new Set(AGENT_CHIPS), sev:new Set(["info","watch","alert"]), hive:"ALL", q:"", live:true, group:false};
let EVENTS=[], evtSeq=0, frameN=4180;
const flaggedCount=()=>HIVES.filter(h=>h.st!=="ok").length;
const critHives=()=>HIVES.filter(h=>h.st==="crit");
const jit=(n,d)=>n+Math.floor(Math.random()*(2*(d||3)+1))-(d||3);
function ev(agent,sev,hive,msg,conf,real){ return {id:++evtSeq, t:new Date(), agent, sev, hive, msg, conf, real:!!real}; }
function makeEvent(){
  const h=HIVES[Math.floor(Math.random()*HIVES.length)], r=Math.random(), f=fusion(h);
  if(h.st==="crit" && r<0.13){
    if(h.queen==="Queenless") return ev("CLAUDE","alert",h.code,"alert authored · requeen within 72h",f.conf);
    return ev("FUSION","alert",h.code,f.rule.split("→")[1].trim().toLowerCase(),f.conf);
  }
  if(h.st==="watch" && r<0.12){
    if(h.queen==="Pre-swarm") return ev("FUSION","watch",h.code,"pre-swarm · inspect for queen cells",f.conf);
    if(h.wasp==="high") return ev("BEHAVIOR","watch",h.code,"wasp pressure HIGH · robbing risk",0.79);
    return ev("FUSION","watch",h.code,"mites trending up · re-test 7d",f.conf);
  }
  if(r<0.22) return ev("VISION","info",h.code,"frame "+(frameN++)+" · "+jit(22,6)+" bees · "+(h.st==="crit"?(1+Math.floor(Math.random()*3)):0)+" mites",0.9);
  if(r<0.38) return ev("ACOUSTIC","info",h.code,"5s window · stress "+jit(h.stress)+" · SSD vector pushed",0.87);
  if(r<0.50) return ev("BEHAVIOR","info",h.code,"traffic "+jit(h.bpm,8)+" bees/min · "+h.btrend,0.84);
  if(r<0.60) return ev("FUSION","info",h.code,"signals within baseline",f.conf);
  if(r<0.72) return ev("REDIS","info",h.code,"SET hive:"+h.code+":state "+h.st,1);
  if(r<0.80) return ev("APIS","info","—","fleet sync · 9 hives · "+flaggedCount()+" flagged",1);
  if(r<0.90){ const c=critHives()[0]; if(c) return ev("ORKES","watch",c.code,"treatment wf step "+(1+Math.floor(Math.random()*4))+"/5 · awaiting approval",1); return ev("REDIS","info",h.code,"GET hive:"+h.code+":baseline",1); }
  return ev("DEEPGRAM","info","—","field copilot · mic armed · idle",1);
}
function agentLabel(a){ return a==="APIS"?"APIS-PRIME":a==="VISION"?"VISION-W":a==="ACOUSTIC"?"ACOUSTIC-W":a==="BEHAVIOR"?"BEHAVIOR-W":a; }
function logRow(e){
  const conf = (e.conf!=null && e.conf<1) ? (e.conf*100|0)+"%" : "";
  const q = e.msg.replace(/"/g,"&quot;");
  return '<div class="logrow clickrow sev-'+e.sev+(e.real?' real':'')+'" data-q="'+q+'" title="Click for a plain-English explanation">'
    +'<span class="lt">'+e.t.toLocaleTimeString([], {hour12:false})+'</span>'
    +'<span class="la a-'+e.agent+'">'+agentLabel(e.agent)+'</span>'
    +'<span class="lh">'+e.hive+'</span>'
    +'<span class="lm">'+e.msg+'</span>'
    +'<span class="lc">'+conf+'</span></div>';
}
// Click a log line -> ask the explainer agent (/api/explain) for plain English.
async function explainLine(q){
  const box=$("#explainbox"); if(!box) return;
  box.style.display="block";
  box.innerHTML='<div class="exp-line">'+q+'</div><div class="exp-ans">explaining…</div>';
  try{
    const r=await fetch("/api/explain?q="+encodeURIComponent(q));
    const j=await r.json();
    box.innerHTML='<div class="exp-head">In plain terms</div>'
      +'<div class="exp-line">'+q+'</div>'
      +'<div class="exp-ans">'+(j.explanation||"No explanation available.")+'</div>'
      +'<button class="exp-close">close</button>';
  }catch{
    box.innerHTML='<div class="exp-ans">Could not reach the explainer. Is api_server running?</div><button class="exp-close">close</button>';
  }
  const c=box.querySelector(".exp-close"); if(c) c.onclick=()=>{ box.style.display="none"; };
}
function filtered(){
  return EVENTS.filter(e=>{
    if(e.agent!=="APIS" && !LF.agents.has(e.agent)) return false;
    if(!LF.sev.has(e.sev)) return false;
    if(LF.hive!=="ALL" && e.hive!==LF.hive) return false;
    if(LF.q){ if(!((e.msg+" "+e.hive+" "+e.agent).toLowerCase().includes(LF.q.toLowerCase()))) return false; }
    return true;
  });
}
function renderLog(){
  const f=filtered(), log=$("#log");
  if(log){
    if(LF.group){
      const groups={}; f.slice(0,300).forEach(e=>{(groups[e.agent]=groups[e.agent]||[]).push(e);});
      const order=["FUSION","CLAUDE","ORKES","APIS","OPERATOR","VISION","ACOUSTIC","BEHAVIOR","REDIS","DEEPGRAM"];
      log.innerHTML=order.filter(a=>groups[a]&&groups[a].length)
        .map(a=>'<div class="loggrp">'+agentLabel(a)+' · '+groups[a].length+'</div>'+groups[a].map(logRow).join("")).join("");
    } else {
      log.innerHTML=f.slice(0,200).map(logRow).join("");
    }
    log.querySelectorAll(".clickrow").forEach(r=>r.onclick=()=>explainLine(r.dataset.q));
  }
  const m=$("#logmeta");
  if(m){ const al=EVENTS.filter(e=>e.sev==="alert").length, w=EVENTS.filter(e=>e.sev==="watch").length;
    m.innerHTML='<span><b>'+f.length+'</b> shown · '+EVENTS.length+' total</span>'
      +'<span style="color:var(--crit)">'+al+' alert</span>'
      +'<span style="color:var(--watch)">'+w+' watch</span>'
      +'<span><b>~1.4</b> events/s</span>'; }
}
function buildFilterBar(){
  const fb=$("#filterbar"); if(!fb || fb.dataset.built) return; fb.dataset.built="1";
  // Beekeeper-simple filters: importance + which hive + search. (The technical
  // per-agent chips were removed; click any log line for a plain explanation.)
  let html='<span class="flabel">Show</span>'
    +'<button class="fchip on" data-sev="info">Routine</button>'
    +'<button class="fchip sev-watch on" data-sev="watch">Watch</button>'
    +'<button class="fchip sev-alert on" data-sev="alert">Alerts</button>'
    +'<span class="fdiv"></span>'
    +'<select class="fsel" id="fhive"><option value="ALL">All hives</option>'+HIVES.map(h=>'<option value="'+h.code+'">'+h.code+' · '+h.name+'</option>').join("")+'</select>'
    +'<input class="fsearch" id="fq" placeholder="search…">'
    +'<button class="livebtn" id="livebtn"><span class="d"></span><span id="livetxt">LIVE</span></button>';
  fb.innerHTML=html;
  fb.querySelectorAll("[data-sev]").forEach(b=>b.onclick=()=>{ const s=b.dataset.sev; if(LF.sev.has(s)){LF.sev.delete(s);b.classList.remove("on");}else{LF.sev.add(s);b.classList.add("on");} renderLog(); });
  $("#fhive").onchange=e=>{ LF.hive=e.target.value; renderLog(); };
  $("#fq").oninput=e=>{ LF.q=e.target.value; renderLog(); };
  $("#livebtn").onclick=function(){ LF.live=!LF.live; this.classList.toggle("paused",!LF.live); $("#livetxt").textContent=LF.live?"LIVE":"PAUSED"; };
}
// Beekeeper-friendly side panel: what needs you, colonies at a glance, monitoring status.
function renderFleet(){
  const flagged=HIVES.filter(h=>h.st!=="ok")
    .sort((a,b)=>(a.st==="crit"?0:1)-(b.st==="crit"?0:1));
  const needs=$("#needs");
  if(needs){
    needs.innerHTML = flagged.length ? flagged.map(h=>{
      const a=action(h), ap=WFAPPROVED[h.code];
      return '<div class="needrow '+h.st+'">'
        +'<div class="needtop"><b>'+h.code+' · '+h.name+'</b><span class="chip '+h.st+'">'+STWORD[h.st]+'</span></div>'
        +'<div class="needact">'+a.t+'</div>'
        +(a.c && !ap ? '<button class="approve" data-hive="'+h.code+'">Approve plan</button>'
          : ap ? '<span class="approved">✓ approved</span>' : '')
        +'</div>';
    }).join("") : '<div class="allgood">All colonies look healthy. Nothing needs you right now.</div>';
    needs.querySelectorAll(".approve").forEach(b=>b.onclick=()=>{ WFAPPROVED[b.dataset.hive]=true; renderFleet(); if(S.sel)renderDetail(); });
  }
  const glance=$("#glance");
  if(glance) glance.innerHTML=HIVES.map(h=>
    '<div class="glrow" data-code="'+h.code+'"><span class="gldot '+h.st+'"></span>'
    +'<span class="glname">'+h.code+' · '+h.name+'</span>'
    +'<span class="glst '+h.st+'">'+STWORD[h.st]+'</span></div>').join("");
  if(glance) glance.querySelectorAll(".glrow").forEach(r=>r.onclick=()=>{ S.sel=r.dataset.code; setView("map"); renderDetail(); });

  const sys=$("#sysline");
  if(sys) sys.innerHTML=[
    ["Colonies monitored",HIVES.length],
    ["Need attention",flagged.length],
    ["Live data link", LINK.state==="live"?"connected":LINK.state==="standby"?"standby":"demo data"]
  ].map(kv=>'<span class="k">'+kv[0]+'</span><span class="v">'+kv[1]+'</span>').join("");
}
function seedLog(){
  EVENTS=[]; const now=Date.now();
  const tmp=[]; for(let i=70;i>0;i--){ const e=makeEvent(); e.t=new Date(now - i*850); tmp.push(e); }
  EVENTS=tmp.reverse();
}
function tickLog(){
  if(S.view!=="orch" || !LF.live) return;
  const n=1+(Math.random()<0.4?1:0);
  for(let i=0;i<n;i++){ EVENTS.unshift(makeEvent()); }
  if(EVENTS.length>400) EVENTS.length=400;
  renderLog();
}
function renderTicker(){
  const items=HIVES.map(h=>{
    const arrow=h.mtrend==="rising"?'<span class="dn">▲ rising</span>':'<span class="up">steady</span>';
    return '<span><b>'+h.code+'</b> '+h.mite.toFixed(1)+'/100 '+arrow+' · stress '+h.stress+'</span>';
  });
  const extra='<span><b>APIARY INDEX</b> live</span><span>SECURE UPLINK · Redis OK · Orkes workflows: 2 pending approval</span>';
  $("#ticker").innerHTML=(items.join("")+extra).repeat(2);
}

/* ---------------- chrome ---------------- */
function setView(v){
  S.view=v;
  document.querySelectorAll(".tab").forEach(t=>t.classList.toggle("on",t.dataset.view===v));
  $("#view-map").classList.toggle("on",v==="map");
  $("#view-orch").classList.toggle("on",v==="orch");
  if(v==="orch"){ buildFilterBar(); renderLog(); renderFleet(); }
}
function setMode(m){
  S.mode=m; document.body.classList.toggle("command",m==="cmd");
  $("#m-field").classList.toggle("on",m==="field"); $("#m-cmd").classList.toggle("on",m==="cmd");
  // The link readout is owned by setLink() so it reflects REAL coordinator state,
  // not the cosmetic field/command skin toggle.
}
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>setView(t.dataset.view));
$("#m-field").onclick=()=>setMode("field"); $("#m-cmd").onclick=()=>setMode("cmd");

function tickClock(){ const t=new Date().toLocaleTimeString([], {hour12:false})+" PDT"; $("#clock").textContent=t; const mt=$("#map-time"); if(mt) mt.textContent=t; }

/* ---------------- boot ---------------- */
seedLog();
renderSummary(); renderMap(); wireMapToolbar(); renderDetail(); renderTicker();
// Deep-linkable view: ?view=orch opens the orchestrator; ?map=sat opens satellite.
const _q = new URLSearchParams(location.search);
const _v = _q.get("view");
if (_v === "orch" || _v === "map") setView(_v);
if (_q.get("seed") === "sensors") { // demo: seed two example coverage boundaries
  const mk=(code,half)=>{ const [la,lo]=hiveLatLon(code), b=boxBounds(la,lo,half);
    return {type:"Polygon",coordinates:[[[b[0][1],b[0][0]],[b[1][1],b[0][0]],[b[1][1],b[1][0]],[b[0][1],b[1][0]],[b[0][1],b[0][0]]]]}; };
  boundaries["S-01"]=mk("A1",7); boundaries["S-04"]=mk("B1",6);
}
if (_q.get("map") === "sat" && $("#mv-sat")) $("#mv-sat").click();
if (_q.get("z")) setTimeout(()=>{ if(satMap) satMap.setView([APIARY.lat,APIARY.lon], +_q.get("z")); }, 140);
if (_q.get("sensors") === "1") setSensorPanel(true);
tickClock(); setInterval(tickClock,1000);
setInterval(tickLog, 850);
setInterval(()=>{ if(S.view==="orch") renderFleet(); }, 3500);

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
  if (LINK.state === "live")    return `LIVE · ${LINK.latency}ms · ${LINK.liveCodes.size} colony feed${LINK.liveCodes.size===1?"":"s"}`;
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

  let st = "ok";
  if (status === "alert") { st = "crit"; hive.mite = 4.6; hive.mtrend = "rising"; hive.dwv = true; }
  else if (status === "watch") { st = "watch"; hive.mite = 2.8; hive.mtrend = "rising"; hive.dwv = false; }
  else { hive.mite = Math.min(hive.mite, 1.2); hive.mtrend = "steady"; hive.dwv = false; }

  // Queenless / swarm are terminal acoustic alerts and outrank varroa for severity.
  if (v.queenless_alert) { st = "crit"; hive.queen = "Queenless"; hive.roar = true; hive.swarm = false; hive.beard = false; }
  else if (v.swarm_alert) { st = (st === "crit" ? "crit" : "watch"); hive.queen = "Pre-swarm"; hive.swarm = true; hive.beard = true; hive.roar = false; }
  else { hive.queen = "Queenright"; hive.roar = false; hive.swarm = false; hive.beard = false; }

  const changed = hive.st !== st; hive.st = st;
  return changed;
}

// Translate a brand-new verdict into a real ops-log line.
function verdictEvent(code, v) {
  if (v.queenless_alert) return ev("CLAUDE", "alert", code, "queenless confirmed · requeen within 72h", 0.88, true);
  if (v.swarm_alert)     return ev("FUSION", "watch", code, "pre-swarm signature · inspect for queen cells", 0.83, true);
  if (v.varroa_status === "alert") return ev("FUSION", "alert", code, "varroa confirmed · treat this week", 0.91, true);
  if (v.varroa_status === "watch") return ev("FUSION", "watch", code, "varroa trending up · re-test 7d", 0.78, true);
  if (typeof v.traffic === "number" && Math.abs(v.traffic) >= 50)
    return ev("BEHAVIOR", "info", code, `net ${v.traffic > 0 ? "influx" : "outflux"} ${v.traffic} bees/cycle`, 0.84, true);
  return ev("APIS", "info", code, "verdict received · signals within baseline", 1, true);
}

async function syncBackendData() {
  const res = await pollCoordinator();
  setLink(res.state, res.latency);
  if (res.state === "offline" || !res.hives) return;

  let changed = false;
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
      EVENTS.unshift(verdictEvent(code, latest));
      if (EVENTS.length > 400) EVENTS.length = 400;
      if (S.view === "orch") renderLog();
    }
    if (applyVerdict(hive, latest)) changed = true;
  }

  if (changed || res.state === "live") {
    renderSummary(); renderMap(); renderTicker();
    if (S.view === "orch") renderFleet();
    if (S.sel) renderDetail();
  }
}

setLink("offline", null);
syncBackendData();
setInterval(syncBackendData, 2000);
