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

# Resolução a que pedimos os frames ao gst-launch (downscale ajuda a GPU/CPU;
# 1280×720 chega para deteção de pessoas e é mais rápido que 1080p).
CAP_W, CAP_H = 1280, 720


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
        # acumulador do calor (vista de cima)
        self._acc = np.zeros((DST_H, DST_W), dtype=np.float32)
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
    def _build_homography(self, corners, frame_w, frame_h):
        import cv2
        # corners em fracções 0..1 → pixels. Ordem: fundo-esq, fundo-dir, frente-dir, frente-esq
        src = np.array([[c[0] * frame_w, c[1] * frame_h] for c in corners], dtype=np.float32)
        dst = np.array([[0, 0], [DST_W, 0], [DST_W, DST_H], [0, DST_H]], dtype=np.float32)
        return cv2.getPerspectiveTransform(src, dst)

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
            self._model = YOLO(model_name)
        except Exception as e:
            with self._lock:
                self._error = f"Falha a carregar modelo {model_name}: {e}"
                self._running = False
            return

        # arranca o gst-launch a debitar frames BGRx crus (4 bytes/pixel) no stdout.
        # vídeo: ficheiro reamostrado a FILE_FPS fixo (frames contínuos p/ o tracker).
        # câmara: RTSP ao vivo.
        from_file = bool(video_path)
        FILE_FPS = 10
        cmd = _gst_file_cmd(video_path, FILE_FPS) if from_file else _gst_cmd(rtsp, codec, FILE_FPS)
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

        # config do tracker (resolvida uma vez, fora do loop)
        import os as _os
        tcfg = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                             "bytetrack_padel.yaml")
        if not _os.path.exists(tcfg):
            tcfg = "bytetrack.yaml"
        fcount = -1
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

                try:
                    res = self._model.track(
                        frame, classes=[0], conf=self._conf, verbose=False,
                        persist=True, tracker=tcfg,
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
                        feet = feet.reshape(-1, 1, 2).astype(np.float32)
                        proj = cv2.perspectiveTransform(feet, self._H).reshape(-1, 2)
                        # margem de tolerância: quem cai um pouco fora (perspetiva/
                        # fisheye na frente) conta na BORDA mais próxima; quem está
                        # muito fora (café/staff/2º court) é ignorado.
                        MX, MY = DST_W * 0.10, DST_H * 0.10
                        seen_ids = set()
                        seen_canon = set()
                        with self._lock:
                            for (dx, dy), tid in zip(proj, ids):
                                if -MX <= dx < DST_W + MX and -MY <= dy < DST_H + MY:
                                    cx = int(min(DST_W - 1, max(0, dx)))
                                    cy = int(min(DST_H - 1, max(0, dy)))
                                    self._acc[cy, cx] += 1.0
                                    n_inside += 1
                                    if tid >= 0:
                                        seen_ids.add(int(tid))
                                        # costura: ID bruto → jogador canónico (1-4)
                                        xm = cx * M_PER_PX_X
                                        ym = cy * M_PER_PX_Y
                                        cid = self._canonical_id(int(tid), xm, ym, now)
                                        if cid is not None:
                                            seen_canon.add(cid)
                                            self._update_stats(cid, cx, cy, now)
                                        # guarda última posição do ID bruto (diagnóstico)
                                        self._track_last[int(tid)] = (cx, cy, now)
                        with self._lock:
                            self._active_ids = seen_ids
                            self._active_canon = seen_canon
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
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        with self._lock:
            self._running = False

    # ─────────────────────── identidade canónica (costura) ───────────────────────
    def _canonical_id(self, tid: int, xm: float, ym: float, now: float):
        """Mapeia um ID bruto do tracker para um dos 4 jogadores canónicos.
        ASSUME lock adquirido. Devolve o id canónico, ou None (falso positivo).
        xm,ym em METROS no court; now em segundos."""
        c = self._canon_map.get(tid)
        if c is not None:
            st = self._canon[c]
            dt = now - st["t"]
            if dt > 1e-3:
                # velocidade suavizada (EMA) — usada para prever onde estaria
                nvx, nvy = (xm - st["x"]) / dt, (ym - st["y"]) / dt
                st["vx"] = 0.6 * st["vx"] + 0.4 * nvx
                st["vy"] = 0.6 * st["vy"] + 0.4 * nvy
            st["x"], st["y"], st["t"] = xm, ym, now
            return c

        # ID bruto novo → herda o canónico "perdido" mais compatível.
        # ativo = visto neste mesmo frame (0.15 s a 10 fps) → não é candidato.
        best, best_d = None, 1e18
        for cid, st in self._canon.items():
            gap = now - st["t"]
            if gap < 0.15:
                continue
            # posição prevista (não anda mais de ~2 s na previsão)
            g = min(gap, 2.0)
            px, py = st["x"] + st["vx"] * g, st["y"] + st["vy"] * g
            d = ((xm - px) ** 2 + (ym - py) ** 2) ** 0.5
            # limiar: 1.5 m + 1.5 m/s pelo tempo perdido (cap 6 m)
            if d < min(1.5 + 1.5 * gap, 6.0) and d < best_d:
                best, best_d = cid, d
        if best is None:
            if len(self._canon) < self._expected_players:
                best = self._next_canon
                self._next_canon += 1
                self._canon[best] = {"x": xm, "y": ym, "t": now, "vx": 0.0, "vy": 0.0}
            else:
                # já há 4: liga ao perdido mais próximo (há SEMPRE 4 no court);
                # se todos os 4 foram vistos AGORA, é uma 5ª deteção = falso positivo.
                lost = [(cid, st) for cid, st in self._canon.items()
                        if now - st["t"] >= 0.15]
                if not lost:
                    return None
                best = min(lost, key=lambda kv: (xm - kv[1]["x"]) ** 2
                           + (ym - kv[1]["y"]) ** 2)[0]
        st = self._canon[best]
        st["x"], st["y"], st["t"] = xm, ym, now
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
        """Resumo por jogador: distância (m), centróide, % rede/fundo, cobertura.
        Mostra só os N IDs com mais tempo de presença (num jogo de padel são 4
        jogadores; os restantes IDs são fragmentos de trocas → descartados)."""
        with self._lock:
            total_cells = ZONES_X * ZONES_Y
            # ordena todos os IDs por nº de amostras (presença) e fica com o top-N
            ranked = sorted(self._stats.items(), key=lambda kv: -kv[1]["n"])
            top = ranked[:self._expected_players]
            out = []
            for tid, st in top:
                n = max(1, st["n"])
                covered = int((st["zones"] > 0).sum())
                presence_s = max(1.0, st["n"] / 10.0)   # tempo de presença (10 fps)
                out.append({
                    "id": tid,
                    "distance_m": round(st["dist"], 1),
                    "avg_speed_ms": round(st["dist"] / presence_s, 2),
                    "centroid": [round(st["sx"] / n, 1), round(st["sy"] / n, 1)],
                    "net_pct": round(100 * st["net"] / n),
                    "back_pct": round(100 * st["back"] / n),
                    "coverage_pct": round(100 * covered / total_cells),
                    "samples": st["n"],
                })
            # ordena pelos mais presentes (jogadores principais primeiro)
            out.sort(key=lambda p: -p["samples"])
            return {"players": out,
                    "total_tracks": len(self._stats),   # IDs brutos (diagnóstico)
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

    def render_png(self) -> Optional[bytes]:
        """Sobrepõe o heatmap (vista de cima) à imagem de fundo do court → PNG."""
        import cv2
        with self._lock:
            acc = self._acc.copy()
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
            heat = cv2.resize(acc, (aw, ah), interpolation=cv2.INTER_LINEAR)
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
