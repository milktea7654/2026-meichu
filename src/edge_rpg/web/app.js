let state, selectedTable='events', activePage='game', busy=false;
const $=id=>document.getElementById(id);
const esc=v=>String(v??'NULL').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names={DISCOVERY:'探索發現',NPC_ENCOUNTER:'NPC 相遇',RESOURCE:'資源',QUEST:'任務',COMBAT:'戰鬥',LANDMARK:'地標',REST:'休息',RARE:'稀有事件'};
const statuses={GPS_BOUNDARY:'位於格線附近 · 等待更明確的位置',DISCOVERING:'正在探索 · 尚未建立事件',KNOWN_AREA:'已探索 · 保留既有故事',WAIT_FOR_SCENE:'等待有效的相機觀察',INDOOR_GUARD:'室內保護 · 不生成事件',GPS_INVALID_ACCURACY:'GPS 精度不足 · 探索暫停',GPS_WARNING:'GPS 無效 · 探索暫停',GPS_STALE:'GPS 中斷 · 探索暫停',GPS_DISCONNECTED:'GPS 已斷線',WAIT_FOR_PHONE_GPS:'等待裝置 GPS 定位',GPS_DISPLAY_ONLY:'GPS 僅供顯示',SAFE_IDLE:'目前區域不可探索'};
const pct=x=>Math.round(x*100)+'%';
function openPage(page){activePage=page;document.querySelectorAll('.page').forEach(e=>e.classList.toggle('active',e.id===page));document.querySelectorAll('.tab').forEach(e=>e.classList.toggle('active',e.dataset.page===page));if(page==='game')requestAnimationFrame(drawMap);}
async function fetchState(){try{let r=await fetch('/api/state');if(!r.ok)throw Error('讀取世界失敗');state=await r.json();render();}catch(e){showError(e.message);}}
function showError(text){$('error').textContent=text;$('error').hidden=false;setTimeout(()=>$('error').hidden=true,6000);}
async function act(action,value){if(busy)return;busy=true;$('walk').disabled=true;try{const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,value})});const data=await r.json();if(!r.ok)throw Error(data.error||'操作失敗');state=data;render();}catch(e){showError(e.message);}finally{busy=false;$('walk').disabled=state?.mode!=='simulation';}}
function render(){
 $('player-stats').textContent=`HP ${state.player.hp} · XP ${state.player.xp}`;
 $('condition').value=state.condition;
 $('gps-mode').value=state.mode;
 for(const id of ['walk','back','condition'])$(id).disabled=state.mode!=='simulation';
 document.querySelector('.map-tag').textContent=`${state.cell_size_m**2} m² / 格`;
 document.querySelectorAll('[data-zone]').forEach(b=>b.disabled=state.mode!=='simulation');
 const saved=new Map(state.tables.map_cells.map(c=>[c.cell_id,c]));
 $('zones').innerHTML=state.zones.map((z,i)=>`<button ${state.mode!=='simulation'?'disabled':''} class="zone ${z.id===state.zone?'active':''}" data-zone="${z.id}"><span class="zone-icon">${['♧','≈','⌂','♜'][i]}</span><span><strong>${esc(z.name)}</strong><small>${saved.get(z.cell)?.state==='EXPLORED'?'已探索 · 故事已保存':saved.has(z.cell)?'探索進行中':'未知區域'}</small></span><span class="arrow">${z.id===state.zone?'↗':'·'}</span></button>`).join('');
 $('current-zone').textContent=state.mode==='simulation'?'模擬足跡':'GPS 探索足跡';
 const t=state.totals, progress=t.pending/t.target;
 $('progress').textContent=t.pending;$('progress-fill').style.width=pct(progress);
 $('components').innerHTML=`<div>永久點亮<b>${t.visited} 格</b></div><div>探索面積<b>${t.visited*state.cell_size_m**2} m²</b></div><div>已觸發<b>${t.events_created} 次</b></div><div>距下次事件<b>${t.target-t.pending} 格</b></div>`;
 document.querySelector('.threshold').textContent=` / ${t.target} 個新格觸發 EVENT`;document.querySelector('.progress-track>span').style.left='100%';
 $('status').textContent=statuses[state.status]||state.status;
 $('story-title').textContent=state.story.title;$('story-text').textContent=state.story.text;$('message').textContent=state.message;
 $('event-label').textContent=state.event?names[state.event.type]:'尚待發現';
 $('story-kicker').textContent=state.event?'A STORY TO REMEMBER':'THE UNWRITTEN PATH';
 const q=state.quest;
 $('quest-name').textContent=q?'遺失的護符':'尚未接下任務';
 $('quest-hint').textContent=!q?'新的相遇，往往就在下一段路上。':q.state==='COMPLETED'?`✓ 任務完成 · 獲得 ${state.quest_xp} XP`:q.state==='AVAILABLE'?'與旅人交談，決定是否幫忙。':q.stage===1?'已找到護符，與旅人交談交付。':'任務進行中：調查這個區域。';
 $('bag').innerHTML=state.tables.inventory.filter(i=>i.quantity>0).map(i=>`<div class="bag-item">◇ ${i.item_id==='lost_charm'?'旅人的護符':'步道藥草'} × ${i.quantity}</div>`).join('')||'<div class="bag-item">◇ 背包目前是空的</div>';
 document.querySelectorAll('[data-command]').forEach(b=>{let k=b.dataset.command;b.disabled=k==='TALK'?!state.npc:k==='ACCEPT'||k==='REFUSE'?!q||q.state!=='AVAILABLE':k==='INSPECT'?!state.event||state.event.status!=='ACTIVE'||(!!q&&(q.state!=='ACTIVE'||q.stage!==0)):false;});
 $('journal').innerHTML=state.tables.event_log.slice(0,3).map(log=>`<p><time>${new Date(log.timestamp*1000).toLocaleTimeString('zh-TW',{hour:'2-digit',minute:'2-digit'})}</time>${esc(log.event_type==='EXPLORE'?'抵達新的探索區域':log.event_type==='EVENT'?'觸發事件：'+(names[log.message.split(':')[0]]||log.message):translateLog(log.message))}</p>`).join('')||'<p>你的探索手記，從這裡開始。</p>';
 $('save-state').textContent=`SQLite 已同步 · ${state.counts.events} 個事件 · ${state.counts.quests} 個任務`;
 renderDatabase();renderGenerator();requestAnimationFrame(drawMap);
}
function translateLog(s){return {'Quest accepted. Investigate here on the permitted path.':'接受任務：遺失的護符','You found a charm. Talk to the traveler to return it.':'找到護符，已加入背包','Charm returned. Quest complete! +50 XP.':'護符交付完成 · +50 XP','I lost my charm here. Will you help me look?':'與旅人交談','Thank you for helping.':'旅人向你道謝'}[s]||s;}
function renderDatabase(){
 $('db-stats').innerHTML=[['探索區域','map_cells'],['已建立事件','events'],['世界角色','npcs'],['任務紀錄','quests']].map(([name,table])=>`<div>${name}<strong>${state.counts[table]}</strong></div>`).join('');
 $('tables').innerHTML=Object.keys(state.tables).map(t=>`<button class="${t===selectedTable?'active':''}" data-table="${t}">${t}<span>${state.counts[t]}</span></button>`).join('');
 const rows=state.tables[selectedTable],cols=Object.keys(rows[0]||{});
 $('table-name').textContent=selectedTable;$('row-count').textContent=`${state.counts[selectedTable]} 筆資料`;
 $('sql').textContent=`SELECT * FROM ${selectedTable} ORDER BY rowid DESC LIMIT 100;`;
 $('table-head').innerHTML='<tr>'+cols.map(c=>`<th>${esc(c)}</th>`).join('')+'</tr>';
 $('table-body').innerHTML=rows.map((r,index)=>'<tr data-row="'+index+'" tabindex="0">'+cols.map(c=>`<td title="${esc(r[c])}">${esc(r[c])}</td>`).join('')+'</tr>').join('');
 $('empty-table').hidden=rows.length>0;
 $('row-detail').textContent=rows.length?JSON.stringify(expandRow(rows[0]),null,2):'此表目前沒有資料。';
 $('db-path').textContent=state.database;
}
function expandRow(row){return Object.fromEntries(Object.entries(row).map(([key,value])=>{if(typeof value==='string'&&(key.endsWith('_json')||key==='rewards')){try{value=JSON.parse(value);}catch{}}return[key,value];}));}
function renderGenerator(){
 const g=state.generator;$('observation-note').textContent=g.observation_note;$('observation').textContent=JSON.stringify(g.observation,null,2)||'尚無有效觀察';$('context').textContent=JSON.stringify(g.context,null,2);
 $('weights').innerHTML=Object.entries(g.weights).map(([type,weight])=>`<div class="weight"><span>${names[type]}</span><div><i style="width:${weight*2}%"></i></div><span>${weight}%</span></div>`).join('');
 $('seed').textContent=`world_seed = ${g.seed}\nseed = SHA-256(world_seed + ':' + cell_id)\n${g.hash.slice(0,28)}…\n候選事件：${names[g.candidate]}`;
 $('generated-title').textContent=state.event?'已保存：'+state.story.title:'尚未達到事件建立條件';
 $('generated-description').textContent=state.event?'這段事件來自 SQLite 的既有紀錄。畫面敘述依事件類型與任務階段選用模板，不重新抽選，也不改寫世界事實。':`候選結果只是解說。只有有效 GPS 首次進入新格，累積達 ${state.threshold} 格時，World 才會建立並儲存事件；沒有相機也能觸發。`;
 $('generated-event').textContent=JSON.stringify(g.existing?expandRow(g.existing):{state:'WAITING',new_cells:state.totals.pending,threshold:state.threshold,candidate_only:g.candidate,backend:g.backend},null,2);
}
const tileCache=new Map();
function drawMap(){
 if(!state||activePage!=='game')return;
 const canvas=$('map'),ctx=canvas.getContext('2d'),w=canvas.clientWidth,h=canvas.clientHeight,dpr=window.devicePixelRatio||1;
 canvas.width=w*dpr;canvas.height=h*dpr;ctx.scale(dpr,dpr);
 const zoom=18,n=2**zoom,worldSize=256*n;
 const project=([lat,lon])=>{const sin=Math.sin(Math.max(-85.05,Math.min(85.05,lat))*Math.PI/180);return[(lon+180)/360*worldSize,(.5-Math.log((1+sin)/(1-sin))/(4*Math.PI))*worldSize];};
 const root=state.position||state.zones[0].center,[cx,cy]=project(root);
 const xy=p=>{const[x,y]=project(p);return[w/2+x-cx,h/2+y-cy];};
 ctx.fillStyle='#e5eadb';ctx.fillRect(0,0,w,h);
 let failed=false,loaded=false;
 for(let tx=Math.floor((cx-w/2)/256);tx<=Math.floor((cx+w/2)/256);tx++)for(let ty=Math.floor((cy-h/2)/256);ty<=Math.floor((cy+h/2)/256);ty++){
  const x=((tx%n)+n)%n,key=`${zoom}/${x}/${ty}`;if(ty<0||ty>=n)continue;
  if(!tileCache.has(key)){const img=new Image();tileCache.set(key,img);img.onload=()=>requestAnimationFrame(drawMap);img.onerror=()=>{img.failed=true;requestAnimationFrame(drawMap);};img.src=`https://tile.openstreetmap.org/${key}.png`;if(tileCache.size>128)tileCache.delete(tileCache.keys().next().value);}
  const img=tileCache.get(key);if(img?.complete&&img.naturalWidth){ctx.drawImage(img,tx*256-cx+w/2,ty*256-cy+h/2,256,256);loaded=true;}else if(img?.failed)failed=true;
 }
 $('tile-status').textContent=failed?'底圖載入失敗；GPS 與格網存檔仍可運作。':loaded?'':'正在載入 OpenStreetMap 真實底圖…';
 for(const c of state.cells){const pts=c.boundary.map(xy);ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();const lit=c.saved?.state==='EXPLORED';ctx.fillStyle=lit?'#8bca5b22':'#263d43a6';ctx.fill();ctx.strokeStyle=lit?'#b9e37bcc':'#a5b9b35a';ctx.lineWidth=lit?1.7:.6;ctx.stroke();if(c.saved?.event_id){const[x,y]=xy(c.center);ctx.fillStyle='#f4ca66';ctx.beginPath();ctx.arc(x,y,8,0,Math.PI*2);ctx.fill();ctx.fillStyle='#394532';ctx.font='bold 12px sans-serif';ctx.textAlign='center';ctx.fillText('!',x,y+4);}}
 if(state.position){const[x,y]=xy(state.position);ctx.fillStyle='#79c9f42e';ctx.beginPath();ctx.arc(x,y,20,0,Math.PI*2);ctx.fill();ctx.strokeStyle='#fff';ctx.lineWidth=3;ctx.fillStyle='#339cc2';ctx.beginPath();ctx.arc(x,y,7,0,Math.PI*2);ctx.fill();ctx.stroke();}
}
let gpsWatch=null;
$('gps-mode').onchange=async e=>{
 const mode=e.target.value;if(gpsWatch!==null){navigator.geolocation.clearWatch(gpsWatch);gpsWatch=null;}
 await act('mode',mode);
 if(mode==='browser'){
  if(!window.isSecureContext||!navigator.geolocation){showError('裝置 GPS 需要 HTTPS 或本機 localhost；也可改用 Android GPS Bridge。');return;}
  gpsWatch=navigator.geolocation.watchPosition(p=>act('gps',{type:'location',latitude:p.coords.latitude,longitude:p.coords.longitude,accuracy_m:p.coords.accuracy,speed_mps:p.coords.speed??0,timestamp_ms:p.timestamp}),e=>showError(`定位失敗：${e.message}`),{enableHighAccuracy:true,maximumAge:0,timeout:10000});
 }
};
setInterval(()=>{if(state?.mode!=='simulation'&&!busy)fetchState();},2000);
document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b||b.disabled)return;if(b.dataset.page)openPage(b.dataset.page);if(b.dataset.open)openPage(b.dataset.open);if(b.dataset.zone)act('zone',b.dataset.zone);if(b.dataset.command)act('command',b.dataset.command);if(b.dataset.table){selectedTable=b.dataset.table;renderDatabase();}});
function selectRow(e){const row=e.target.closest('tr[data-row]');if(row)$('row-detail').textContent=JSON.stringify(expandRow(state.tables[selectedTable][Number(row.dataset.row)]),null,2);}
$('table-body').addEventListener('click',selectRow);$('table-body').addEventListener('keydown',e=>{if(e.key==='Enter')selectRow(e);});
$('walk').onclick=()=>act('walk');$('back').onclick=()=>act('back');$('reload').onclick=fetchState;$('condition').onchange=e=>act('condition',e.target.value);window.addEventListener('resize',drawMap);fetchState();
