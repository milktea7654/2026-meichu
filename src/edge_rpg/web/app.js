// app.js - 零網路依賴的 2.5D 街道、立體房屋與 H3 動態迷霧渲染器

let canvas, ctx;
let playerPos = { x: 0, y: 0 };
let currentTargetEvent = null;

// 模擬已探索與未探索的 H3 六角格子
const cells = [
  { id: "c1", q: 0, r: 0, state: "EXPLORED" },
  { id: "c2", q: 1, r: -1, state: "EXPLORED" },
  { id: "c3", q: -1, r: 1, state: "DISCOVERING", progress: 0.65 },
  { id: "c4", q: 0, r: 1, state: "UNSEEN" },
  { id: "c5", q: 1, r: 0, state: "UNSEEN" },
  { id: "c6", q: -1, r: 0, state: "UNSEEN" }
];

function initMap() {
  canvas = document.getElementById('offline-canvas-map');
  ctx = canvas.getContext('2d');
  resizeCanvas();
  window.addEventListener('resize', resizeCanvas);

  // 初始 HUD
  updateHUD({
    level: 2, xp: 95, needed_xp: 150,
    weather: { icon: "☀️", name: "晴朗", temp: "28°C" }
  });

  // 渲染迴圈
  requestAnimationFrame(renderLoop);
}

function resizeCanvas() {
  canvas.width = canvas.parentElement.clientWidth;
  canvas.height = canvas.parentElement.clientHeight;
  playerPos.x = canvas.width / 2;
  playerPos.y = canvas.height / 2;
}

function renderLoop() {
  drawPokemonGoMap();
  requestAnimationFrame(renderLoop);
}

function drawPokemonGoMap() {
  const w = canvas.width;
  const h = canvas.height;
  const cx = playerPos.x;
  const cy = playerPos.y;

  // 1. 地面底色 (Pokemon Go 清爽淺綠)
  ctx.fillStyle = '#d6eed2';
  ctx.fillRect(0, 0, w, h);

  // 2. 繪製清爽街道網格 (白色路面 + 灰色輪廓)
  ctx.lineWidth = 26;
  ctx.strokeStyle = '#ffffff';
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // 主要街道
  ctx.beginPath();
  ctx.moveTo(cx - 300, cy - 80);
  ctx.lineTo(cx + 300, cy + 120);
  ctx.moveTo(cx - 100, cy - 250);
  ctx.lineTo(cx + 120, cy + 250);
  ctx.stroke();

  // 街道外邊框線
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#c4dfbe';
  ctx.stroke();

  // 3. 繪製 2.5D 簡易立體房屋 (Extruded Buildings)
  drawBuilding(cx - 160, cy - 140, 70, 50, 16);
  drawBuilding(cx + 80, cy - 180, 85, 60, 20);
  drawBuilding(cx + 120, cy + 60, 65, 75, 14);
  drawBuilding(cx - 190, cy + 80, 80, 55, 18);

  // 4. 繪製 H3 迷霧 (Fog of War)
  drawH3Fog(cx, cy);

  // 5. 繪製玩家角色 (精靈球光暈圖標)
  ctx.save();
  ctx.shadowColor = 'rgba(37, 99, 235, 0.5)';
  ctx.shadowBlur = 15;
  ctx.fillStyle = '#2563eb';
  ctx.beginPath();
  ctx.arc(cx, cy, 9, 0, Math.PI * 2);
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = '#ffffff';
  ctx.stroke();
  ctx.restore();
}

// 繪製 2.5D 建物 (底部深色陰影 + 頂部亮色屋頂)
function drawBuilding(x, y, bw, bh, height) {
  // 建築側面深色陰影
  ctx.fillStyle = '#b8cfb4';
  ctx.beginPath();
  ctx.moveTo(x, y + bh);
  ctx.lineTo(x + bw, y + bh);
  ctx.lineTo(x + bw, y + bh - height);
  ctx.lineTo(x, y + bh - height);
  ctx.fill();

  // 建築屋頂 (淺米灰色)
  ctx.fillStyle = '#f1efe8';
  ctx.strokeStyle = '#d7d4ca';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.rect(x, y - height, bw, bh);
  ctx.fill();
  ctx.stroke();
}

// 繪製 H3 迷霧遮罩
function drawH3Fog(cx, cy) {
  const hexRadius = 85;
  cells.forEach(cell => {
    // 簡單六角坐標投影
    const hx = cx + hexRadius * 1.5 * cell.q;
    const hy = cy + hexRadius * Math.sqrt(3) * (cell.r + cell.q / 2);

    if (cell.state === "UNSEEN") {
      ctx.fillStyle = 'rgba(30, 41, 59, 0.72)'; // 濃黑迷霧
      ctx.strokeStyle = 'rgba(51, 65, 85, 0.4)';
      drawHexagon(hx, hy, hexRadius);
    } else if (cell.state === "DISCOVERING") {
      ctx.fillStyle = 'rgba(51, 65, 85, 0.35)'; // 漸散半透明迷霧
      ctx.strokeStyle = 'rgba(59, 130, 246, 0.5)';
      drawHexagon(hx, hy, hexRadius);
    }
  });
}

function drawHexagon(x, y, r) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    const px = x + r * Math.cos(angle);
    const py = y + r * Math.sin(angle);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
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
