@echo off
rem Abre o painel do Arsenal (motion-studio) no navegador. Dois cliques e pronto; feche esta janela para parar.
cd /d "%~dp0"
python tools\studio.py arsenal --serve
if errorlevel 1 pause
