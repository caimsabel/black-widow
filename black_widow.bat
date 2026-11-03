@echo off
REM ==========================================================================
REM  BLACK WIDOW - iniciador do Mic-E-Mouse (wrapper para cmd.exe do Windows)
REM  Desenha o banner colorido e chama o bundle standalone em bin\.
REM
REM  Uso:  black_widow\black_widow.bat            -> menu
REM        black_widow\black_widow.bat extrair    -> extrair direto (CSV mais novo)
REM        black_widow\black_widow.bat coletar    -> coleta direta
REM ==========================================================================
setlocal
python "%~dp0banner.py" >NUL 2>&1 || GOTO orphan
python "%~dp0banner.py"

REM repasse direto do bundle da pasta
if "%~1"=="" GOTO menu
cd /d "%~dp0bin"
python ouvir_mouse.py %*
GOTO end

:menu
cd /d "%~dp0bin"
python ouvir_mouse.py
GOTO end

:orphan
echo.
echo [ERRO] python nao encontrado. Instale em https://python.org (marque "Add to PATH") e reabra o cmd.

:end
endlocal
