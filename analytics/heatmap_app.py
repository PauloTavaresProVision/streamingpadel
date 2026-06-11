#!/usr/bin/env python3
"""
Mini-app de ANÁLISE (heatmap de jogadores) — ISOLADA da app de streaming.

Corre na porta 8001 (a de streaming é a 8000). Se isto crashar, o streaming
dos jogos NÃO é afetado.

Páginas:
  /          → calibração (4 cantos do court, vista de cima)
  /heatmap   → heatmap ao vivo (iniciar/parar/limpar/guardar)

O motor (heatmap_engine.py) corre o YOLO em loop, filtra quem está dentro do
court (homografia dos 4 cantos) e acumula as posições dos pés num mapa de calor.

Arranque no Jetson:
    source ~/analytics-venv/bin/activate
    cd ~/streamingpadel
    python analytics/heatmap_app.py --ip 192.168.88.201 --user admin --password 'P@ssw0rd1535'
    # calibração: http://10.11.1.71:8001/   |   heatmap: http://10.11.1.71:8001/heatmap
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from typing import List, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile, File
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


# Estimativa inicial dos 4 cantos do COURT TODO (fracções 0..1), com base na
# imagem da câmara 192.168.88.201. Ordem: fundo-esq, fundo-dir, frente-dir, frente-esq.
# São um ponto de partida — o utilizador arrasta para afinar.
_DEFAULT_CORNERS = [
    [0.275, 0.045],   # 1 fundo-esquerda (topo)
    [0.665, 0.045],   # 2 fundo-direita (topo)
    [0.880, 0.760],   # 3 frente-direita (linha de fundo perto da câmara, acima das almofadas)
    [0.130, 0.760],   # 4 frente-esquerda
]


@app.get("/api/config")
def get_config():
    cfg = _load_config()
    # Se ainda não há calibração, devolve a estimativa inicial para o utilizador afinar.
    if len(cfg.get("court_corners") or []) != 4:
        cfg = dict(cfg)
        cfg["court_corners"] = _DEFAULT_CORNERS
        cfg["is_default"] = True
    return cfg


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


# ─────────────────────────── Heatmap (motor de IA) ───────────────────────────
def _detect_codec(rtsp: str) -> str:
    """Reusa o detector da app de streaming se disponível; senão tenta gst-discoverer."""
    try:
        import sys
        sys.path.insert(0, os.path.dirname(HERE))  # raiz do repo (tem app/)
        from app.gstreamer import _detect_codec as dc  # type: ignore
        return dc(rtsp)
    except Exception:
        return "h264"


# parâmetros do motor (ajustáveis nos args)
ENGINE_CFG = {"model": "yolov8s.pt", "conf": 0.25, "fps": 2.0}


@app.post("/api/heatmap/start")
def heatmap_start():
    from heatmap_engine import engine
    try:
        engine.start(_rtsp(), _detect_codec, _load_config(),
                     ENGINE_CFG["model"], ENGINE_CFG["conf"], ENGINE_CFG["fps"])
    except Exception as e:
        raise HTTPException(400, str(e))
    return engine.status()


@app.post("/api/heatmap/analyze-video")
async def analyze_video(file: UploadFile = File(...)):
    """Processa uma gravação (.mp4/.mkv) do MESMO ângulo da câmara calibrada.
    Corre o mais rápido possível e produz heatmap + métricas."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".mp4", ".mkv", ".mov", ".avi"}:
        raise HTTPException(400, "Formato não suportado (usa MP4/MKV/MOV/AVI).")
    vid_dir = os.path.join(OUT_DIR, "videos")
    os.makedirs(vid_dir, exist_ok=True)
    path = os.path.join(vid_dir, "analyze" + ext)
    with open(path, "wb") as f:
        while True:
            chunk = await file.read(1 << 20)   # 1 MB
            if not chunk:
                break
            f.write(chunk)
    from heatmap_engine import engine
    try:
        engine.start(_rtsp(), _detect_codec, _load_config(),
                     ENGINE_CFG["model"], ENGINE_CFG["conf"], ENGINE_CFG["fps"],
                     video_path=path)
    except Exception as e:
        raise HTTPException(400, str(e))
    return engine.status()


