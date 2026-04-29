@echo off
title Quadro de Dicas Guardiola
cd /d "%~dp0"
echo Iniciando o Quadro de Dicas Guardiola...
echo.
echo O navegador abrira automaticamente em http://localhost:8501
echo Para encerrar, feche esta janela ou pressione Ctrl+C.
echo.
streamlit run streamlit_app.py
pause
