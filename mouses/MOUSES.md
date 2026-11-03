# 🐭 Dados dos Mouses (Mic-E-Mouse BR)

Base de dados dos perfis de hardware suportados pela ferramenta. Estes dados
 alimentam `core/signal/br_mouse.py` (arena o arquivo-fonte, e
`mouses/profiles.json` é o snapshot legível gerado automaticamente de lá).

## Referência do paper (hardware original)

| Mouse | DPI | Polling | Uso no paper |
|---|---|---|---|
| Razer Viper 8KHz | 20.000 (max) | 8.000 Hz | Hardware de referência, >16.000 DPI; os modelos públicos foram treinados nessa faixa |

## Perfis de mouses brasileiros (4.000–8.000 DPI)

Key para uso: `--profile <key>` no `ouvir_mouse.py` / `mouse2wav.py` /
`black_widow`.

| key | Mouse | DPI | Polling | Observação |
|---|---|---|---|---|
| `custom` | Custom | 8.000 | 1.000 Hz | Override livre de DPI/polling via CLI |
| `hyperx_pulsefire` | HyperX Pulsefire Haste | 16.000 | 1.000 Hz | Até 16k DPI, polling ainda 1 kHz |
| `logitech_g304` | Logitech G304/G305 | 12.000 | 1.000 Hz | Best-seller Logitech no Brasil (polling fixo 1 kHz) |
| `logitech_g502` | Logitech G502 HERO | 25.600 | 1.000 Hz | Usado no paper como referência de 1 kHz |
| `pichau_p701` | Pichau P701 | 6.400 | 1.000 Hz | Mouse gamer de marca própria |
| `razer_viper_8k` | Razer Viper 8KHz | 20.000 | 8.000 Hz | Hardware de referência do paper |
| `redragon_cobra` | Redragon Cobra | 10.000 | 1.000 Hz | Variante Cobra; móvel a 12.4k |
| `redragon_m711` | Redragon M711 Cobra | 7.200 | 1.000 Hz | Redragon gamer intermediário comum |
| `redragon_m808` | Redragon M808 Storm | 12.400 | 1.000 Hz | Top Redragon; polling continua 1 kHz |

## Teto físico de áudio por polling (o que você consegue ouvir)

| Polling | Teto Nyquist | Banda útil típica |
|---|---|---|
| 1.000 Hz | ~500 Hz | graves, F0 da voz, entonação |
| 2.000 Hz | ~1.000 Hz | graves + formantes baixos |
| 4.000 Hz | ~2.000 Hz | boa parte da banda de fala |
| 8.000 Hz | ~4.000 Hz | banda de voz completa (referência) |

> A qualidade de reconstrução escala com o **polling rate** (tempo), não com o
> DPI (amplitude). O DPI entra como ganho de sensibilidade no DSP.

## Dados coletados

Os CSVs de coleta (formato do paper: `offset, x, y` com deltas em
microssegundos e contagens crua do sensor) ficam em `bin/data/` quando
coletados pelo Black Widow, e as saídas de áudio em `bin/out/`.

## Como adicionar um mouse novo

1. Edite o dict `PROFILES` em `core/signal/br_mouse.py` (ou o local em
   `bin/core/signal/br_mouse.py`).
2. Rode o snapshot:
   ```bash
   python -c "import sys; sys.path.insert(0,'.') ; from core.signal.br_mouse import PROFILES; import json; print(json.dumps({k: v.__dict__ for k, v in PROFILES.items()}, indent=2))"
   ```
3. Atualize a tabela acima com a mesma linha.
