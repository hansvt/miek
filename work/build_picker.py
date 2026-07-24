"""Build a self-contained HTML landmark picker (pan/zoom/rotate) with both images embedded."""
import base64, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")


def b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


oct_src = os.path.join(OUT, "oct_enh.png")
imm_src = os.path.join(OUT, "imm_enh.png")
oct_b = b64(oct_src if os.path.exists(oct_src) else os.path.join(ROOT, "images", "2lindex_.jpg"))
imm_b = b64(imm_src if os.path.exists(imm_src) else os.path.join(ROOT, "images", "L2_index_mag_20sec_500.CR2.JPG"))

HTML = r"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<title>Landmark picker - OCT / immunolabel</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#111;color:#eee}
 header{padding:10px 14px;background:#1b1b1b;border-bottom:1px solid #333}
 h1{font-size:16px;margin:0 0 4px} .hint{font-size:13px;color:#bbb}
 #status{font-size:14px;font-weight:600;padding:6px 10px;border-radius:6px;display:inline-block;margin-top:6px}
 .wait-oct{background:#0a3d62} .wait-imm{background:#6a1b1b}
 .cols{display:flex;gap:8px;padding:8px;align-items:flex-start}
 .col{flex:1;min-width:0}
 .toolbar{display:flex;gap:6px;align-items:center;margin-bottom:4px;font-size:13px;flex-wrap:wrap}
 button{background:#2a2a2a;color:#eee;border:1px solid #444;border-radius:5px;padding:5px 9px;cursor:pointer}
 button:hover{background:#383838}
 input[type=range]{vertical-align:middle}
 .viewport{border:1px solid #333;overflow:hidden;height:74vh;background:#000;position:relative;cursor:grab;touch-action:none}
 .viewport.drag{cursor:grabbing}
 .imgwrap{position:absolute;top:0;left:0;transform-origin:0 0;will-change:transform}
 .imgwrap img{display:block;image-rendering:auto;-webkit-user-drag:none;user-select:none}
 .mk{position:absolute;width:16px;height:16px;margin:-8px 0 0 -8px;border:2px solid;border-radius:50%;
     box-sizing:border-box;pointer-events:none;transform-origin:center}
 .mk b{position:absolute;left:15px;top:-5px;font-size:12px;text-shadow:0 0 3px #000,0 0 3px #000,0 0 3px #000;white-space:nowrap}
 .oct .mk{border-color:#3cf;color:#3cf} .imm .mk{border-color:#f66;color:#f66}
 .mk.pend{border-style:dashed}
 table{border-collapse:collapse;font-size:12px;width:100%;margin-top:6px}
 td,th{border:1px solid #333;padding:2px 6px;text-align:center} th{background:#222}
 #out{width:100%;height:110px;background:#0a0a0a;color:#8f8;border:1px solid #333;font-family:monospace;font-size:12px}
 .foot{padding:8px 14px}
 .deg{width:44px;display:inline-block;text-align:right;color:#9cf}
</style></head><body>
<header>
 <h1>Landmark picker — klik corresponderende punten (OCT ↔ immunolabel)</h1>
 <div class="hint">Klik een herkenbaar punt in <b>OCT</b>, dan hetzelfde in <b>immunolabel</b>. 4–8 paren, goed verspreid.
   <b>Slepen</b> = pannen · <b>scroll-wiel</b> = zoomen · <b>draai-knoppen/schuif</b> = roteren (om de orientaties gelijk te leggen). Roteren/zoomen verandert alleen de weergave; geexporteerde coordinaten blijven in originele pixels.</div>
 <div id="status" class="wait-oct">Klik nu punt #1 in OCT (links)</div>
</header>
<div class="cols">
 <div class="col oct">
  <div class="toolbar"><b>OCT</b>
    <button onclick="zc('o',1.25)">＋</button><button onclick="zc('o',0.8)">－</button>
    <button onclick="fit('o')">passend</button>
    <span>| draai</span><button onclick="rot('o',-90)">⟲90</button><button onclick="rot('o',90)">⟳90</button>
    <input type="range" min="-180" max="180" value="0" id="rs_o" oninput="setRot('o',this.value)">
    <span class="deg" id="rl_o">0°</span><button onclick="setRot('o',0);setSlider('o',0)">reset</button></div>
  <div class="viewport" id="vp_o"><div class="imgwrap" id="wrap_o"><img id="img_o"></div></div>
 </div>
 <div class="col imm">
  <div class="toolbar"><b>immunolabel</b>
    <button onclick="zc('i',1.25)">＋</button><button onclick="zc('i',0.8)">－</button>
    <button onclick="fit('i')">passend</button>
    <span>| draai</span><button onclick="rot('i',-90)">⟲90</button><button onclick="rot('i',90)">⟳90</button>
    <input type="range" min="-180" max="180" value="0" id="rs_i" oninput="setRot('i',this.value)">
    <span class="deg" id="rl_i">0°</span><button onclick="setRot('i',0);setSlider('i',0)">reset</button></div>
  <div class="viewport" id="vp_i"><div class="imgwrap" id="wrap_i"><img id="img_i"></div></div>
 </div>
</div>
<div class="foot">
 <button onclick="undo()">↶ Laatste ongedaan</button>
 <button onclick="clearAll()">🗑 Alles wissen</button>
 <button onclick="exportJSON()">⤓ Exporteer JSON</button>
 <span class="hint">Kopieer de JSON hieronder en plak terug in de chat (of sla op als work/points.json).</span>
 <table id="tbl"><thead><tr><th>#</th><th>OCT x,y</th><th>immuno x,y</th></tr></thead><tbody></tbody></table>
 <textarea id="out" readonly></textarea>
</div>
<script>
const IMG={o:"data:image/png;base64,__OCT__",i:"data:image/png;base64,__IMM__"};
const nat={o:[0,0],i:[0,0]};
const view={o:{z:1,rot:0,tx:0,ty:0}, i:{z:1,rot:0,tx:0,ty:0}};
const pairs=[]; let expect='o'; let pending=null;
const el=id=>document.getElementById(id);

// ---- transform helpers ----
function matrix(s){const v=view[s];
  return new DOMMatrix().translateSelf(v.tx,v.ty).scaleSelf(v.z).rotateSelf(v.rot);}
function apply(s){const v=view[s];
  el('wrap_'+s).style.transform=`translate(${v.tx}px,${v.ty}px) scale(${v.z}) rotate(${v.rot}deg)`;
  render();}
function vpPoint(s,clientX,clientY){const r=el('vp_'+s).getBoundingClientRect();
  return new DOMPoint(clientX-r.left,clientY-r.top);}
function toNative(s,clientX,clientY){const p=vpPoint(s,clientX,clientY);
  const n=matrix(s).inverse().transformPoint(p);return [Math.round(n.x),Math.round(n.y)];}
function zoomAt(s,factor,clientX,clientY){const v=view[s];const p=vpPoint(s,clientX,clientY);
  const n=matrix(s).inverse().transformPoint(p);          // native under cursor
  v.z=Math.min(12,Math.max(0.03,v.z*factor));
  const M0=new DOMMatrix().scaleSelf(v.z).rotateSelf(v.rot);
  const w=M0.transformPoint(n); v.tx=p.x-w.x; v.ty=p.y-w.y; apply(s);}
function zc(s,f){const r=el('vp_'+s).getBoundingClientRect();zoomAt(s,f,r.left+r.width/2,r.top+r.height/2);}
function rotAround(s,newRot,clientX,clientY){const v=view[s];const p=vpPoint(s,clientX,clientY);
  const n=matrix(s).inverse().transformPoint(p); v.rot=newRot;
  const M0=new DOMMatrix().scaleSelf(v.z).rotateSelf(v.rot);
  const w=M0.transformPoint(n); v.tx=p.x-w.x; v.ty=p.y-w.y; apply(s);}
function rot(s,d){const r=el('vp_'+s).getBoundingClientRect();
  rotAround(s,view[s].rot+d,r.left+r.width/2,r.top+r.height/2);setSlider(s,view[s].rot);}
function setRot(s,val){const r=el('vp_'+s).getBoundingClientRect();
  rotAround(s,parseFloat(val),r.left+r.width/2,r.top+r.height/2);el('rl_'+s).textContent=Math.round(view[s].rot)+'°';}
function setSlider(s,val){let v=((val+180)%360+360)%360-180;el('rs_'+s).value=v;el('rl_'+s).textContent=Math.round(view[s].rot)+'°';}
function fit(s){const vp=el('vp_'+s);let W=vp.clientWidth,H=vp.clientHeight;if(!(W>20))W=700;if(!(H>20))H=500;
  const v=view[s];v.rot=0;setSlider(s,0);v.z=Math.max(0.03,Math.min(W/nat[s][0],H/nat[s][1])*0.97);
  v.tx=(W-nat[s][0]*v.z)/2; v.ty=(H-nat[s][1]*v.z)/2; apply(s);}

// ---- image + interaction wiring ----
for(const s of ['o','i']){
  const im=el('img_'+s); im.src=IMG[s];
  im.onload=()=>{nat[s]=[im.naturalWidth,im.naturalHeight];
     requestAnimationFrame(()=>requestAnimationFrame(()=>fit(s)));};
  const vp=el('vp_'+s);
  vp.addEventListener('wheel',ev=>{ev.preventDefault();zoomAt(s,ev.deltaY<0?1.15:1/1.15,ev.clientX,ev.clientY);},{passive:false});
  let down=null,moved=false;
  vp.addEventListener('mousedown',ev=>{down={x:ev.clientX,y:ev.clientY};moved=false;vp.classList.add('drag');});
  window.addEventListener('mousemove',ev=>{if(!down)return;const dx=ev.clientX-down.x,dy=ev.clientY-down.y;
     if(Math.abs(dx)+Math.abs(dy)>4)moved=true;
     view[s].tx+=ev.clientX-down.x; view[s].ty+=ev.clientY-down.y; down={x:ev.clientX,y:ev.clientY}; apply(s);});
  window.addEventListener('mouseup',ev=>{if(!down)return;const wasClick=!moved;const cx=ev.clientX,cy=ev.clientY;
     down=null;vp.classList.remove('drag');
     if(wasClick && document.elementFromPoint(cx,cy) && el('vp_'+s).contains(document.elementFromPoint(cx,cy))) click(s,cx,cy);});
}
function click(s,cx,cy){
  if(s!==expect){flash();return;}
  const xy=toNative(s,cx,cy);
  if(xy[0]<0||xy[1]<0||xy[0]>nat[s][0]||xy[1]>nat[s][1]){flashMsg('⚠ Buiten het beeld geklikt');return;}
  if(s=='o'){pending=xy;expect='i';}else{pairs.push({o:pending,i:xy});pending=null;expect='o';}
  setStatus();render();
}
function setStatus(){const st=el('status');
  if(expect=='o'){st.className='wait-oct';st.textContent='Klik nu punt #'+(pairs.length+1)+' in OCT (links)';}
  else{st.className='wait-imm';st.textContent='Klik nu HETZELFDE punt #'+(pairs.length+1)+' in immunolabel (rechts)';}}
function flash(){flashMsg('⚠ Klik in het andere beeld ('+(expect=='o'?'OCT':'immuno')+')');}
function flashMsg(m){const st=el('status');st.textContent=m;setTimeout(setStatus,1000);}
function render(){
  for(const s of ['o','i']){const w=el('wrap_'+s);[...w.querySelectorAll('.mk')].forEach(m=>m.remove());
    pairs.forEach((p,idx)=>addMk(s,p[s],idx+1,false));
    if(s=='o'&&pending)addMk('o',pending,pairs.length+1,true);}
  const tb=el('tbl').querySelector('tbody');tb.innerHTML='';
  pairs.forEach((p,i)=>{tb.insertRow().innerHTML=`<td>${i+1}</td><td>${p.o[0]}, ${p.o[1]}</td><td>${p.i[0]}, ${p.i[1]}</td>`;});}
function addMk(s,xy,n,pend){const v=view[s];const m=document.createElement('div');
  m.className='mk'+(pend?' pend':'');m.style.left=xy[0]+'px';m.style.top=xy[1]+'px';
  m.style.transform=`scale(${1/v.z}) rotate(${-v.rot}deg)`;   // keep constant size + upright
  m.innerHTML='<b>'+n+'</b>';el('wrap_'+s).appendChild(m);}
function undo(){if(pending){pending=null;expect='o';}else{pairs.pop();}setStatus();render();}
function clearAll(){pairs.length=0;pending=null;expect='o';setStatus();render();el('out').value='';}
function exportJSON(){const data={oct_image:"2lindex_.jpg",imm_image:"L2_index_mag_20sec_500.CR2.JPG",
   note:"coords in native full-image pixels",pairs:pairs};
  const js=JSON.stringify(data,null,2);el('out').value=js;
  try{const blob=new Blob([js],{type:'application/json'});const a=document.createElement('a');
    a.href=URL.createObjectURL(blob);a.download='points.json';a.click();}catch(e){}
  if(navigator.clipboard)navigator.clipboard.writeText(js);}
setStatus();
window.addEventListener('resize',()=>{for(const s of ['o','i'])if(nat[s][0])apply(s);});
window.addEventListener('load',()=>{for(const s of ['o','i'])if(nat[s][0])fit(s);});
</script></body></html>"""

HTML = HTML.replace("__OCT__", oct_b).replace("__IMM__", imm_b)
path = os.path.join(ROOT, "point_picker.html")
with open(path, "w", encoding="utf-8") as f:
    f.write(HTML)
print("wrote", path, "size(MB)=%.1f" % (len(HTML) / 1e6))
