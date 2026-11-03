# TUTORIAL SIMPLES — OUVIR O SEU MOUSE (Logitech G304)

Passo a passo para o cmd.exe do Windows. Copie e cole **uma linha por vez**.

---

## PASSO 0 — Preparar (uma vez só)

Abra o cmd e vá para a pasta do projeto:

```bat
cd C:\Users\Casa\Downloads\Mouse\Mic-E-Mouse
```

Instale as dependências do caminho de áudio (só numpy + scipy):

```bat
python -m pip install -r requirements.txt
```

> Depende de internet. Se der timeout, rode de novo até concluir
> (são 2 pacotes pequenos).

---

## PASSO 1 — Configurar o mouse (G304)

No software **G Hub** (se instalado):
- DPI: **12.000** (o G304 suporta até isso; mais DPI = sinal mais forte)
- Polling rate: o G304 é fixo em **1.000 Hz** (não precisa mexer)

Sem G Hub: não tem problema — o script detecta o DPI automaticamente
pelo sinal. Na dúvida use `--dpi 12000`.

---

## PASSO 2 — Coletar (a parte que "liga o microfone" do mouse)

```bat
python ouvir_mouse.py coletar
```

- Ele mostra: `output: data\data_win_<data-hora>.csv`
- **Mova o mouse continuamente por 30–60 segundos** (circles, curvas,
  como quem escreve uma frase com o cursor)
- **Ctrl+C** para encerrar. Aparece `concluido: N eventos gravados`.

Alternativa com desligamento automático (faça os círculos enquanto roda):

```bat
python ouvir_mouse.py coletar --seconds 45
```

> Importante: mova o mouse MESMO durante a coleta. Se você ficar parado,
> o CSV só vai ter ruído de fundo (nada audível).

---

## PASSO 3 — Extrair o áudio e ouvir

Tudo bem se você não souber o nome exato do CSV — sem passar arquivo,
o script pega **o CSV mais novo da pasta `data/` automaticamente**:

```bat
python ouvir_mouse.py extrair
```

Ou com o nome completo (veja na pasta `data\`):

```bat
python ouvir_mouse.py extrair data\data_win_2026-11-03_21-10-00.csv
```

Especificando o seu hardware:

```bat
python ouvir_mouse.py extrair data\data_win_2026-11-03_21-10-00.csv --profile logitech_g304
```

O WAV é gravado em `out\` e **abre no player padrão automaticamente**.

---

## ERROS COMUNS (e o que significam)

| Você digitou | Problema | Correto |
|---|---|---|
| `--profile --logitech_g304` | o valor não leva `--` | `--profile logitech_g304` |
| `python tool/mouse2wav.py --logitech_g304` | nome de perfil não é flag | use `--profile logitech_g304` |
| `src/mouse_logger/mouse_logger_win.py` | cmd não executa caminho assim | `python src\mouse_logger\mouse_logger_win.py` |
| `data/rec.csv` não existe | arquivo não foi coletado ainda | rode PASSO 2 |
| `unknown interpolation method` | (não deve ocorrer) | me avise |
| `dependencia faltando (numpy)` | PASSO 0 incompleto | `python -m pip install -r requirements.txt` |

---

## AJUSTES FINOS (depois que o básico funcionar)

```bat
:: sem o chiado do mousepad mais agressivo:
python ouvir_mouse.py extrair --profile logitech_g304 --seconds 30

:: comparar o sinal em BRUTO (sem qualquer DSP):
python ouvir_mouse.py extrair --stage raw

:: som mais "natural" (inverte a pré-ênfase aguda):
python ouvir_mouse.py extrair --deemph

:: ouvir os primeiros 30 s do arquivo inteiro:
python ouvir_mouse.py extrair --seconds 30
```

## O QUE ESPERAR OUVIR

Toda extração garante **no mínimo 30 segundos de áudio**: coletas mais
curtas são preenchidas por loop com crossfade suave (o script avisa
`[min-listen] gravacao X s < 30 s -> preenchida...`).

O G304 tem polling de 1.000 Hz, então o teto físico do áudio é ~500 Hz.
Você deve ouvir: **graves, sopro do movimento, entonação** — o "timbre" do
que o sensor enxergou. Vozes com clareza de palavras exigem hardware de
8 kHz (Razer Viper 8KHz) — para o G304 o resultado é reconstrução
musical/granular, não uma gravação de voz limpa.

Tudo pronto? Duvidas: rode `python ouvir_mouse.py perfis` para ver as
características de cada mouse, ou `python ouvir_mouse.py` sem argumento
para o menu interativo.
