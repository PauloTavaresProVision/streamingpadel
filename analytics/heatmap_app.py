#!/usr/bin/env python3
"""
Mini-app de ANÁLISE (heatmap de jogadores) — ISOLADA da app de streaming.

Corre na porta 8001 (a de streaming é a 8000). Se isto crashar, o streaming
dos jogos NÃO é afetado.

Fase 1 — esta entrega:
  - snapshot da câmara (para calibrar)
  - página de calibração: clicas o contorno do court; guarda o polígono
  - guarda/lê a config em analytics/config.json

(o motor de deteção + heatmap entram a seguir, depois de validares a calibração)

Arranque no Jetson:
    source ~/analytics-venv/bin/activate
    cd ~/streamingpadel
    python analytics/heatmap_app.py --ip 192.168.88.201 --user admin --password 'P@ssw0rd1535'
    # abre  http://10.11.1.71:8001/
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from typing import List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
import uvicorn

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
OUT_DIR = os.path.join(HERE, "out")
os.makedirs(OUT_DIR, exist_ok=True)

# Preenchido a partir dos args no arranque.
CAM = {"ip": "", "user": "admin", "password": "", "path": "/Streaming/Channels/101"}


def _rtsp() -> str:
    u = quote(CAM["user"] or "", safe="")
    p = quote(CAM["password"] or "", safe="")
    path = CAM["path"]
    if not path.startswith("/"):
        path = "/" + path
    return f"rtsp://{u}:{p}@{CAM['ip']}{path}"


def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"court_corners": [], "court_polygon": []}


def _save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _which(bin_name: str) -> bool:
    from shutil import which
    return which(bin_name) is not None


def _grab_snapshot_jpeg() -> Optional[bytes]:
    """Tira 1 frame da câmara → JPEG. Tenta ffmpeg; se não existir/falhar, usa
    gst-launch (o Jetson tem-no de certeza, é o que o streaming usa). Sem IA."""
    out = os.path.join(OUT_DIR, "calib_snapshot.jpg")
    try:
        if os.path.exists(out):
            os.remove(out)
    except Exception:
        pass
    rtsp = _rtsp()
    attempts = []

    if _which("ffmpeg"):
        attempts.append([
            "ffmpeg", "-y", "-rtsp_transport", "tcp", "-i", rtsp,
            "-frames:v", "1", "-q:v", "2", out,
        ])
    # Alternativa GStreamer (decode HW + JPEG). num-buffers=1 vai no rtspsrc (1 frame).
    # Tenta h264 e h265 — a câmara pode ser qualquer um.
    if _which("gst-launch-1.0"):
        for depay, parse in (("rtph264depay", "h264parse"), ("rtph265depay", "h265parse")):
            attempts.append([
                "gst-launch-1.0", "-e",
                "rtspsrc", f"location={rtsp}", "protocols=tcp", "latency=300", "num-buffers=1", "!",
                depay, "!", parse, "!", "nvv4l2decoder", "!",
                "nvvidconv", "!", "video/x-raw,format=I420", "!",
                "jpegenc", "!", "filesink", f"location={out}",
            ])

    if not attempts:
        print("[snapshot] ERRO: nem ffmpeg nem gst-launch-1.0 encontrados no PATH.")
        return None

    for cmd in attempts:
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=25, text=True)
            if os.path.exists(out) and os.path.getsize(out) > 1024:
                with open(out, "rb") as f:
                    return f.read()
            # falhou: mostra as últimas linhas do erro real
            tail = "\n".join((r.stdout or "").strip().splitlines()[-6:])
            print(f"[snapshot] '{cmd[0]}' não gerou imagem. Saída:\n{tail}\n")
        except Exception as e:
            print(f"[snapshot] '{cmd[0]}' rebentou: {e}")
    return None


app = FastAPI(title="padel-analytics", version="0.1.0")


@app.get("/api/snapshot")
def snapshot():
    data = _grab_snapshot_jpeg()
    if not data:
        raise HTTPException(503, "Não consegui capturar a câmara (ver IP/credenciais).")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/config")
def get_config():
    return _load_config()


class CalibIn(BaseModel):
    # 4 cantos do court, por ordem: fundo-esq, fundo-dir, frente-dir, frente-esq.
    # Fracções 0..1 da imagem. Usados para a homografia (vista de cima).
    court_corners: List[List[float]]


@app.post("/api/config")
def set_config(data: CalibIn):
    if len(data.court_corners) != 4:
        raise HTTPException(400, "São precisos exatamente 4 cantos.")
    cfg = _load_config()
    cfg["court_corners"] = data.court_corners
    # mantém também o polígono (= os 4 cantos) para a máscara "dentro do court".
    cfg["court_polygon"] = data.court_corners
    _save_config(cfg)
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return _PAGE


# ─────────────────────────── UI (página única, sem build) ───────────────────────────
_PAGE = """<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Calibração do court — Padel Analytics</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,Segoe UI,Arial}
  header{padding:16px 20px;border-bottom:1px solid #1e293b}
  h1{margin:0;font-size:18px}
  p{color:#94a3b8;font-size:13px;margin:6px 0 0}
  .wrap{padding:20px;max-width:1280px;margin:0 auto}
  .row{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}
  .stage{position:relative;display:inline-block;border:1px solid #1e293b;border-radius:10px;overflow:hidden;flex:1;min-width:520px}
  #img{display:block;width:100%;height:auto}
  svg{position:absolute;inset:0;width:100%;height:100%}
  .side{width:300px}
  .prevbox{border:1px solid #1e293b;border-radius:10px;padding:10px;background:#0b1220}
  #prevcanvas{width:100%;height:auto;border-radius:6px;background:#020617;display:block}
  .step{display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:8px;margin:5px 0;font-size:13px;background:#1e293b}
  .step.done{background:#064e3b;color:#a7f3d0}
  .step.cur{outline:2px solid #2dd4bf}
  .num{display:inline-flex;width:22px;height:22px;border-radius:50%;background:#0d9488;color:#fff;align-items:center;justify-content:center;font-weight:700;font-size:12px;flex-shrink:0}
  .bar{display:flex;gap:10px;align-items:center;margin:14px 0;flex-wrap:wrap}
  button{background:#0d9488;color:#fff;border:0;padding:9px 16px;border-radius:8px;cursor:pointer;font-size:14px}
  button.sec{background:#334155}
  button:disabled{opacity:.5;cursor:default}
  .hint{color:#94a3b8;font-size:13px}
  .ok{color:#34d399}.err{color:#f87171}
  .dot{fill:#2dd4bf;stroke:#0f172a;stroke-width:2}
  .lbl{fill:#fff;font-size:15px;font-weight:700;paint-order:stroke;stroke:#0f172a;stroke-width:4px}
  .poly{fill:rgba(45,212,191,.18);stroke:#2dd4bf;stroke-width:2}
</style></head><body>
<header><h1>Calibração do court (vista de cima)</h1>
<p>Clica os <b>4 cantos do chão do court</b> pela ordem indicada à direita. O preview mostra o court endireitado — se ficar um retângulo bonito, está bem.</p></header>
<div class="wrap">
  <div class="bar">
    <button class="sec" onclick="reload()">↻ Nova imagem</button>
    <button class="sec" onclick="undo()">↶ Anular último</button>
    <button class="sec" onclick="clearAll()">✕ Recomeçar</button>
    <button id="save" onclick="save()">Guardar calibração</button>
    <span id="msg" class="hint"></span>
  </div>
  <div class="row">
    <div class="stage" id="stage">
      <img id="img" alt="snapshot da câmara">
      <svg id="ov" preserveAspectRatio="none"></svg>
    </div>
    <div class="side">
      <div id="steps"></div>
      <div class="prevbox" style="margin-top:12px">
        <div class="hint" style="margin-bottom:6px">Preview (court endireitado)</div>
        <canvas id="prevcanvas" width="200" height="100"></canvas>
      </div>
    </div>
  </div>
</div>
<script>
const STEPS=[
  ["Fundo-esquerda","canto do court AO LONGE, à esquerda"],
  ["Fundo-direita","canto AO LONGE, à direita"],
  ["Frente-direita","canto PERTO da câmara, à direita"],
  ["Frente-esquerda","canto PERTO da câmara, à esquerda"],
];
const img=document.getElementById('img'), ov=document.getElementById('ov'),
      stage=document.getElementById('stage'), msg=document.getElementById('msg'),
      stepsEl=document.getElementById('steps'), prev=document.getElementById('prevcanvas');
let pts=[];  // até 4 cantos, fracções 0..1

function reload(){ img.src='/api/snapshot?t='+Date.now(); }
img.onload=()=>{ ov.setAttribute('viewBox',`0 0 ${img.clientWidth} ${img.clientHeight}`); draw(); };
window.addEventListener('resize',()=>{ ov.setAttribute('viewBox',`0 0 ${img.clientWidth} ${img.clientHeight}`); draw(); });

stage.addEventListener('click',(e)=>{
  if(pts.length>=4) return;                       // já temos os 4
  const r=img.getBoundingClientRect();
  const x=(e.clientX-r.left)/r.width, y=(e.clientY-r.top)/r.height;
  if(x<0||x>1||y<0||y>1) return;
  pts.push([+x.toFixed(4),+y.toFixed(4)]); draw();
});
function undo(){ pts.pop(); draw(); }
function clearAll(){ pts=[]; draw(); }

function draw(){
  const w=img.clientWidth,h=img.clientHeight;
  const P=pts.map(p=>[p[0]*w,p[1]*h]);
  let s='';
  if(P.length>=2){ const pl=P.length===4?'polygon':'polyline';
    s+=`<${pl} class="poly" ${pl==='polyline'?'fill="none"':''} points="${P.map(p=>p.join(',')).join(' ')}"/>`; }
  P.forEach((p,i)=>{ s+=`<circle class="dot" cx="${p[0]}" cy="${p[1]}" r="7"/>`+
                       `<text class="lbl" x="${p[0]+11}" y="${p[1]+5}">${i+1}</text>`; });
  ov.innerHTML=s;
  // passos
  stepsEl.innerHTML=STEPS.map((st,i)=>{
    const cls=i<pts.length?'step done':(i===pts.length?'step cur':'step');
    return `<div class="${cls}"><span class="num">${i+1}</span><div><b>${st[0]}</b><br><span class="hint">${st[1]}</span></div></div>`;
  }).join('');
  drawPreview();
}

// Preview: homografia dos 4 cantos -> retângulo 200x100 (proporção 2:1 do court 20x10m)
function drawPreview(){
  const ctx=prev.getContext('2d'); ctx.clearRect(0,0,prev.width,prev.height);
  ctx.fillStyle='#1e3a8a'; ctx.fillRect(0,0,prev.width,prev.height);
  // linhas do court (meio + linhas de serviço aprox.) só decorativo
  ctx.strokeStyle='rgba(255,255,255,.7)'; ctx.lineWidth=1;
  ctx.strokeRect(2,2,prev.width-4,prev.height-4);
  ctx.beginPath(); ctx.moveTo(prev.width/2,2); ctx.lineTo(prev.width/2,prev.height-2); ctx.stroke();
  if(pts.length===4){
    ctx.fillStyle='#34d399'; ctx.font='12px system-ui';
    ctx.fillText('✓ 4 cantos definidos', 8, prev.height-8);
  }else{
    ctx.fillStyle='#64748b'; ctx.font='12px system-ui';
    ctx.fillText((4-pts.length)+' canto(s) em falta', 8, prev.height-8);
  }
}

async function save(){
  if(pts.length!==4){ msg.textContent='Faltam cantos — precisas dos 4.'; msg.className='hint err'; return; }
  msg.textContent='A guardar…'; msg.className='hint';
  try{
    const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({court_corners:pts})});
    if(!r.ok) throw new Error((await r.json()).detail||r.statusText);
    msg.textContent='✓ Calibração guardada. Podes fechar.'; msg.className='hint ok';
  }catch(e){ msg.textContent='Erro: '+e.message; msg.className='hint err'; }
}

(async()=>{
  try{ const c=await (await fetch('/api/config')).json();
       if(c.court_corners?.length===4) pts=c.court_corners; }catch{}
  reload();
})();
</script></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Mini-app de análise (calibração + heatmap)")
    ap.add_argument("--ip", required=True)
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="")
    ap.add_argument("--path", default="/Streaming/Channels/101")
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()
    CAM.update(ip=args.ip, user=args.user, password=args.password, path=args.path)
    print(f"[analytics] câmara {args.ip}  |  http://0.0.0.0:{args.port}/")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
