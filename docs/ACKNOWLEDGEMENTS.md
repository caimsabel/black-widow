# Acknowledgements / Agradecimentos

## 🙏 github.com/AICPS/Mic-E-Mouse

**Este projeto só existe graças ao excelente trabalho dos autores do
Mic-E-Mouse.** Muito obrigado pela pesquisa, pelo repositório aberto e
pelos modelos públicos:

> 🔗 **https://github.com/AICPS/Mic-E-Mouse**
>
> *"Mic-E-Mouse: your computer mouse has big ears"*
> — **Side-Channel Audio Attack through computer mice**
> Pesquisa publicada nos anais da USENIX Security e mantida anonimamente
> durante a submissão, conforme o repositório original.

### O que é do trabalho original (AICPS/Mic-E-Mouse)

- A ideia, a metodologia do ataque de canal lateral acústico via mouse;
- O coletor C++ original (`src/mouse_logger/`), o pipeline de
  reconstrução de forma de onda (notebooks), o processamento de sinais
  base (`core/signal/preprocess.py`), as arquiteturas em `core/nn/` e os
  modelos treinados em `models/`;
- O formato de CSV de coleta (`offset, x, y`).

### O que é a adaptação brasileira (este repositório)

Camadas adaptadas para o hardware intermediário popular no Brasil
(4.000–8.000 DPI, polling de 1.000–2.000 Hz: Redragon, Pichau,
Logitech G304/G502, HyperX etc.), sem alterar o pipeline de ML original:

- `core/signal/br_mouse.py` — perfis de hardware e ganho por DPI;
- `core/signal/br_mouse_dsp.py` — janela de Nyquist contra imagens de
  resample, spectral subtraction + gate para chiado de mousepad de
  tecido, pré-ênfase, pipeline de extração completo;
- `src/mouse_logger/logger.cc` — modos genéricos de polling;
- `src/mouse_logger/mouse_logger_win.py` — coletor Windows (Raw Input
  com fallback de hook);
- `ouvir_mouse.py`, `tool/mouse2wav.py`, `black_widow/` — iniciadores e
  ferramentas de colheita/audição (inclusive o iniciador 🕷️ BLACK WIDOW).

### Créditos de uso

Se você citar este projeto em publicações, **cite primeiro o trabalho
original dos pesquisadores do AICPS/Mic-E-Mouse** — a adaptação para
hardware mainstream é descendentemente derivada de suas descobertas.
