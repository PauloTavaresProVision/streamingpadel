#!/usr/bin/env python3
"""
Motor do heatmap de jogadores (Fase 2).

Corre numa thread: captura frames da câmara (GStreamer + decode HW), deteta
pessoas (YOLO/ultralytics na GPU), fica só com quem está DENTRO do court
(via homografia dos 4 cantos calibrados), e acumula as posições dos pés num
mapa de calor "visto de cima" (court endireitado 20×10 m).

Desenha-se sobre um diagrama do court. Tudo isolado da app de streaming.
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
from typing import List, Optional, Tuple

import numpy as np

# Compat: numpy >=1.24 removeu os aliases np.bool/np.int/np.float. O ultralytics
# 8.2.x usa-os no caminho do TensorRT (.engine) → repomo-los (eram só aliases
# dos builtins; 100% seguro). Sem isto, a inferência TensorRT rebenta com
# "module 'numpy' has no attribute 'bool'".
for _alias, _builtin in (("bool", bool), ("int", int), ("float", float),
                         ("object", object), ("str", str)):
    if not hasattr(np, _alias):
        setattr(np, _alias, _builtin)


def _os_path_join_out(name: str) -> str:
    """Caminho para analytics/out/<name> (cria a pasta se preciso)."""
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out, exist_ok=True)
    return os.path.join(out, name)

# Dimensões do "court endireitado" (vista de cima). Proporção 2:1 (20×10 m).
DST_W, DST_H = 400, 200
# Escala px→metros (court oficial de padel: 20 m comprimento × 10 m largura).
M_PER_PX_X = 20.0 / DST_W       # 0.05 m/px (comprimento 20 m em 400 px)
M_PER_PX_Y = 10.0 / DST_H       # 0.05 m/px (largura 10 m em 200 px)
NET_X_M = 10.0                  # rede no meio do comprimento (x=DST_W/2)
NET_BAND_M = 4.0               # "na rede" se a <=4 m da rede; senão "no fundo"
ZONES_X, ZONES_Y = 6, 3        # grelha de zonas para % de cobertura
MAX_STEP_M = 2.5               # salto máx. plausível (usado na costura de IDs)
# Distância robusta: o erro da caixa é BIMODAL (caixa inteira vs cortada na
# rede → pés saltam 0,5-1 m entre 2 estados). Mediana deslizante ignora o
# estado minoritário (a média/EMA oscilava e somava fantasma).
MED_WIN = 11                   # janela da mediana (~1,1 s a 10 fps)
SAMPLE_PERIOD_S = 2.0          # mede o passo a cada 2 s (ruído cancela, movimento soma)
MIN_STEP_M = 0.5               # passo mín. por amostra p/ contar (0,25 m/s)
# Cap 2,0: em janelas de 2 s, deslocações >2 m/s sustentadas são quase sempre
# TROCAS de caixa entre jogadores que se cruzam (teleporte 3-6 m), não sprints.
MAX_SPEED_MS = 2.0

# Pontos extra opcionais com posição REAL conhecida (court 20×10 m). Regra FIP:
# as linhas de serviço ficam a 6,95 m DA REDE — ou seja a 3,05 m de cada parede
# de fundo (antes estava 6,95 m do fundo: errado, deslocava os T's ~4 m).
# Coords em px do DST (x=comprimento 0..DST_W a partir da parede LONGE;
# y=largura 0..DST_H, esq→dir).
_SVC_FAR_X = 3.05 / 20.0 * DST_W
_SVC_NEAR_X = (20.0 - 3.05) / 20.0 * DST_W
EXTRA_DST = {
    5: (_SVC_FAR_X, 0),            # serviço-longe × parede esquerda
    6: (_SVC_FAR_X, DST_H),        # serviço-longe × parede direita
    7: (_SVC_NEAR_X, 0),           # serviço-perto × parede esquerda
    8: (_SVC_NEAR_X, DST_H),       # serviço-perto × parede direita
    9: (_SVC_FAR_X, DST_H / 2),    # T longe (serviço × linha central)
    10: (_SVC_NEAR_X, DST_H / 2),  # T perto
}

# Resolução a que pedimos os frames ao gst-launch (downscale ajuda a GPU/CPU;
# 1280×720 chega para deteção de pessoas e é mais rápido que 1080p).
CAP_W, CAP_H = 1280, 720
# Resolução de INFERÊNCIA do YOLO. O default (640) encolhe o frame e perde
# jogadores pequenos/tapados pela rede. A 1280 (≈resolução total) deteta-os muito
# melhor. A .engine TensorRT TEM de ser exportada a este mesmo tamanho.
INFER_IMGSZ = 1280


def _gst_cmd(rtsp: str, codec: str, live_fps: int = 10) -> list:
    """Comando gst-launch que decodifica o RTSP (HW) e escreve frames BGRx crus
    (4 bytes/pixel) no stdout, a live_fps CONTÍNUOS (videorate). O nvvidconv
    produz BGRx; o canal alfa é descartado no Python. O OpenCV deste Jetson NÃO
    tem GStreamer, por isso lemos os bytes nós próprios."""
    depay, parse = ("rtph264depay", "h264parse") if codec == "h264" else ("rtph265depay", "h265parse")
    return [
        "gst-launch-1.0", "-q",
        "rtspsrc", f"location={rtsp}", "protocols=tcp", "latency=300", "!",
        depay, "!", parse, "!", "nvv4l2decoder", "!",
        "nvvidconv", "!", f"video/x-raw,format=BGRx,width={CAP_W},height={CAP_H}", "!",
        # 10 fps CONTÍNUOS para o tracker (1 câmara → há GPU de sobra)
        "videorate", "!", f"video/x-raw,framerate={live_fps}/1", "!",
        "fdsink", "fd=1", "sync=false",
    ]


def _gst_file_cmd(path: str, out_fps: int = 10) -> list:
    """Lê um ficheiro de vídeo e debita frames BGRx crus a CADÊNCIA FIXA (out_fps),
    contínuos. videorate reamostra para out_fps → o tracker recebe frames
    uniformes (essencial: o ByteTrack/Kalman assume continuidade). sem sync →
    corre o mais rápido possível (offline)."""
    return [
        "gst-launch-1.0", "-q",
        "filesrc", f"location={path}", "!", "decodebin", "!",
        # nvvidconv PRIMEIRO (sai de NVMM→sysmem BGRx); só DEPOIS videorate
        # (elemento de CPU, precisa de sysmem). A ordem inversa não negoceia
        # e o pipeline morre logo no arranque.
        "nvvidconv", "!", f"video/x-raw,format=BGRx,width={CAP_W},height={CAP_H}", "!",
        "videorate", "!", f"video/x-raw,framerate={out_fps}/1", "!",
        "fdsink", "fd=1", "sync=false",
    ]


class HeatmapEngine:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        # acumulador do calor (vista de cima) — TODOS os jogadores juntos
        self._acc = np.zeros((DST_H, DST_W), dtype=np.float32)
        # acumuladores POR SLOT (1-4), em dois referenciais:
        #  • real  = posição física no court
        #  • tac   = tático: rodado 180° quando as equipas trocaram de lado, para
        #            cada dupla cair sempre na MESMA metade de referência (assim o
        #            padrão de uma dupla soma-se entre sets em vez de se espalhar).
        self._acc_slot = {s: np.zeros((DST_H, DST_W), dtype=np.float32)
                          for s in (1, 2, 3, 4)}
        self._acc_slot_tac = {s: np.zeros((DST_H, DST_W), dtype=np.float32)
                              for s in (1, 2, 3, 4)}
        self._last_frame = None        # último frame BGR (p/ "live camera" no modo TV)
        self._last_dets = []           # [(box, cid, slot)] do último frame (vista tracking)
        self._H = None                 # matriz de homografia (3x3)
        self._running = False
        self._error: Optional[str] = None
        self._frames = 0               # frames analisados
        self._detections = 0           # somatório de jogadores (dentro do court)
        self._current = 0              # jogadores no último frame
        self._started_at = 0.0
        self._model = None
        self._cfg = {}
        # parâmetros afináveis AO VIVO (sem reiniciar a análise)
        self._conf = 0.25          # confiança mínima do YOLO
        self._min_box = 0.012      # altura mín. da caixa (fracção da imagem) — corta reflexos/objetos
        self._max_box = 0.55       # altura máx. — corta blobs gigantes (2 pessoas juntas/sombras)
        self._recent = []          # últimas contagens (para suavizar o KPI)
        self._track_last = {}      # {id: (cx, cy, t)} última posição de cada jogador (campo)
        self._active_ids = set()   # IDs vistos no último frame
        # métricas por ID: distância (m), nº amostras, soma x/y (centróide),
        # amostras na rede vs fundo, grelha de zonas visitadas
        self._stats = {}           # {id canónico: dict}
        self._expected_players = 4  # padel = 4 jogadores

        # ── identidade canónica (costura de fragmentos) ──
        # O tracker fragmenta IDs nos cruzamentos. Regras físicas do padel:
        # (a) um jogador não se teleporta; (b) há SEMPRE <=4 no court.
        # Mantemos 4 "jogadores canónicos"; um ID bruto novo herda o canónico
        # que desapareceu mais perto da sua posição (prevista pela velocidade).
        self._canon_map = {}       # tid bruto -> id canónico
        self._canon = {}           # id canónico -> {x,y,t,vx,vy} (metros, tempo)
        self._next_canon = 1
        self._active_canon = set() # jogadores canónicos vistos no último frame
        self._media_t = 0.0        # tempo de VÍDEO processado (ficheiro corre +rápido que real)
        # ── slots por lado/equipa (suporta "trocaram de lado") ──
        # As métricas acumulam por SLOT 1-4 (com nome), não por track: equipa A
        # = slots 1-2, equipa B = 3-4. A atribuição track→slot é pela POSIÇÃO
        # (lado do campo), revista a cada troca de lado.
        self._slots = {}           # canon_id -> slot (1..4)
        self._prev_slots = {}      # atribuição anterior (desempate na troca)
        self._swapped = False      # False: equipa A no lado longe (x<10)
        self._need_assign = True

    # ─────────────────────────── controlo ───────────────────────────
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict:
        with self._lock:
            # tempo de VÍDEO analisado (em ficheiro o processamento corre mais
            # rápido que tempo real — mostrar o relógio real enganava).
            dur = int(self._media_t) if self._running else 0
            return {
                "running": self._running,
                "error": self._error,
                "frames": self._frames,
                "detections": self._detections,
                "current_players": self._current,
                "duration_seconds": dur,
                "has_calibration": bool(self._cfg.get("court_corners")),
                "conf": round(self._conf, 2),
                "min_box": round(self._min_box, 3),
                "max_box": round(self._max_box, 3),
                "infer_imgsz": INFER_IMGSZ,                  # resolução de inferência
                "model_kind": getattr(self, "_model_kind", "—"),  # TensorRT / PyTorch
                "active_ids": sorted(self._active_ids),     # IDs brutos (diagnóstico)
                "active_players": sorted(self._active_canon),  # jogadores 1-4 no court
                "total_ids": len(self._track_last),         # IDs brutos distintos vistos
                # DIAGNÓSTICO da fragmentação: nº de amostras de cada ID (= tempo
                # de vida). top-8 mais longos + quantos viveram <1s e <3s.
                "track_diag": self._track_diag(),
            }

    def _track_diag(self) -> dict:
        """ASSUME lock. Distribuição de tempo de vida dos IDs (amostras a 10 fps)."""
        ns = sorted((st["n"] for st in self._stats.values()), reverse=True)
        fps = 10.0
        # histograma agregado de velocidades dos passos somados (diagnóstico da
        # distância): buckets 0-0.5/0.5-1/1-1.5/1.5-2 m/s + rejeitados (>=2 = trocas)
        spd = [0, 0, 0, 0]
        rej = 0
        for st in self._stats.values():
            for i in range(4):
                spd[i] += st.get("spd", [0, 0, 0, 0])[i]
            rej += st.get("spd_rej", 0)
        return {
            "total_tracks": len(ns),
            "top_secs": [round(n / fps, 1) for n in ns[:8]],   # duração dos 8 maiores
            "under_1s": sum(1 for n in ns if n < fps),         # IDs com <1s de vida
            "under_3s": sum(1 for n in ns if n < 3 * fps),     # IDs com <3s de vida
            "speed_hist": {"0-0.5": spd[0], "0.5-1": spd[1],
                           "1-1.5": spd[2], "1.5-2": spd[3], "rejected>=2": rej},
        }

    def set_params(self, conf=None, min_box=None, max_box=None) -> dict:
        """Afina os parâmetros de deteção AO VIVO (aplica no próximo frame)."""
        with self._lock:
            if conf is not None:
                self._conf = max(0.05, min(float(conf), 0.9))
            if min_box is not None:
                self._min_box = max(0.0, min(float(min_box), 0.3))
            if max_box is not None:
                self._max_box = max(0.2, min(float(max_box), 1.0))
        return {"conf": self._conf, "min_box": self._min_box, "max_box": self._max_box}

    def reset(self) -> None:
        with self._lock:
            self._acc[:] = 0
            for s in (1, 2, 3, 4):
                self._acc_slot[s][:] = 0
                self._acc_slot_tac[s][:] = 0
            self._last_frame = None
            self._last_dets = []
            self._frames = 0
            self._detections = 0
            self._recent = []
            self._track_last = {}
            self._active_ids = set()
            self._stats = {}
            self._canon_map = {}
            self._canon = {}
            self._next_canon = 1
            self._active_canon = set()
            self._slots = {}
            self._prev_slots = {}
            self._swapped = False
            self._need_assign = True

    def swap_sides(self) -> dict:
        """As equipas trocaram de lado: inverte a regra lado→equipa e reatribui
        os tracks aos slots quando os 4 estiverem de novo posicionados 2+2.
        As métricas acumuladas por slot/nome mantêm-se."""
        with self._lock:
            self._swapped = not self._swapped
            self._prev_slots = dict(self._slots)
            self._slots = {}
            self._need_assign = True
            return {"sides_swapped": self._swapped}

    def _try_assign_slots(self, now: float) -> None:
        """ASSUME lock. Atribui canónicos→slots pela POSIÇÃO TÁTICA, que no padel
        é fixa: slots 1=A-Esquerda, 2=A-Direita, 3=B-Esquerda, 4=B-Direita
        ("esquerda" do ponto de vista do jogador a olhar para a rede).
        Lado longe (x<10): olham no sentido +x → a esquerda deles é y MAIOR.
        Lado perto: olham -x → esquerda é y MENOR. Lado longe = equipa A,
        salvo se trocaram de lado. Como o jogador de esquerda joga sempre à
        esquerda, o nome segue-o automaticamente através das trocas de campo."""
        fresh = {cid: st for cid, st in self._canon.items() if now - st["t"] < 0.5}
        if len(fresh) != self._expected_players:
            return
        far = [cid for cid, st in fresh.items() if st["x"] < 10.0]
        near = [cid for cid, st in fresh.items() if st["x"] >= 10.0]
        if len(far) != 2 or len(near) != 2:
            return                       # ainda não estão 2+2 (ex.: a meio da troca)
        far_slots = (3, 4) if self._swapped else (1, 2)    # (esquerda, direita)
        near_slots = (1, 2) if self._swapped else (3, 4)
        # lado longe: esquerda do jogador = y maior; lado perto: y menor
        far.sort(key=lambda c: -fresh[c]["y"])             # [esq, dir]
        near.sort(key=lambda c: fresh[c]["y"])             # [esq, dir]
        for pair, slots in ((far, far_slots), (near, near_slots)):
            self._slots[pair[0]] = slots[0]    # esquerda
            self._slots[pair[1]] = slots[1]    # direita
        self._need_assign = False

    def start(self, rtsp: str, codec_detect, cfg: dict, model_name: str,
              conf: float, fps: float, video_path: Optional[str] = None) -> None:
        """Arranca a análise. Se video_path for dado, processa esse ficheiro (o
        mais rápido possível); senão lê a câmara ao vivo (rtsp)."""
        if self._running:
            return
        corners = cfg.get("court_corners") or []
        if len(corners) != 4:
            raise RuntimeError("Sem calibração: define os 4 cantos do court primeiro.")
        self._cfg = cfg
        self._conf = conf          # valor inicial (depois afinável ao vivo)
        self._stop.clear()
        self._error = None
        self.reset()
        # pasta do relatório desta sessão (auto-guardado: ver _save_report)
        self._report_dir = os.path.join(
            _os_path_join_out("relatorios"), time.strftime("%Y-%m-%d_%H-%M-%S"))
        self._thread = threading.Thread(
            target=self._run, name="heatmap-engine", daemon=True,
            args=(rtsp, codec_detect, corners, model_name, conf, fps, video_path),
        )
        self._running = True
        self._started_at = time.time()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._running = False

    # ─────────────────────────── loop ───────────────────────────
    # ───────────────────── correção da lente (fisheye) ─────────────────────
    @staticmethod
    def _lens_undistort_pts(pts, w: int, h: int, k1: float, k2: float = 0.0):
        """Corrige a distorção radial de pontos em píxeis (Nx2). Modelo:
        ponto_distorcido = ponto_corrigido * (1 + k1*r² + k2*r⁴), r normalizado
        ao meio-largura. Invertido por ponto-fixo (3 iterações — converge para
        |k| pequenos). k1=0 → identidade. NÃO desdistorce o frame (caro);
        só os pontos (cantos + pés) — equivalente e grátis."""
        if abs(k1) < 1e-9 and abs(k2) < 1e-9:
            return pts
        p = np.asarray(pts, dtype=np.float64).reshape(-1, 2).copy()
        cx, cy = w / 2.0, h / 2.0
        s = w / 2.0                          # escala de normalização
        xd = (p[:, 0] - cx) / s
        yd = (p[:, 1] - cy) / s
        xu, yu = xd.copy(), yd.copy()        # inversão por ponto-fixo
        for _ in range(6):
            r2 = xu * xu + yu * yu
            f = 1.0 + k1 * r2 + k2 * r2 * r2
            f = np.where(np.abs(f) < 1e-6, 1e-6, f)
            xu, yu = xd / f, yd / f
        p[:, 0] = xu * s + cx
        p[:, 1] = yu * s + cy
        return p.astype(np.float32)

    def _lens_params(self):
        try:
            return (float(self._cfg.get("lens_k1", 0.0) or 0.0),
                    float(self._cfg.get("lens_k2", 0.0) or 0.0))
        except Exception:
            return 0.0, 0.0

    def _load_calib(self):
        """Carrega camera_calib.json (calibração com xadrez) uma vez. Devolve
        (K, dist, w, h) ou None. Se existir, é MUITO mais preciso que o k1/k2
        afinado à mão (cv2.calibrateCamera mede a distorção real da lente)."""
        if getattr(self, "_calib_loaded", False):
            return self._calib
        self._calib_loaded = True
        self._calib = None
        try:
            import json as _json
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "camera_calib.json")
            if os.path.exists(path):
                with open(path) as f:
                    d = _json.load(f)
                K = np.array(d["K"], dtype=np.float64)
                dist = np.array(d["dist"], dtype=np.float64).reshape(1, -1)
                sz = d.get("image_size") or [CAP_W, CAP_H]
                self._calib = (K, dist, int(sz[0]), int(sz[1]))
        except Exception:
            self._calib = None
        return self._calib

    def _undistort_pts(self, pts, w: int, h: int):
        """Desdistorce pontos (Nx2 px). Usa a calibração do xadrez se existir
        (cv2.undistortPoints), senão o modelo radial k1/k2 afinado à mão."""
        import cv2
        calib = self._load_calib()
        if calib is not None:
            K, dist, cw, ch = calib
            K2 = K.copy()
            if cw != w or ch != h:           # escala K p/ a resolução de trabalho
                sx, sy = w / float(cw), h / float(ch)
                K2[0, 0] *= sx; K2[0, 2] *= sx
                K2[1, 1] *= sy; K2[1, 2] *= sy
            p = np.asarray(pts, np.float32).reshape(-1, 1, 2)
            u = cv2.undistortPoints(p, K2, dist, P=K2)
            return u.reshape(-1, 2).astype(np.float32)
        k1, k2 = self._lens_params()
        return self._lens_undistort_pts(pts, w, h, k1, k2)

    def _build_homography(self, corners, frame_w, frame_h):
        """Homografia imagem→court. CORREÇÃO DE ORIENTAÇÃO: a câmara está atrás
        da parede de fundo — os cantos 1-2 (longe) distam 10 m (LARGURA) e o
        comprimento (20 m) vai de longe→perto. Mapeamento certo:
          1 fundo-longe-esq → (0, 0)          2 fundo-longe-dir → (0, DST_H)
          3 fundo-perto-dir → (DST_W, DST_H)  4 fundo-perto-esq → (DST_W, 0)
        (antes esticava a largura no eixo de 20 m → %rede e distâncias erradas).
        Se houver pontos extra calibrados (linhas de serviço/T), usa-os em
        mínimos quadrados (findHomography) para mais precisão."""
        import cv2
        src_list = [[c[0] * frame_w, c[1] * frame_h] for c in corners]
        dst_list = [[0, 0], [0, DST_H], [DST_W, DST_H], [DST_W, 0]]
        # pontos extra opcionais {idx: [fx, fy]} em fracções 0..1
        extra = self._cfg.get("court_extra") or {}
        for k, v in sorted(extra.items()):
            idx = int(k)
            if idx in EXTRA_DST and isinstance(v, (list, tuple)) and len(v) == 2:
                src_list.append([float(v[0]) * frame_w, float(v[1]) * frame_h])
                dst_list.append(list(EXTRA_DST[idx]))
        src = self._undistort_pts(
            np.array(src_list, dtype=np.float32), frame_w, frame_h)
        dst = np.array(dst_list, dtype=np.float32)
        if len(src_list) > 4:
            H, _ = cv2.findHomography(src, dst, 0)   # mínimos quadrados c/ extras
            if H is not None:
                return H.astype(np.float32)
        return cv2.getPerspectiveTransform(src[:4], dst[:4])

    def _run(self, rtsp, codec_detect, corners, model_name, conf, fps,
             video_path=None) -> None:
        try:
            import cv2
            from ultralytics import YOLO
        except Exception as e:
            with self._lock:
                self._error = f"Falha a importar IA: {e}"
                self._running = False
            return

        # codec da câmara (reusa o detector da app de streaming se disponível)
        codec = "h264"
        if not video_path:
            try:
                codec = codec_detect(rtsp) or "h264"
            except Exception:
                pass

        try:
            # prefere a versão TensorRT (.engine) se existir — ~3x mais rápida no
            # Jetson. A .engine é gerada por export_tensorrt.py (específica do GPU).
            use, is_engine = model_name, False
            base = os.path.splitext(model_name)[0]
            here = os.path.dirname(os.path.abspath(__file__))
            for cand in (base + ".engine", os.path.join(here, base + ".engine")):
                if os.path.exists(cand):
                    use, is_engine = cand, True
                    break
            self._model = YOLO(use, task="detect") if is_engine else YOLO(use)
            self._model_kind = ("TensorRT " if is_engine else "PyTorch ") + os.path.basename(use)
        except Exception as e:
            with self._lock:
                self._error = f"Falha a carregar modelo {model_name}: {e}"
                self._running = False
            return

        # arranca o gst-launch a debitar frames BGRx crus (4 bytes/pixel) no stdout.
        # vídeo: ficheiro reamostrado a FILE_FPS fixo (frames contínuos p/ o tracker).
        # câmara: RTSP ao vivo.
        from_file = bool(video_path)
        # gravação processa-se offline → mais FPS (20) sem custo de latência:
        # metade do movimento entre frames → cruzamentos resolvem-se muito melhor.
        FILE_FPS = 20
        # FPS ao vivo configurável (live_fps na config). Mais FPS = cruzamentos
        # resolvem-se melhor, MAS a inferência tem de acompanhar (senão acumula
        # atraso) — sobe com cautela e só com modelo rápido/TensorRT.
        try:
            live_fps = int(self._cfg.get("live_fps")
                           or os.environ.get("ANALYTICS_FPS", 10))
            live_fps = max(5, min(25, live_fps))
        except Exception:
            live_fps = 10
        cmd = _gst_file_cmd(video_path, FILE_FPS) if from_file else _gst_cmd(rtsp, codec, live_fps)
        frame_bytes = CAP_W * CAP_H * 4
        # stderr do gst → ficheiro de log (para diagnosticar se o pipeline morre)
        gst_log_path = _os_path_join_out("gst_engine.log")
        gst_log = open(gst_log_path, "wb")
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=gst_log,
            bufsize=frame_bytes,
        )
        if self._H is None:
            self._H = self._build_homography(corners, CAP_W, CAP_H)
        lens_k1, lens_k2 = self._lens_params()   # lidos uma vez (fora do loop)

        # config do tracker (resolvida uma vez, fora do loop)
        import os as _os
        tcfg = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                             "bytetrack_padel.yaml")
        if not _os.path.exists(tcfg):
            tcfg = "bytetrack.yaml"
        fcount = -1
        self._last_report_save = time.time()
        try:
            while not self._stop.is_set():
                # lê exatamente 1 frame do stdout
                buf = proc.stdout.read(frame_bytes)
                if not buf or len(buf) < frame_bytes:
                    # se NÃO chegou a processar nenhum frame, o pipeline morreu →
                    # mostra o erro real do gst (últimas linhas do stderr).
                    if fcount < 0:
                        try:
                            gst_log.flush()
                            with open(gst_log_path, "r", errors="ignore") as f:
                                tail = "".join(f.readlines()[-4:]).strip()
                        except Exception:
                            tail = ""
                        with self._lock:
                            self._error = ("Pipeline de vídeo falhou no arranque. "
                                           + (tail or "ver out/gst_engine.log"))
                    elif from_file:
                        with self._lock:
                            self._error = None   # fim do vídeo = sucesso
                    else:
                        with self._lock:
                            self._error = "Stream interrompido; a recuperar…"
                    break
                # Ambos os modos: frames já vêm a FILE_FPS fixo e CONTÍNUOS (videorate).
                # Processa TODOS — o tracker (Kalman) precisa de continuidade; saltar
                # frames era o bug que fragmentava os IDs em centenas.
                fcount += 1
                if from_file:
                    now = self._started_at + (fcount / FILE_FPS)   # tempo do VÍDEO
                    with self._lock:
                        self._media_t = fcount / FILE_FPS
                else:
                    now = time.time()                              # tempo real
                    with self._lock:
                        self._media_t = now - self._started_at

                # BGRx → descarta o canal alfa (4º) → BGR para o YOLO
                frame = np.frombuffer(buf, dtype=np.uint8).reshape((CAP_H, CAP_W, 4))[:, :, :3]
                self._last_frame = frame          # p/ live camera (modo TV)

                try:
                    res = self._model.track(
                        frame, classes=[0], conf=self._conf, verbose=False,
                        persist=True, tracker=tcfg, imgsz=INFER_IMGSZ,
                    )
                except Exception as e:
                    with self._lock:
                        self._error = f"Erro na deteção: {e}"
                    continue

                boxes = res[0].boxes
                n_inside = 0
                if boxes is not None and len(boxes) > 0:
                    xyxy = boxes.xyxy.cpu().numpy()
                    # IDs do tracker (None se o tracker ainda não atribuiu)
                    if boxes.id is not None:
                        ids = boxes.id.cpu().numpy().astype(int)
                    else:
                        ids = np.full(len(xyxy), -1, dtype=int)
                    # filtro por TAMANHO da caixa: descarta minúsculas
                    # (reflexos/objetos) e gigantes (2 pessoas juntas/sombras).
                    bh = (xyxy[:, 3] - xyxy[:, 1]) / CAP_H
                    keep = (bh >= self._min_box) & (bh <= self._max_box)
                    xyxy, ids = xyxy[keep], ids[keep]
                    if len(xyxy) > 0:
                        # posição dos PÉS = centro inferior da caixa
                        feet = np.stack([(xyxy[:, 0] + xyxy[:, 2]) / 2.0, xyxy[:, 3]], axis=1)
                        # correção da lente (mesma aplicada aos cantos da homografia)
                        feet = self._undistort_pts(feet, CAP_W, CAP_H)
                        feet = feet.reshape(-1, 1, 2).astype(np.float32)
                        proj = cv2.perspectiveTransform(feet, self._H).reshape(-1, 2)
                        # assinatura de aparência (Re-ID) por deteção, na imagem crua
                        descs = [self._appearance(frame, b) for b in xyxy]
                        # margem de tolerância: quem cai um pouco fora (perspetiva/
                        # fisheye na frente) conta na BORDA mais próxima; quem está
                        # muito fora (café/staff/2º court) é ignorado.
                        MX, MY = DST_W * 0.10, DST_H * 0.10
                        seen_ids = set()
                        with self._lock:
                            # 1) recolhe deteções dentro do court (+ calor global)
                            dets = []
                            for (dx, dy), tid, desc, box in zip(proj, ids, descs, xyxy):
                                if not (-MX <= dx < DST_W + MX and -MY <= dy < DST_H + MY):
                                    continue
                                cx = int(min(DST_W - 1, max(0, dx)))
                                cy = int(min(DST_H - 1, max(0, dy)))
                                self._acc[cy, cx] += 1.0
                                n_inside += 1
                                if tid >= 0:
                                    seen_ids.add(int(tid))
                                    self._track_last[int(tid)] = (cx, cy, now)
                                dets.append({"cx": cx, "cy": cy, "xm": cx * M_PER_PX_X,
                                             "ym": cy * M_PER_PX_Y, "desc": desc,
                                             "box": box.tolist(), "tid": int(tid)})
                            # 2) atribuição UM-PARA-UM: cada jogador canónico recebe no
                            #    MÁXIMO uma caixa e cada caixa um jogador (evita 2 caixas
                            #    com o mesmo nome num cruzamento).
                            cids = self._assign_frame(dets, now)
                            # 3) métricas + calor por jogador + vista de tracking
                            frame_dets, seen_canon = [], set()
                            for d, cid in zip(dets, cids):
                                if cid is None:
                                    continue
                                seen_canon.add(cid)
                                slot = self._slots.get(cid)
                                frame_dets.append((d["box"], int(cid), slot))
                                if slot is not None:
                                    self._update_stats(slot, d["cx"], d["cy"], now)
                                    self._acc_slot[slot][d["cy"], d["cx"]] += 1.0
                                    if self._swapped:
                                        self._acc_slot_tac[slot][DST_H - 1 - d["cy"],
                                                                 DST_W - 1 - d["cx"]] += 1.0
                                    else:
                                        self._acc_slot_tac[slot][d["cy"], d["cx"]] += 1.0
                            self._active_ids = seen_ids
                            self._active_canon = seen_canon
                            self._last_dets = frame_dets
                            if self._need_assign:
                                self._try_assign_slots(now)
                with self._lock:
                    self._frames += 1
                    self._detections += n_inside
                    # KPI suavizado: mediana das últimas 5 leituras (estabiliza o
                    # número quando salta entre 2/4/5 por frame).
                    self._recent.append(n_inside)
                    if len(self._recent) > 5:
                        self._recent.pop(0)
                    s = sorted(self._recent)
                    self._current = s[len(s) // 2]
                # auto-guardar: um restart/crash nunca apaga mais de ~60 s de jogo
                if time.time() - self._last_report_save >= 60.0:
                    self._last_report_save = time.time()
                    self._save_report()
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            self._save_report()       # relatório final da sessão
        with self._lock:
            self._running = False

    def _save_report(self) -> None:
        """Grava o relatório da sessão (heatmap.png + metricas.json) em
        out/relatorios/<data-hora-do-início>/. Escrita atómica (tmp+replace),
        sempre por cima dos mesmos 2 ficheiros — o último estado vale por
        todos. Nunca levanta exceção (não pode matar a análise)."""
        try:
            import json as _json
            rdir = getattr(self, "_report_dir", None)
            if not rdir:
                return
            with self._lock:
                frames = self._frames
            if frames <= 0:
                return                      # nada analisado — não criar lixo
            os.makedirs(rdir, exist_ok=True)
            m = self.player_metrics()
            names = (self._cfg or {}).get("player_names") or {}
            for p in m.get("players", []):
                p["name"] = names.get(str(p["id"])) or ("Jogador %d" % p["id"])
            m["frames"] = frames
            m["saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            tmp = os.path.join(rdir, "metricas.json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(m, f, ensure_ascii=False, indent=1)
            os.replace(tmp, os.path.join(rdir, "metricas.json"))
            png = self.render_png()
            if png:
                tmp2 = os.path.join(rdir, "heatmap.png.tmp")
                with open(tmp2, "wb") as f:
                    f.write(png)
                os.replace(tmp2, os.path.join(rdir, "heatmap.png"))
        except Exception:
            pass

    # ─────────────────────── identidade canónica (costura) ───────────────────────
    @staticmethod
    def _appearance(frame, box):
        """Assinatura de aparência (Re-ID leve): histograma de cor HSV do TORSO
        do jogador. É o que distingue jogadores pela camisola e evita trocas de
        ID quando se cruzam. None se a caixa for pequena de mais."""
        import cv2
        x1, y1, x2, y2 = [int(v) for v in box]
        w, h = x2 - x1, y2 - y1
        if w < 8 or h < 16:
            return None
        # faixa superior-central = torso (evita pernas, court e cabeça)
        ty1, ty2 = y1 + int(0.15 * h), y1 + int(0.55 * h)
        tx1, tx2 = x1 + int(0.18 * w), x2 - int(0.18 * w)
        H, W = frame.shape[:2]
        ty1, tx1 = max(0, ty1), max(0, tx1)
        ty2, tx2 = min(H, ty2), min(W, tx2)
        if ty2 - ty1 < 4 or tx2 - tx1 < 4:
            return None
        hsv = cv2.cvtColor(frame[ty1:ty2, tx1:tx2], cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [12, 12], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist.astype(np.float32)

    @staticmethod
    def _app_dist(a, b) -> float:
        """Distância entre 2 assinaturas (0=igual, 1=diferente). 0.5 = neutro
        quando falta informação."""
        if a is None or b is None:
            return 0.5
        import cv2
        return float(cv2.compareHist(a, b, cv2.HISTCMP_BHATTACHARYYA))

    def _canon_side(self, c):
        """Metade do court onde este jogador canónico joga ('far' x<10, 'near'
        x>10) — pela regra da rede no padel. None se o slot ainda não foi
        atribuído. ASSUME lock."""
        slot = self._slots.get(c)
        if slot is None:
            return None
        far_slots = (3, 4) if self._swapped else (1, 2)
        return "far" if slot in far_slots else "near"

    def _assign_frame(self, dets, now):
        """Atribui as deteções de UM frame aos jogadores canónicos de forma
        UM-PARA-UM (ASSUME lock). Cada canónico recebe no máximo 1 deteção e cada
        deteção 1 canónico → impede 2 caixas com o mesmo jogador num cruzamento.
        Custo = distância (com previsão+gate físico) + aparência. Devolve uma
        lista de cid (mesma ordem das dets), ou None p/ deteções sem par."""
        APP_W = 1.3
        n = len(dets)
        result = [None] * n
        if n == 0:
            return result
        # 1) pares viáveis (dentro do gate físico) ordenados por custo.
        #    (NOTA: a "regra da rede" rígida foi removida — os jogadores MUDAM de
        #    ponta entre games, e prender cada um a um lado partia esse caso. A
        #    identidade através das trocas resolve-se por aparência, não posição.)
        pairs = []
        for i, d in enumerate(dets):
            for c, st in self._canon.items():
                gap = max(0.0, now - st["t"])
                g = min(gap, 2.0)
                px, py = st["x"] + st["vx"] * g, st["y"] + st["vy"] * g
                dist = ((d["xm"] - px) ** 2 + (d["ym"] - py) ** 2) ** 0.5
                gate = min(1.5 + 1.5 * gap, 6.0)
                if dist < gate:
                    cost = dist / gate + APP_W * self._app_dist(d["desc"], st.get("app"))
                    pairs.append((cost, i, c))
        pairs.sort(key=lambda t: t[0])
        used_det, used_canon = set(), set()
        for cost, i, c in pairs:
            if i in used_det or c in used_canon:
                continue
            result[i] = c
            used_det.add(i)
            used_canon.add(c)
        # 2) atualiza os canónicos emparelhados (posição, velocidade, aparência)
        for i, d in enumerate(dets):
            c = result[i]
            if c is None:
                continue
            st = self._canon[c]
            dt = now - st["t"]
            if dt > 1e-3:
                nvx, nvy = (d["xm"] - st["x"]) / dt, (d["ym"] - st["y"]) / dt
                st["vx"] = 0.6 * st["vx"] + 0.4 * nvx
                st["vy"] = 0.6 * st["vy"] + 0.4 * nvy
            st["x"], st["y"], st["t"] = d["xm"], d["ym"], now
            if d["desc"] is not None:
                if st.get("app") is None:
                    st["app"] = d["desc"]
                elif self._app_dist(d["desc"], st["app"]) < 0.45:
                    st["app"] = (0.9 * st["app"] + 0.1 * d["desc"]).astype(np.float32)
            if d["tid"] >= 0:
                self._canon_map[d["tid"]] = c
        # 3) deteções sem par → cria canónico novo se ainda há vagas (<4)
        for i, d in enumerate(dets):
            if result[i] is not None:
                continue
            if len(self._canon) < self._expected_players:
                nc = self._next_canon
                self._next_canon += 1
                self._canon[nc] = {"x": d["xm"], "y": d["ym"], "t": now,
                                   "vx": 0.0, "vy": 0.0, "app": d["desc"]}
                result[i] = nc
                if d["tid"] >= 0:
                    self._canon_map[d["tid"]] = nc
            # senão: já há 4 → 5ª deteção = falso positivo (fica None)
        return result

    def _canonical_id(self, tid: int, xm: float, ym: float, now: float, desc=None):
        """Mapeia um ID bruto do tracker para um dos 4 jogadores canónicos.
        ASSUME lock adquirido. Combina POSIÇÃO (física: sem teletransporte) com
        APARÊNCIA (cor da camisola) → resolve cruzamentos sem trocar de jogador.
        Devolve o id canónico, ou None (falso positivo). xm,ym em metros."""
        APP_W = 1.3                    # peso da aparência vs posição
        c = self._canon_map.get(tid)
        if c is not None:
            st = self._canon[c]
            dt = now - st["t"]
            if dt > 1e-3:
                nvx, nvy = (xm - st["x"]) / dt, (ym - st["y"]) / dt
                st["vx"] = 0.6 * st["vx"] + 0.4 * nvx
                st["vy"] = 0.6 * st["vy"] + 0.4 * nvy
            st["x"], st["y"], st["t"] = xm, ym, now
            # atualiza a assinatura SÓ quando é consistente (não a corrompe se o
            # tracker tiver trocado a caixa por baixo do mesmo tid)
            if desc is not None:
                if st.get("app") is None:
                    st["app"] = desc
                elif self._app_dist(desc, st["app"]) < 0.45:
                    st["app"] = (0.9 * st["app"] + 0.1 * desc).astype(np.float32)
            return c

        # ID bruto novo → herda o canónico "perdido" mais compatível (posição
        # dentro do gate físico, depois melhor combinação posição+aparência).
        best, best_score = None, 1e18
        for cid, st in self._canon.items():
            gap = now - st["t"]
            if gap < 0.15:
                continue
            g = min(gap, 2.0)
            px, py = st["x"] + st["vx"] * g, st["y"] + st["vy"] * g
            d = ((xm - px) ** 2 + (ym - py) ** 2) ** 0.5
            gate = min(1.5 + 1.5 * gap, 6.0)
            if d < gate:
                score = d / gate + APP_W * self._app_dist(desc, st.get("app"))
                if score < best_score:
                    best, best_score = cid, score
        if best is None:
            if len(self._canon) < self._expected_players:
                best = self._next_canon
                self._next_canon += 1
                self._canon[best] = {"x": xm, "y": ym, "t": now, "vx": 0.0,
                                     "vy": 0.0, "app": desc}
            else:
                # já há 4: liga ao perdido melhor (posição + aparência).
                lost = [(cid, st) for cid, st in self._canon.items()
                        if now - st["t"] >= 0.15]
                if not lost:
                    return None
                best = min(lost, key=lambda kv: (
                    ((xm - kv[1]["x"]) ** 2 + (ym - kv[1]["y"]) ** 2) ** 0.5
                    + APP_W * 3.0 * self._app_dist(desc, kv[1].get("app"))))[0]
        st = self._canon[best]
        st["x"], st["y"], st["t"] = xm, ym, now
        if desc is not None and st.get("app") is None:
            st["app"] = desc
        self._canon_map[tid] = best
        return best

    # ─────────────────────────── métricas por jogador ───────────────────────────
    def _update_stats(self, tid: int, cx: int, cy: int, now: float) -> None:
        """Acumula métricas de um jogador (ASSUME lock adquirido). cx,cy em px do
        court endireitado (0..DST_W, 0..DST_H)."""
        xm = cx * M_PER_PX_X          # metros ao longo do comprimento (0..20)
        ym = cy * M_PER_PX_Y          # metros ao longo da largura (0..10)
        st = self._stats.get(tid)
        if st is None:
            st = {"dist": 0.0, "n": 0, "sx": 0.0, "sy": 0.0,
                  "net": 0, "back": 0,
                  "zones": np.zeros((ZONES_Y, ZONES_X), dtype=np.int32),
                  "last": None,
                  "bufx": [], "bufy": [],              # janela p/ mediana
                  "mx": xm, "my": ym, "mt": now,       # última amostra robusta
                  "spd": [0, 0, 0, 0], "spd_rej": 0}   # hist 0-.5/-1/-1.5/-2 + rejeitados
            self._stats[tid] = st
        # DISTÂNCIA robusta a ruído bimodal (caixa inteira vs cortada na rede):
        # 1) mediana deslizante da posição (~1,1 s) — ignora o estado minoritário
        #    em vez de oscilar como a média;
        # 2) passo medido a cada 2 s; conta só se plausível (>=0,5 m, <=3 m/s).
        st["bufx"].append(xm)
        st["bufy"].append(ym)
        if len(st["bufx"]) > MED_WIN:
            st["bufx"].pop(0)
            st["bufy"].pop(0)
        gap = now - st["mt"]
        if gap >= SAMPLE_PERIOD_S and len(st["bufx"]) >= 5:
            bx = sorted(st["bufx"])
            by = sorted(st["bufy"])
            rx, ry = bx[len(bx) // 2], by[len(by) // 2]   # mediana por eixo
            d = ((rx - st["mx"]) ** 2 + (ry - st["my"]) ** 2) ** 0.5
            v = d / gap
            if MIN_STEP_M <= d and v < MAX_SPEED_MS:
                st["dist"] += d
                st["spd"][min(3, int(v / 0.5))] += 1   # bucket de 0.5 m/s
            elif v >= MAX_SPEED_MS:
                st["spd_rej"] += 1                     # teleporte/troca rejeitado
            st["mx"], st["my"], st["mt"] = rx, ry, now
        st["last"] = (xm, ym, now)
        st["n"] += 1
        st["sx"] += xm
        st["sy"] += ym
        # rede vs fundo (distância à linha da rede)
        if abs(xm - NET_X_M) <= NET_BAND_M:
            st["net"] += 1
        else:
            st["back"] += 1
        # zona ocupada
        zx = min(ZONES_X - 1, max(0, int(cx / DST_W * ZONES_X)))
        zy = min(ZONES_Y - 1, max(0, int(cy / DST_H * ZONES_Y)))
        st["zones"][zy, zx] += 1

    def player_metrics(self) -> dict:
        """Resumo por SLOT 1-4 (slots têm nome e equipa: A = 1-2, B = 3-4).
        As stats acumulam por slot — sobrevivem a trocas de lado."""
        with self._lock:
            total_cells = ZONES_X * ZONES_Y
            out = []
            for slot in sorted(self._stats.keys()):
                st = self._stats[slot]
                n = max(1, st["n"])
                covered = int((st["zones"] > 0).sum())
                presence_s = max(1.0, st["n"] / 10.0)   # tempo de presença (10 fps)
                out.append({
                    "id": slot,
                    "team": "A" if slot in (1, 2) else "B",
                    "pos": "Esq" if slot in (1, 3) else "Dir",
                    "distance_m": round(st["dist"], 1),
                    "avg_speed_ms": round(st["dist"] / presence_s, 2),
                    "centroid": [round(st["sx"] / n, 1), round(st["sy"] / n, 1)],
                    "net_pct": round(100 * st["net"] / n),
                    "back_pct": round(100 * st["back"] / n),
                    "coverage_pct": round(100 * covered / total_cells),
                    "samples": st["n"],
                })
            return {"players": out,
                    "sides_swapped": self._swapped,
                    "slots_assigned": len(self._slots) == self._expected_players,
                    "duration_seconds":
                    int(time.time() - self._started_at) if self._running else 0}

    # ─────────────────────────── render ───────────────────────────
    def _court_base(self, w: int, h: int):
        """Imagem de fundo do court. Se existir analytics/court_bg.(png|jpg) usa-a
        (a imagem que o utilizador forneceu, vista de cima); senão desenha um
        diagrama 2D simples."""
        import os
        import cv2
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("court_bg.png", "court_bg.jpg", "court_bg.jpeg"):
            p = os.path.join(here, name)
            if os.path.exists(p):
                img = cv2.imread(p, cv2.IMREAD_COLOR)
                if img is not None:
                    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        # fallback: diagrama desenhado
        base = np.full((h, w, 3), (120, 60, 20), dtype=np.uint8)   # BGR azul
        cv2.rectangle(base, (2, 2), (w - 3, h - 3), (255, 255, 255), 1)
        cv2.line(base, (w // 2, 2), (w // 2, h - 2), (255, 255, 255), 1)
        for fx in (0.25, 0.75):
            x = int(w * fx)
            cv2.line(base, (x, 2), (x, h - 2), (200, 200, 200), 1)
        cv2.line(base, (2, h // 2), (w - 2, h // 2), (200, 200, 200), 1)
        return base

    def _pick_acc(self, who: str, view: str):
        """Devolve o acumulador a desenhar. ASSUME lock.
        who: 'all' (todos), 'A'/'B' (dupla), '1'..'4' (jogador/slot).
        view: 'real' (posição física) ou 'tatico' (normalizado por dupla)."""
        src = self._acc_slot_tac if view == "tatico" else self._acc_slot
        if who == "all":
            if view == "tatico":
                return sum(src[s] for s in (1, 2, 3, 4))
            return self._acc                          # global: inclui não-atribuídos
        if who == "A":
            return src[1] + src[2]
        if who == "B":
            return src[3] + src[4]
        if who in ("1", "2", "3", "4"):
            return src[int(who)]
        return self._acc

    def heat_grid(self, cols: int = 100, rows: int = 56) -> dict:
        """Grelha de calor (todos os jogadores) normalizada 0..1, já orientada
        como o render (parede à esquerda). Para o canvas do modo TV desenhar
        manchas no estilo esquemático. Devolve {cols, rows, grid, max}."""
        import cv2
        with self._lock:
            acc = self._acc.copy()
        mx = float(acc.max())
        if mx <= 0:
            return {"cols": cols, "rows": rows, "grid": [], "max": 0.0}
        # acc é [largura(DST_H), comprimento(DST_W)]; canvas quer comprimento na
        # horizontal → resize p/ (cols=comprimento, rows=largura); flip vertical
        # (mesma orientação do render_png).
        g = cv2.resize(acc, (cols, rows), interpolation=cv2.INTER_AREA)
        # suaviza ligeiramente (mantém manchas distintas, não um borrão único)
        g = cv2.GaussianBlur(g, (0, 0), sigmaX=0.8, sigmaY=0.8)
        g = np.flipud(g) / max(1e-6, g.max())
        g = np.power(g, 0.7)           # gamma<1 realça o rasto sem fundir tudo
        grid = [[round(float(v), 3) for v in row] for row in g]
        return {"cols": cols, "rows": rows, "grid": grid, "max": mx}

    def latest_frame_jpeg(self, max_w: int = 960, annotate: bool = False) -> Optional[bytes]:
        """Último frame da câmara em JPEG (para a 'live camera' do modo TV).
        Reutiliza os frames já decodificados pela análise — sem 2ª ligação à
        câmara. Se annotate=True, desenha as CAIXAS + nome/cor de cada jogador
        seguido (vista de verificação do tracking). None se não há frame."""
        import cv2
        with self._lock:
            fr = None if self._last_frame is None else self._last_frame.copy()
            dets = list(self._last_dets)
            names = (self._cfg or {}).get("player_names") or {}
        if fr is None:
            return None
        if annotate:
            # cor por equipa: A (slots 1,2) azul · B (slots 3,4) verde-água · BGR
            colA, colB, colU = (255, 160, 60), (90, 210, 60), (160, 160, 160)
            for box, cid, slot in dets:
                x1, y1, x2, y2 = [int(v) for v in box]
                if slot in (1, 2):
                    col = colA
                elif slot in (3, 4):
                    col = colB
                else:
                    col = colU
                lbl = names.get(str(slot)) if slot else None
                lbl = lbl or ("J%d" % cid)
                cv2.rectangle(fr, (x1, y1), (x2, y2), col, 3)
                cv2.rectangle(fr, (x1, y1 - 26), (x1 + 12 + 14 * len(lbl), y1), col, -1)
                cv2.putText(fr, lbl, (x1 + 6, y1 - 7), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (20, 20, 20), 2)
        h, w = fr.shape[:2]
        if w > max_w:
            fr = cv2.resize(fr, (max_w, int(h * max_w / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", fr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return buf.tobytes() if ok else None

    def render_png(self, who: str = "all", view: str = "real") -> Optional[bytes]:
        """Sobrepõe o heatmap (vista de cima) à imagem de fundo do court → PNG.
        who/view selecionam o acumulador (ver _pick_acc)."""
        import cv2
        with self._lock:
            acc = self._pick_acc(who, view).copy()
        OUT_W, OUT_H = DST_W * 3, DST_H * 3          # render final mais nítido
        base = self._court_base(OUT_W, OUT_H)

        # Sub-região da imagem de fundo onde está o court azul (fracções 0..1).
        # O heatmap (retângulo perfeito) é colocado SÓ aqui, para não pintar a
        # faixa cinzenta/paredes da imagem. Ajustável via court_area na config.
        area = (self._cfg.get("court_area") or {})
        ax0 = int(OUT_W * float(area.get("left", 0.0)))
        ax1 = int(OUT_W * float(area.get("right", 1.0)))
        ay0 = int(OUT_H * float(area.get("top", 0.0)))
        ay1 = int(OUT_H * float(area.get("bottom", 1.0)))
        aw, ah = max(1, ax1 - ax0), max(1, ay1 - ay0)

        if acc.max() > 0:
            # FLIP vertical: o eixo y do DST cresce esq→dir na vista da câmara,
            # que desenhado direto dá uma vista de cima ESPELHADA (lados E/D
            # trocados para quem lê o mapa). Invertido, o mapa é uma vista de
            # cima verdadeira: parede à esquerda, lado dir. da câmara em cima.
            heat = cv2.resize(np.flipud(acc), (aw, ah), interpolation=cv2.INTER_LINEAR)
            # blur menor → focos definidos (estilo "manchas", não borrão suave)
            blur = cv2.GaussianBlur(heat, (0, 0), sigmaX=7, sigmaY=7)
            n = blur / blur.max()
            # realça os picos: gamma<1 puxa o calor médio para cima → núcleos
            # vermelhos bem marcados como na referência
            n = np.power(n, 0.7)
            norm = (n * 255).astype(np.uint8)
            cmap = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
            # alfa: transparente onde não há calor; opaco e vivo onde há
            a = np.where(norm > 18, np.clip(0.30 + n * 0.62, 0, 0.92), 0.0)
            a = a.astype(np.float32)[..., None]
            roi = base[ay0:ay1, ax0:ax1]
            base[ay0:ay1, ax0:ax1] = (roi * (1 - a) + cmap * a).astype(np.uint8)
        out = base

        ok, buf = cv2.imencode(".png", out)
        return buf.tobytes() if ok else None


# instância única partilhada pela app
engine = HeatmapEngine()
