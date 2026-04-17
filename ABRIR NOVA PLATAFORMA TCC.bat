@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"
set "APP_DIR=%~dp0nova_plataforma_tcc"

if not exist "%APP_DIR%\app.py" (
    echo.
    echo Nao encontrei a nova plataforma em:
    echo %APP_DIR%\app.py
    echo.
    pause
    exit /b 1
)

set "PYTHON_CMD="

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo.
    echo Python nao foi encontrado neste computador.
    echo Instale o Python e tente novamente.
    echo.
    pause
    exit /b 1
)

echo Verificando dependencias...
%PYTHON_CMD% -c "import streamlit, pandas, openpyxl, requests, playwright" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Algumas dependencias nao estao instaladas.
    echo Vou tentar instalar automaticamente agora...
    echo.
    %PYTHON_CMD% -m pip install -r "%APP_DIR%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo Nao consegui instalar as dependencias automaticamente.
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Abrindo a nova plataforma TCC...
echo Quando quiser fechar o site, basta fechar esta janela.
echo.

%PYTHON_CMD% -m streamlit run "%APP_DIR%\app.py" --server.headless false

echo.
echo A plataforma foi encerrada.
echo.
pause
