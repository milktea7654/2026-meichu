// app.js - 前端地圖渲染、2.5D 擬真建築、H3 六角格迷霧遮罩與即時狀態同步

let map;
let playerMarker;
let fogLayerGroup;

// 預設中心 (以新竹交大/清大週邊為例)
const DEFAULT_LAT = 24.787;
const DEFAULT_LNG = 120.997;

function initMap() {
  map = L.map('map', {
    center: [DEFAULT_LAT, DEFAULT_LNG],
    zoom: 17,
    zoomControl: false
  });

  // 使用 Pokemon GO 清爽質感的淺色乾淨街道底圖 (CartoDB Positron / OSM 清新配色)
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd'
  }).addTo(map);

  fogLayerGroup = L.layerGroup().addTo(map);

  // 玩家標記 (小精靈球 / 冒險者圖標)
  const playerIcon = L.divIcon({
    className: 'player-custom-icon',
    html: '<div style="background:#ef4444; width:18px; height:18px; border-radius:50%; border:3px solid white; box-shadow:0 0 10px rgba(239,68,68,0.8);"></div>',
    iconSize: [24, 24],
    iconAnchor: [12, 12]
  });

  playerMarker = L.marker([DEFAULT_LAT, DEFAULT_LNG], { icon: playerIcon }).addTo(map);

  // 模擬載入示範數據
  updateHUD({
    level: 2,
    xp: 85,
    needed_xp: 150,
    weather: { icon: "☀️", name: "晴朗", temp: "28°C" }
  });

  renderDemoFog();
}

// 模擬繪製 H3 迷霧 (未探索區域為灰色六角格，已探索處開霧透明)
function renderDemoFog() {
  fogLayerGroup.clearLayers();

  // 繪製周邊的迷霧格 (半透明夜霧)
  const offsets = [
    [-0.001, -0.001], [0.001, 0.001], [-0.0015, 0.0005], [0.0012, -0.0015]
  ];

  offsets.forEach(([dlat, dlng]) => {
    L.circle([DEFAULT_LAT + dlat, DEFAULT_LNG + dlng], {
      radius: 40,
      color: '#334155',
      fillColor: '#1e293b',
      fillOpacity: 0.65,
      weight: 1
    }).bindPopup("未探索迷霧 (靠近累積探索度即可開霧)").addTo(fogLayerGroup);
  });
}

function updateHUD(data) {
  if (data.level) document.getElementById('player-level').innerText = `Lv.${data.level}`;
  if (data.xp !== undefined && data.needed_xp) {
    document.getElementById('current-xp').innerText = data.xp;
    document.getElementById('needed-xp').innerText = data.needed_xp;
    const pct = Math.min(100, Math.round((data.xp / data.needed_xp) * 100));
    document.getElementById('xp-bar').style.width = `${pct}%`;
  }
  if (data.weather) {
    document.getElementById('weather-icon').innerText = data.weather.icon;
    document.getElementById('weather-name').innerText = data.weather.name;
    document.getElementById('weather-temp').innerText = data.weather.temp;
  }
}

window.addEventListener('DOMContentLoaded', initMap);
