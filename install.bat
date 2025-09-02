@echo off
SETLOCAL

REM ================================
REM 1. Cek Python
REM ================================
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo Python tidak ditemukan, akan diinstall via winget...
    winget install --id Python.Python.3 --source winget --silent
    IF ERRORLEVEL 1 (
        echo Gagal install Python. Pastikan winget tersedia.
        pause
        exit /b
    )
    echo Python berhasil diinstall.
)

REM ================================
REM 2. Install requirements.txt
REM ================================
echo Menginstall dependencies...
pip install --upgrade pip
pip install -r requirements.txt
IF ERRORLEVEL 1 (
    echo Gagal install dependencies.
    pause
    exit /b
)

pause
ENDLOCAL