@app.post("/api/heatmap/stop")
def heatmap_stop():
    from heatmap_engine import engine
    engine.stop()
    return engine.status()


@app.post("/api/heatmap/reset")
def heatmap_reset():
    from heatmap_engine import engine
    engine.reset()
    return engine.status()


@app.get("/api/heatmap/status")
def heatmap_status():
    from heatmap_engine import engine
    return engine.status()


@app.get("/api/heatmap/metrics")
def heatmap_metrics():
    """Métricas por jogador: distância (m), centróide, % rede/fundo, cobertura."""
    from heatmap_engine import engine
    return engine.player_metrics()


class AreaIn(BaseModel):
    left: float = 0.0
    right: float = 1.0
    top: float = 0.0
    bottom: float = 1.0


class ParamsIn(BaseModel):
    conf: Optional[float] = None
    min_box: Optional[float] = None
    max_box: Optional[float] = None


@app.post("/api/heatmap/params")
def set_params(data: ParamsIn):
    """Afina a deteção ao vivo: conf (sensibilidade) + tamanho min/max da caixa."""
    from heatmap_engine import engine
    return engine.set_params(conf=data.conf, min_box=data.min_box, max_box=data.max_box)


@app.post("/api/heatmap/area")
def set_area(data: AreaIn):
    """Define onde está o court azul DENTRO da imagem de fundo (fracções 0..1).
    O heatmap só é pintado nesta sub-região (não na faixa cinzenta da imagem)."""
    cfg = _load_config()
    cfg["court_area"] = {"left": data.left, "right": data.right,
                         "top": data.top, "bottom": data.bottom}
    _save_config(cfg)
    # aplica já à instância em execução (sem reiniciar a análise)
    from heatmap_engine import engine
    engine._cfg["court_area"] = cfg["court_area"]
    return {"ok": True, "court_area": cfg["court_area"]}


@app.get("/api/heatmap/image")
def heatmap_image():
    from heatmap_engine import engine
    png = engine.render_png()
    if not png:
        raise HTTPException(503, "Sem imagem de heatmap.")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.post("/api/heatmap/background")
async def upload_background(file: UploadFile = File(...)):
    """Carrega a imagem de fundo do court (vista de cima) para o heatmap.
    Guarda como analytics/court_bg.png. Se não houver, usa o diagrama simples."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(400, "Formato não suportado (usa PNG/JPG).")
    data = await file.read()
    # remove versões antigas e grava sempre como .png (o motor procura court_bg.*)
    for old in ("court_bg.png", "court_bg.jpg", "court_bg.jpeg"):
        p = os.path.join(HERE, old)
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    with open(os.path.join(HERE, "court_bg.png"), "wb") as f:
        f.write(data)
    return {"ok": True}


@app.get("/api/heatmap/has-background")
def has_background():
    for name in ("court_bg.png", "court_bg.jpg", "court_bg.jpeg"):
        if os.path.exists(os.path.join(HERE, name)):
            return {"has_background": True}
    return {"has_background": False}


@app.get("/", response_class=HTMLResponse)
def index():
    return _PAGE


@app.get("/heatmap", response_class=HTMLResponse)
def heatmap_page():
    return _HEATMAP_PAGE


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
<p>Já vêm 4 cantos pré-marcados. <b>Arrasta cada ponto</b> com o rato para o canto certo do chão (ou clica para recriar). Não tens de ser perfeito — aproxima. Depois <b>Guardar</b>. &nbsp;|&nbsp; <a href="/heatmap" style="color:#2dd4bf">Ver heatmap →</a></p></header>
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

let drag=-1;  // índice do ponto a ser arrastado
function evFrac(e){ const r=img.getBoundingClientRect();
  return [Math.min(1,Math.max(0,(e.clientX-r.left)/r.width)),
          Math.min(1,Math.max(0,(e.clientY-r.top)/r.height))]; }
function nearest(x,y){ let bi=-1,bd=0.0009;  // ~3% de distância
  pts.forEach((p,i)=>{const d=(p[0]-x)**2+(p[1]-y)**2; if(d<bd){bd=d;bi=i;}}); return bi; }

stage.addEventListener('mousedown',(e)=>{
  const [x,y]=evFrac(e); const hit=nearest(x,y);
  if(hit>=0){ drag=hit; return; }               // começa a arrastar um ponto existente
  if(pts.length<4){ pts.push([+x.toFixed(4),+y.toFixed(4)]); draw(); }  // ou adiciona novo
});
window.addEventListener('mousemove',(e)=>{
  if(drag<0) return; const [x,y]=evFrac(e);
  pts[drag]=[+x.toFixed(4),+y.toFixed(4)]; draw();
});
window.addEventListener('mouseup',()=>{ drag=-1; });
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
       if(c.court_corners?.length===4){ pts=c.court_corners;
         if(c.is_default) msg.textContent='4 cantos pré-marcados — arrasta para afinar e Guarda.'; } }catch{}
  reload();
})();
</script></body></html>"""


