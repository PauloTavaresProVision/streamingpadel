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
    return {"court_polygon": []}


def _save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _grab_snapshot_jpeg() -> Optional[bytes]:
    """Tira 1 frame da câmara via ffmpeg → JPEG em memória. Sem dependências de IA."""
    out = os.path.join(OUT_DIR, "calib_snapshot.jpg")
    try:
        if os.path.exists(out):
            os.remove(out)
    except Exception:
        pass
    cmd = [
        "ffmpeg", "-y", "-rtsp_transport", "tcp", "-i", _rtsp(),
        "-frames:v", "1", "-q:v", "2", out,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except Exception:
        return None
    if os.path.exists(out) and os.path.getsize(out) > 1024:
        with open(out, "rb") as f:
            return f.read()
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
    court_polygon: List[List[float]]   # [[x,y], ...] em fracções 0..1 da imagem


@app.post("/api/config")
def set_config(data: CalibIn):
    if len(data.court_polygon) < 3:
        raise HTTPException(400, "O polígono do court precisa de pelo menos 3 pontos.")
    cfg = _load_config()
    cfg["court_polygon"] = data.court_polygon
    _save_config(cfg)
    return {"ok": True, "points": len(data.court_polygon)}


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
  .stage{position:relative;display:inline-block;border:1px solid #1e293b;border-radius:10px;overflow:hidden}
  #img{display:block;max-width:100%;height:auto}
  svg{position:absolute;inset:0;width:100%;height:100%}
  .bar{display:flex;gap:10px;align-items:center;margin:14px 0;flex-wrap:wrap}
  button{background:#0d9488;color:#fff;border:0;padding:9px 16px;border-radius:8px;cursor:pointer;font-size:14px}
  button.sec{background:#334155}
  button:disabled{opacity:.5;cursor:default}
  .hint{color:#94a3b8;font-size:13px}
  .ok{color:#34d399}.err{color:#f87171}
  .dot{fill:#2dd4bf;stroke:#0f172a;stroke-width:2}
  .poly{fill:rgba(45,212,191,.20);stroke:#2dd4bf;stroke-width:2}
</style></head><body>
<header><h1>Calibração do court</h1>
<p>Clica os cantos do <b>court de jogo</b> (a área azul), seguindo a borda. 4 pontos chegam; podes pôr mais para acompanhar a curva da lente. Depois <b>Guardar</b>.</p></header>
<div class="wrap">
  <div class="bar">
    <button class="sec" onclick="reload()">↻ Nova imagem</button>
    <button class="sec" onclick="undo()">↶ Anular último</button>
    <button class="sec" onclick="clearAll()">✕ Limpar</button>
    <button id="save" onclick="save()">Guardar zona</button>
    <span id="msg" class="hint"></span>
  </div>
  <div class="stage" id="stage">
    <img id="img" alt="snapshot da câmara">
    <svg id="ov" preserveAspectRatio="none"></svg>
  </div>
  <p class="hint">Pontos: <span id="count">0</span></p>
</div>
<script>
const img=document.getElementById('img'), ov=document.getElementById('ov'),
      stage=document.getElementById('stage'), msg=document.getElementById('msg'),
      count=document.getElementById('count');
let pts=[];  // fracções 0..1

function reload(){ img.src='/api/snapshot?t='+Date.now(); }
img.onload=()=>{ ov.setAttribute('viewBox',`0 0 ${img.clientWidth} ${img.clientHeight}`); draw(); };
window.addEventListener('resize',()=>ov.setAttribute('viewBox',`0 0 ${img.clientWidth} ${img.clientHeight}`));

stage.addEventListener('click',(e)=>{
  if(e.target.tagName==='circle') return;        // ignora clique nos próprios pontos
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
  if(P.length>=3) s+=`<polygon class="poly" points="${P.map(p=>p.join(',')).join(' ')}"/>`;
  else if(P.length===2) s+=`<polyline class="poly" fill="none" points="${P.map(p=>p.join(',')).join(' ')}"/>`;
  P.forEach((p,i)=>{ s+=`<circle class="dot" cx="${p[0]}" cy="${p[1]}" r="6"/>`; });
  ov.innerHTML=s; count.textContent=pts.length;
}
async function save(){
  if(pts.length<3){ msg.textContent='Marca pelo menos 3 pontos.'; msg.className='hint err'; return; }
  msg.textContent='A guardar…'; msg.className='hint';
  try{
    const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({court_polygon:pts})});
    if(!r.ok) throw new Error((await r.json()).detail||r.statusText);
    const j=await r.json();
    msg.textContent='✓ Zona guardada ('+j.points+' pontos).'; msg.className='hint ok';
  }catch(e){ msg.textContent='Erro: '+e.message; msg.className='hint err'; }
}
// carrega config existente (se houver) + imagem
(async()=>{
  try{ const c=await (await fetch('/api/config')).json(); if(c.court_polygon?.length) pts=c.court_polygon; }catch{}
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
