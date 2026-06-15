# Módulo da bola (pós-jogo) — plano

Objetivo: a partir de uma **gravação** do jogo, produzir **trajetória da bola**,
**velocidade de pancada (km/h)** e (mais tarde) **tipo de pancada**. É
**processamento pós-jogo** — nenhum tracker de bola corre em tempo real no nosso
Jetson com fiabilidade (confirmado na pesquisa).

## Verdade importante (descoberta na pesquisa)
- O melhor ponto de partida é **`michele98/ball_tracking_padel`** (TrackNetV2,
  **licença MIT**, feito **para padel**). Tem treino + a pasta `trajectories/`
  (ajuste/filtragem de trajetória) reutilizável.
- **NÃO inclui pesos treinados** → temos de **TREINAR o modelo primeiro**.
- Treino faz-se **FORA do Jetson** (PC/cloud com GPU decente), não no Orin NX.
- Dataset pronto: **PadelTracker100** (CC BY 4.0, ~100k frames, 2 jogos pro,
  anotado para bola + posições + pose + tipo de pancada). A câmara dele é
  **elevada por trás do vidro (7,6 m alto, 15,5 m atrás)** — quase igual à nossa
  → transfere bem para o nosso ângulo.
- Referência de arquitetura: **`AlvaroNovillo/DS_Padel`** (YOLOv8 + TrackNet +
  homografia = a nossa stack).

## Pipeline alvo
1. **Treinar** TrackNetV2 (ball_tracking_padel) no PadelTracker100 — fora do Jetson.
2. **Inferência pós-jogo**: correr o modelo sobre a gravação .mp4 → posição da
   bola em píxeis por frame (+ confiança).
3. **Trajetória → court**: desdistorcer + homografia (REUSAR a nossa calibração:
   `camera_calib.json` + `court_corners`/`court_extra`) → bola em metros.
4. **Velocidade**: derivada da posição suavizada → km/h; **pancada** = pico de
   velocidade / inversão de direção junto a um jogador.
5. **Saída**: vídeo com a trajetória sobreposta + JSON (velocidade máx./média por
   pancada, nº de pancadas, etc.). Integrar nos relatórios e no modo TV.

## O que JÁ está pronto do nosso lado
- Homografia + correção de lente (motor) — passo 3 reaproveita-as.
- Auto-guardar de relatórios — a saída da bola entra aqui.

## Próximas ações (quando avançarmos)
- [ ] Obter PadelTracker100 e treinar TrackNetV2 (fora do Jetson). Erro-alvo: bola
      detetada na maioria dos frames com bola visível.
- [ ] `ball_postgame.py`: detetor (modelo treinado) → trajetória → court → km/h.
- [ ] Validar velocidades contra senso comum (smash pro ~ 100-120 km/h).
- [ ] Overlay + JSON + integração nos relatórios/TV.

Notas de licença: ball_tracking_padel = MIT (reutilizável); PadelTracker100 =
CC BY 4.0 (atribuir); TennisCourtDetector = **sem licença** (não usar). BoxMOT =
AGPL + Python 3.10+ (não serve para o nosso Jetson — por isso fizemos Re-ID próprio).
