"""WI-E — manual curation of immuno pore detection (safety net). Self-contained HTML:
shows the optimised immuno image with auto-detected centroids; click a pore to remove it,
click empty space to add one; pan/zoom/rotate; export the curated set as JSON. Feed back
into analysis via `porepair analyze --imm-points curated_points.json`."""
import os
import json
import base64
import cv2

_TEMPLATE = r"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<title>Immuno curator — poriën bijwerken</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#111;color:#eee}
 header{padding:8px 14px;background:#1b1b1b;border-bottom:1px solid #333;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
 button{background:#2a2a2a;color:#eee;border:1px solid #444;border-radius:5px;padding:5px 9px;cursor:pointer}
 button:hover{background:#383838} button.on{background:#0a3d62;border-color:#2a7}
 label{font-size:13px;color:#ccc}
 .viewport{position:absolute;top:52px;left:0;right:0;bottom:0;overflow:hidden;background:#000;cursor:crosshair}
 .viewport.pan{cursor:grab} .viewport.pan.drag{cursor:grabbing}
 .wrap{position:absolute;top:0;left:0;transform-origin:0 0}
 .wrap img{display:block}
 .mk{position:absolute;width:12px;height:12px;margin:-6px 0 0 -6px;border:2px solid #2d2;border-radius:50%;box-sizing:border-box;pointer-events:none;transform-origin:center}
 .mk.rm{border-color:#f44;border-style:dashed}
 .mk.add{border-color:#3cf}
</style></head><body>
<header>
 <b>Immuno curator</b>
 <button id="bMode" class="on" onclick="toggleMode()">modus: verwijderen</button>
 <label>(klik porie = verwijderen · lege plek = toevoegen; knop wisselt primaire actie)</label>
 <button onclick="undo()">↶ undo</button>
 <button onclick="resetAll()">reset naar auto</button>
 <button onclick="zc(1.25)">+</button><button onclick="zc(0.8)">−</button><button onclick="fit()">passend</button>
 <button onclick="rot(90)">⟳90</button>
 <span id="count" style="color:#9cf"></span>
 <button onclick="exportJSON()">⤓ exporteer</button>
</header>
<div class="viewport pan" id="vp"><div class="wrap" id="wrap"><img id="img"></div></div>
<textarea id="out" style="position:absolute;bottom:0;left:0;width:60%;height:60px;display:none"></textarea>
<script>
const IMG="data:image/png;base64,__IMG__";
const AUTO=__PTS__;               // [[x,y],...] auto-detected (image px)
let pts=AUTO.map(p=>p.slice());
const nat=[0,0]; let z=1,rot=0,tx=0,ty=0; let removeMode=true;
const hist=[];
const el=id=>document.getElementById(id);
function M(){return new DOMMatrix().translateSelf(tx,ty).scaleSelf(z).rotateSelf(rot);}
function apply(){el('wrap').style.transform=`translate(${tx}px,${ty}px) scale(${z}) rotate(${rot}deg)`;render();}
function vp(cx,cy){const r=el('vp').getBoundingClientRect();return new DOMPoint(cx-r.left,cy-r.top);}
function toImg(cx,cy){const n=M().inverse().transformPoint(vp(cx,cy));return [n.x,n.y];}
function zoomAt(f,cx,cy){const p=vp(cx,cy);const n=M().inverse().transformPoint(p);
  z=Math.min(16,Math.max(0.03,z*f));const M0=new DOMMatrix().scaleSelf(z).rotateSelf(rot);
  const w=M0.transformPoint(n);tx=p.x-w.x;ty=p.y-w.y;apply();}
function zc(f){const r=el('vp').getBoundingClientRect();zoomAt(f,r.left+r.width/2,r.top+r.height/2);}
function rot90(d){const r=el('vp').getBoundingClientRect();const c=vp(r.left+r.width/2,r.top+r.height/2);
  const n=M().inverse().transformPoint(c);rot+=d;const M0=new DOMMatrix().scaleSelf(z).rotateSelf(rot);
  const w=M0.transformPoint(n);tx=c.x-w.x;ty=c.y-w.y;apply();}
window.rot=rot90;
function fit(){const r=el('vp').getBoundingClientRect();let W=r.width,H=r.height;if(!(W>20))W=800;if(!(H>20))H=600;
  rot=0;z=Math.max(0.03,Math.min(W/nat[0],H/nat[1])*0.97);tx=(W-nat[0]*z)/2;ty=(H-nat[1]*z)/2;apply();}
function toggleMode(){removeMode=!removeMode;el('bMode').textContent='modus: '+(removeMode?'verwijderen':'toevoegen');
  el('bMode').classList.toggle('on',removeMode);}
function nearest(x,y){let bi=-1,bd=1e9;for(let i=0;i<pts.length;i++){const dx=pts[i][0]-x,dy=pts[i][1]-y;const d=dx*dx+dy*dy;if(d<bd){bd=d;bi=i;}}return[bi,Math.sqrt(bd)];}
function render(){const w=el('wrap');[...w.querySelectorAll('.mk')].forEach(m=>m.remove());
  for(const p of pts){const m=document.createElement('div');m.className='mk';
    m.style.left=p[0]+'px';m.style.top=p[1]+'px';m.style.transform=`scale(${1/z}) rotate(${-rot}deg)`;w.appendChild(m);}
  el('count').textContent=pts.length+' poriën (auto '+AUTO.length+')';}
const im=el('img');
function init(){nat[0]=im.naturalWidth;nat[1]=im.naturalHeight;requestAnimationFrame(()=>requestAnimationFrame(fit));}
im.onload=init;im.src=IMG;if(im.complete&&im.naturalWidth)requestAnimationFrame(init);
const vpo=el('vp');let down=null,moved=false;
vpo.addEventListener('wheel',e=>{e.preventDefault();zoomAt(e.deltaY<0?1.15:1/1.15,e.clientX,e.clientY);},{passive:false});
vpo.addEventListener('mousedown',e=>{down={x:e.clientX,y:e.clientY};moved=false;});
window.addEventListener('mousemove',e=>{if(!down)return;if(Math.abs(e.clientX-down.x)+Math.abs(e.clientY-down.y)>4){moved=true;
  tx+=e.clientX-down.x;ty+=e.clientY-down.y;down={x:e.clientX,y:e.clientY};apply();}});
window.addEventListener('mouseup',e=>{const wasClick=down&&!moved;down=null;if(!wasClick)return;
  const [x,y]=toImg(e.clientX,e.clientY);if(x<0||y<0||x>nat[0]||y>nat[1])return;
  const [bi,bd]=nearest(x,y);const tol=Math.max(6,0.5*Math.sqrt(nat[0]*nat[1]/Math.max(pts.length,1))/2);
  if(removeMode){ if(bi>=0&&bd<tol){hist.push(['add',pts[bi].slice(),bi]);pts.splice(bi,1);} }
  else{ hist.push(['rm',null,pts.length]);pts.push([Math.round(x),Math.round(y)]); }
  render();});
function undo(){const h=hist.pop();if(!h)return;if(h[0]==='add')pts.splice(h[2],0,h[1]);else pts.pop();render();}
function resetAll(){pts=AUTO.map(p=>p.slice());hist.length=0;render();}
function exportJSON(){const data={imm_image:"__NAME__",note:"curated immuno pore centroids, native px [x,y]",points:pts};
  const js=JSON.stringify(data);const t=el('out');t.style.display='block';t.value=js;
  try{const b=new Blob([js],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='curated_points.json';a.click();}catch(e){}
  if(navigator.clipboard)navigator.clipboard.writeText(js);}
window.addEventListener('resize',apply);
</script></body></html>"""


def build(out_dir, imm_name="immuno"):
    opt = os.path.join(out_dir, "imm_optimized.png")
    base = opt if os.path.exists(opt) else os.path.join(out_dir, "imm_enh.png")
    pts_path = os.path.join(out_dir, "imm_pts.npy")
    if not (os.path.exists(base) and os.path.exists(pts_path)):
        return None
    import numpy as np
    pts = np.load(pts_path)[:, ::-1]          # (y,x) -> [x,y]
    pts_json = json.dumps([[int(round(x)), int(round(y))] for x, y in pts])
    with open(base, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    html = (_TEMPLATE.replace("__IMG__", b64).replace("__PTS__", pts_json)
            .replace("__NAME__", imm_name))
    path = os.path.join(out_dir, "imm_curator.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