# ─────────────────────────── Página do Heatmap ───────────────────────────
_HEATMAP_PAGE = """<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Heatmap — Padel Analytics</title>
<style>
  :root{color-scheme:dark}
  body{margin:0;background:#0f172a;color:#e2e8f0;font-family:system-ui,Segoe UI,Arial}
  header{padding:16px 20px;border-bottom:1px solid #1e293b}
  h1{margin:0;font-size:18px}
  p{color:#94a3b8;font-size:13px;margin:6px 0 0}
  .wrap{padding:20px;max-width:1100px;margin:0 auto}
  .bar{display:flex;gap:10px;align-items:center;margin:14px 0;flex-wrap:wrap}
  button{background:#0d9488;color:#fff;border:0;padding:9px 16px;border-radius:8px;cursor:pointer;font-size:14px}
  button.sec{background:#334155}button.danger{background:#b91c1c}
  button:disabled{opacity:.5;cursor:default}
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}
  .kpi{background:#0b1220;border:1px solid #1e293b;border-radius:10px;padding:12px}
  .kpi .v{font-size:24px;font-weight:800;color:#fff}.kpi .l{font-size:11px;color:#64748b}
  #hm{width:100%;display:block;border-radius:10px}
  .hmwrap{position:relative;max-width:900px;border:1px solid #1e293b;border-radius:10px;overflow:hidden}
  .hmwrap.adjust #hm{opacity:.55}
  #crop{position:absolute;border:2px solid #2dd4bf;box-shadow:0 0 0 9999px rgba(2,6,23,.55);cursor:move;display:none}
  .hmwrap.adjust #crop{display:block}
  .hd{position:absolute;width:14px;height:14px;background:#2dd4bf;border:2px solid #0f172a;border-radius:3px}
  .hd.nw{left:-8px;top:-8px;cursor:nwse-resize}.hd.ne{right:-8px;top:-8px;cursor:nesw-resize}
  .hd.sw{left:-8px;bottom:-8px;cursor:nesw-resize}.hd.se{right:-8px;bottom:-8px;cursor:nwse-resize}
  .hint{color:#94a3b8;font-size:13px}.ok{color:#34d399}.err{color:#f87171}
  a{color:#2dd4bf}
</style></head><body>
<header><h1>Heatmap de jogadores (ao vivo)</h1>
<p>Corre a deteção e acumula as posições dos jogadores dentro do court. &nbsp;|&nbsp; <a href="/">← Calibração</a></p></header>
<div class="wrap">
  <div class="bar">
    <button id="start" onclick="start()">▶ Iniciar análise</button>
    <button id="stop" class="danger" onclick="stop()">■ Parar</button>
    <button class="sec" onclick="reset()">↺ Limpar mapa</button>
    <a href="/api/heatmap/image" download="heatmap.png"><button class="sec">⤓ Guardar imagem</button></a>
    <button class="sec" onclick="bgInput.click()">🖼 Imagem de fundo</button>
    <input id="bgInput" type="file" accept="image/*" style="display:none">
    <button class="sec" onclick="vidInput.click()">📹 Analisar gravação</button>
    <input id="vidInput" type="file" accept="video/*" style="display:none">
    <button id="adjBtn" class="sec" onclick="toggleAdjust()">✂ Ajustar área</button>
    <span id="msg" class="hint"></span>
  </div>
  <div class="kpis">
    <div class="kpi"><div class="v" id="k_state">—</div><div class="l">ESTADO</div></div>
    <div class="kpi"><div class="v" id="k_cur">0</div><div class="l">JOGADORES AGORA</div></div>
    <div class="kpi"><div class="v" id="k_ids">—</div><div class="l">IDs NO COURT</div></div>
    <div class="kpi"><div class="v" id="k_dur">00:00</div><div class="l">DURAÇÃO</div></div>
  </div>
  <div class="hmwrap" id="hmwrap">
    <img id="hm" alt="heatmap">
    <div id="crop">
      <div class="hd nw"></div><div class="hd ne"></div><div class="hd sw"></div><div class="hd se"></div>
    </div>
  </div>
  <p id="adjHint" class="hint" style="display:none;margin-top:8px">Arrasta a caixa para cobrir só o <b>court azul</b>. Puxa os cantos para redimensionar. Clica <b>Ajustar área</b> outra vez para terminar.</p>

  <h2 style="font-size:16px;margin:22px 0 8px">Métricas por jogador</h2>
  <table id="mtable" style="width:100%;border-collapse:collapse;font-size:14px">
    <thead><tr style="text-align:left;color:#94a3b8;border-bottom:1px solid #1e293b">
      <th style="padding:8px 6px">Jogador</th><th>Distância</th><th>% na rede</th><th>% no fundo</th><th>Cobertura</th>
    </tr></thead>
    <tbody id="mbody"><tr><td colspan="5" class="hint" style="padding:10px 6px">Sem dados — inicia a análise com jogadores no court.</td></tr></tbody>
  </table>
  <p class="hint" style="margin-top:6px">Distância = metros percorridos · % rede/fundo = tempo perto/longe da rede · Cobertura = % do court visitado. <b>Nota:</b> com 1 câmara os IDs podem trocar quando os jogadores se cruzam — os totais são indicativos.</p>

  <details style="margin-top:14px">
    <summary style="cursor:pointer;color:#2dd4bf;font-size:14px">⚙ Sensibilidade da deteção</summary>
    <p class="hint" style="margin:8px 0">Se detetar a mais (reflexos): sobe a sensibilidade ou o tamanho mínimo. Se detetar a menos: desce.</p>
    <div style="display:grid;gap:12px;max-width:520px">
      <label class="hint">Confiança mínima — <span id="v_conf">0.25</span>
        <input id="p_conf" type="range" min="0.05" max="0.7" step="0.01" value="0.25" style="width:100%"></label>
      <label class="hint">Tamanho mínimo do jogador — <span id="v_min">0.012</span>
        <input id="p_min" type="range" min="0" max="0.08" step="0.002" value="0.012" style="width:100%"></label>
    </div>
  </details>
</div>
<script>
const msg=document.getElementById('msg');
function fmtDur(s){const m=Math.floor(s/60),ss=s%60;return String(m).padStart(2,'0')+':'+String(ss).padStart(2,'0');}
async function start(){ msg.textContent='A iniciar (carrega o modelo na 1ª vez)…'; msg.className='hint';
  try{const r=await fetch('/api/heatmap/start',{method:'POST'});
    if(!r.ok) throw new Error((await r.json()).detail||r.statusText);
    msg.textContent='Análise a correr.'; msg.className='hint ok';}catch(e){msg.textContent='Erro: '+e.message;msg.className='hint err';}
}
async function stop(){ await fetch('/api/heatmap/stop',{method:'POST'}); msg.textContent='Parado.'; msg.className='hint'; }
async function reset(){ await fetch('/api/heatmap/reset',{method:'POST'}); }
const bgInput=document.getElementById('bgInput');
bgInput.addEventListener('change',async()=>{
  if(!bgInput.files[0]) return;
  msg.textContent='A enviar imagem de fundo…'; msg.className='hint';
  const fd=new FormData(); fd.append('file',bgInput.files[0]);
  try{ const r=await fetch('/api/heatmap/background',{method:'POST',body:fd});
    if(!r.ok) throw new Error((await r.json()).detail||r.statusText);
    msg.textContent='✓ Fundo atualizado.'; msg.className='hint ok';
    document.getElementById('hm').src='/api/heatmap/image?t='+Date.now();
  }catch(e){ msg.textContent='Erro: '+e.message; msg.className='hint err'; }
});

// ── Ajuste da área do court por CROP visual ──
const hmwrap=document.getElementById('hmwrap'), hm=document.getElementById('hm'),
      crop=document.getElementById('crop'), adjBtn=document.getElementById('adjBtn'),
      adjHint=document.getElementById('adjHint');
let adjusting=false;
// área em fracções 0..1 (left,top,right,bottom)
let area={left:0.10,top:0.18,right:0.90,bottom:0.82};

function applyCropBox(){
  const w=hm.clientWidth,h=hm.clientHeight;
  crop.style.left=(area.left*w)+'px'; crop.style.top=(area.top*h)+'px';
  crop.style.width=((area.right-area.left)*w)+'px';
  crop.style.height=((area.bottom-area.top)*h)+'px';
}
function toggleAdjust(){
  adjusting=!adjusting;
  hmwrap.classList.toggle('adjust',adjusting);
  adjHint.style.display=adjusting?'block':'none';
  adjBtn.textContent=adjusting?'✓ Concluir':'✂ Ajustar área';
  if(adjusting) applyCropBox(); else saveArea();
}
async function saveArea(){
  await fetch('/api/heatmap/area',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(area)});
  hm.src='/api/heatmap/image?t='+Date.now();
}

let mode=null, sx=0, sy=0, start0=null;
function onDown(e, m){ if(!adjusting) return; e.preventDefault(); e.stopPropagation();
  mode=m; sx=e.clientX; sy=e.clientY; start0={...area}; }
crop.addEventListener('mousedown',(e)=>{ if(e.target.classList.contains('hd')) return; onDown(e,'move'); });
crop.querySelector('.nw').addEventListener('mousedown',(e)=>onDown(e,'nw'));
crop.querySelector('.ne').addEventListener('mousedown',(e)=>onDown(e,'ne'));
crop.querySelector('.sw').addEventListener('mousedown',(e)=>onDown(e,'sw'));
crop.querySelector('.se').addEventListener('mousedown',(e)=>onDown(e,'se'));
window.addEventListener('mousemove',(e)=>{
  if(!mode) return;
  const w=hm.clientWidth,h=hm.clientHeight;
  const dx=(e.clientX-sx)/w, dy=(e.clientY-sy)/h;
  let a={...start0};
  if(mode==='move'){ const cw=a.right-a.left, ch=a.bottom-a.top;
    a.left=Math.min(Math.max(0,a.left+dx),1-cw); a.top=Math.min(Math.max(0,a.top+dy),1-ch);
    a.right=a.left+cw; a.bottom=a.top+ch; }
  if(mode.includes('w')) a.left=Math.min(Math.max(0,a.left+dx),a.right-0.05);
  if(mode.includes('e')) a.right=Math.max(Math.min(1,a.right+dx),a.left+0.05);
  if(mode.includes('n')) a.top=Math.min(Math.max(0,a.top+dy),a.bottom-0.05);
  if(mode.includes('s')) a.bottom=Math.max(Math.min(1,a.bottom+dy),a.top+0.05);
  area=a; applyCropBox();
});
window.addEventListener('mouseup',()=>{ if(mode){ mode=null; saveArea(); } });
window.addEventListener('resize',()=>{ if(adjusting) applyCropBox(); });

// upload + análise de gravação
const vidInput=document.getElementById('vidInput');
vidInput.addEventListener('change',async()=>{
  if(!vidInput.files[0]) return;
  const mb=Math.round(vidInput.files[0].size/1048576);
  msg.textContent='A enviar gravação ('+mb+' MB)… pode demorar.'; msg.className='hint';
  const fd=new FormData(); fd.append('file',vidInput.files[0]);
  try{ const r=await fetch('/api/heatmap/analyze-video',{method:'POST',body:fd});
    if(!r.ok) throw new Error((await r.json()).detail||r.statusText);
    msg.textContent='✓ A processar a gravação (vê o mapa e as métricas a evoluir).'; msg.className='hint ok';
  }catch(e){ msg.textContent='Erro: '+e.message; msg.className='hint err'; }
});

// sliders de sensibilidade da deteção (aplicam ao vivo)
const pConf=document.getElementById('p_conf'), pMin=document.getElementById('p_min'),
      vConf=document.getElementById('v_conf'), vMin=document.getElementById('v_min');
let pTimer=null;
function sendParams(){
  vConf.textContent=(+pConf.value).toFixed(2); vMin.textContent=(+pMin.value).toFixed(3);
  clearTimeout(pTimer);
  pTimer=setTimeout(()=>fetch('/api/heatmap/params',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({conf:+pConf.value,min_box:+pMin.value})}), 200);
}
pConf.addEventListener('input',sendParams); pMin.addEventListener('input',sendParams);

async function poll(){
  try{ const s=await (await fetch('/api/heatmap/status')).json();
    document.getElementById('k_state').textContent = s.running?'A correr':(s.error?'Erro':'Parado');
    document.getElementById('k_cur').textContent = s.current_players;
    document.getElementById('k_ids').textContent = (s.active_ids&&s.active_ids.length)?('#'+s.active_ids.join(' #')):'—';
    document.getElementById('k_dur').textContent = fmtDur(s.duration_seconds||0);
    if(s.error){ msg.textContent='Erro: '+s.error; msg.className='hint err'; }
    if(!s.has_calibration){ msg.textContent='Sem calibração — vai a / e marca os 4 cantos.'; msg.className='hint err'; }
  }catch{}
  if(!adjusting) hm.src='/api/heatmap/image?t='+Date.now();   // não refresca a meio do ajuste
  // métricas por jogador
  try{ const m=await (await fetch('/api/heatmap/metrics')).json();
    const tb=document.getElementById('mbody');
    if(m.players && m.players.length){
      tb.innerHTML=m.players.map(p=>`<tr style="border-bottom:1px solid #1e293b">
        <td style="padding:8px 6px">Jogador #${p.id}</td>
        <td>${p.distance_m} m</td>
        <td>${p.net_pct}%</td>
        <td>${p.back_pct}%</td>
        <td>${p.coverage_pct}%</td></tr>`).join('');
    }
  }catch{}
}
hm.addEventListener('load',()=>{ if(adjusting) applyCropBox(); });
// carrega a área guardada
(async()=>{ try{ const c=await (await fetch('/api/config')).json();
  if(c.court_area) area={left:c.court_area.left,top:c.court_area.top,right:c.court_area.right,bottom:c.court_area.bottom}; }catch{} })();
setInterval(poll, 3000); poll();
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
