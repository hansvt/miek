"""Interactive overlay viewer (WI-8): pan/zoom/rotate the registered composite with a
cross-fade opacity slider between the two aligned layers (warped OCT ↔ immunolabel).
Self-contained HTML (images base64-embedded); opens by double-click. Built from the
aligned crops `layer_oct.png` / `layer_imm.png` written by analyze._save_overlay."""
import os
import base64

_TEMPLATE = r"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<title>Overlay viewer — OCT / immunolabel</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;margin:0;background:#111;color:#eee}
 header{padding:8px 14px;background:#1b1b1b;border-bottom:1px solid #333;display:flex;
        gap:14px;align-items:center;flex-wrap:wrap}
 button{background:#2a2a2a;color:#eee;border:1px solid #444;border-radius:5px;padding:5px 9px;cursor:pointer}
 button:hover{background:#383838}
 label{font-size:13px;color:#ccc}
 .viewport{position:absolute;top:52px;left:0;right:0;bottom:0;overflow:hidden;background:#000;cursor:grab}
 .viewport.drag{cursor:grabbing}
 .wrap{position:absolute;top:0;left:0;transform-origin:0 0}
 .wrap img{position:absolute;top:0;left:0;display:block;image-rendering:auto}
 #imm{filter:none}
</style></head><body>
<header>
 <b>Overlay viewer</b>
 <button onclick="zc(1.25)">+</button><button onclick="zc(0.8)">−</button>
 <button onclick="fit()">passend</button>
 <button onclick="rot(-90)">⟲90</button><button onclick="rot(90)">⟳90</button>
 <input type="range" min="-180" max="180" value="0" id="rs" oninput="setRot(this.value)">
 <span id="rl" style="color:#9cf">0°</span>
 <label>OCT ⟷ immuno&nbsp;<input type="range" min="0" max="100" value="50" id="op" oninput="setOp()"></label>
 <label><input type="checkbox" id="cOCT" checked onchange="setOp()"> OCT</label>
 <label><input type="checkbox" id="cIMM" checked onchange="setOp()"> immuno</label>
 <span class="hint" style="color:#888;font-size:12px">slepen=pannen · wiel=zoomen · magenta=OCT, groen=immuno</span>
</header>
<div class="viewport" id="vp"><div class="wrap" id="wrap">
  <img id="imm" src="data:image/png;base64,__IMM__">
  <img id="oct" src="data:image/png;base64,__OCT__">
</div></div>
<script>
const nat=[0,0]; let z=1,rot=0,tx=0,ty=0;
const el=id=>document.getElementById(id);
function matrix(){return new DOMMatrix().translateSelf(tx,ty).scaleSelf(z).rotateSelf(rot);}
function apply(){el('wrap').style.transform=`translate(${tx}px,${ty}px) scale(${z}) rotate(${rot}deg)`;}
function vp(cx,cy){const r=el('vp').getBoundingClientRect();return new DOMPoint(cx-r.left,cy-r.top);}
function zoomAt(f,cx,cy){const p=vp(cx,cy);const n=matrix().inverse().transformPoint(p);
  z=Math.min(16,Math.max(0.03,z*f));const M0=new DOMMatrix().scaleSelf(z).rotateSelf(rot);
  const w=M0.transformPoint(n);tx=p.x-w.x;ty=p.y-w.y;apply();}
function zc(f){const r=el('vp').getBoundingClientRect();zoomAt(f,r.left+r.width/2,r.top+r.height/2);}
function rotAround(nr,cx,cy){const p=vp(cx,cy);const n=matrix().inverse().transformPoint(p);rot=nr;
  const M0=new DOMMatrix().scaleSelf(z).rotateSelf(rot);const w=M0.transformPoint(n);tx=p.x-w.x;ty=p.y-w.y;apply();}
function rot90(d){const r=el('vp').getBoundingClientRect();rotAround(rot+d,r.left+r.width/2,r.top+r.height/2);
  el('rs').value=((rot+180)%360+360)%360-180;el('rl').textContent=Math.round(rot)+'°';}
window.rot=rot90;
function setRot(v){const r=el('vp').getBoundingClientRect();rotAround(parseFloat(v),r.left+r.width/2,r.top+r.height/2);
  el('rl').textContent=Math.round(rot)+'°';}
function fit(){const r=el('vp').getBoundingClientRect();let W=r.width,H=r.height;if(!(W>20))W=800;if(!(H>20))H=600;
  rot=0;el('rs').value=0;el('rl').textContent='0°';z=Math.max(0.03,Math.min(W/nat[0],H/nat[1])*0.97);
  tx=(W-nat[0]*z)/2;ty=(H-nat[1]*z)/2;apply();}
function setOp(){const s=el('op').value/100;
  el('oct').style.opacity=el('cOCT').checked? s:0;
  el('imm').style.opacity=el('cIMM').checked? (1-s):0;}
// tint layers: OCT->magenta, immuno->green (via CSS blend on grayscale sources)
el('oct').style.mixBlendMode='screen'; el('imm').style.mixBlendMode='screen';
el('oct').style.filter='brightness(1) sepia(1) hue-rotate(260deg) saturate(6)';
el('imm').style.filter='brightness(1) sepia(1) hue-rotate(60deg) saturate(4)';
const im=el('imm');
function init(){nat[0]=im.naturalWidth;nat[1]=im.naturalHeight;
  requestAnimationFrame(()=>requestAnimationFrame(fit));setOp();}
im.onload=init;
if(im.complete && im.naturalWidth) requestAnimationFrame(init);
const vpo=el('vp');
vpo.addEventListener('wheel',e=>{e.preventDefault();zoomAt(e.deltaY<0?1.15:1/1.15,e.clientX,e.clientY);},{passive:false});
let down=null;
vpo.addEventListener('mousedown',e=>{down={x:e.clientX,y:e.clientY};vpo.classList.add('drag');});
window.addEventListener('mousemove',e=>{if(!down)return;tx+=e.clientX-down.x;ty+=e.clientY-down.y;down={x:e.clientX,y:e.clientY};apply();});
window.addEventListener('mouseup',()=>{down=null;vpo.classList.remove('drag');});
window.addEventListener('resize',apply);
</script></body></html>"""


def _b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def build(out_dir):
    lo = os.path.join(out_dir, "layer_oct.png")
    li = os.path.join(out_dir, "layer_imm.png")
    if not (os.path.exists(lo) and os.path.exists(li)):
        return None
    html = (_TEMPLATE.replace("__OCT__", _b64(lo)).replace("__IMM__", _b64(li)))
    path = os.path.join(out_dir, "overlay_viewer.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
