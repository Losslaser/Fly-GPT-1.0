@echo off
setlocal
cd /d "%~dp0"
title Build FlyGPT for Windows

echo ======================================
echo           FlyGPT Windows Build
echo ======================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python Launcher was not found.
  echo Install Python 3.11 or newer from python.org, then try again.
  pause
  exit /b 1
)

py -m pip install --upgrade pip
if errorlevel 1 goto failed
py -m pip install --upgrade pyinstaller
if errorlevel 1 goto failed

echo.
echo Building FlyGPT. This can take a few minutes...
py -m PyInstaller --noconfirm --clean --windowed --onedir --name FlyGPT main.py
if errorlevel 1 goto failed

if exist "connections_princeton.csv" (
  copy /Y "connections_princeton.csv" "dist\FlyGPT\connections_princeton.csv" >nul
) else (
  echo WARNING: connections_princeton.csv not found; connectome data will not load.
)
if exist "Supplemental_file1_neuron_annotations.tsv" (
  copy /Y "Supplemental_file1_neuron_annotations.tsv" "dist\FlyGPT\Supplemental_file1_neuron_annotations.tsv" >nul
) else (
  echo WARNING: Supplemental_file1_neuron_annotations.tsv not found; annotations will not load.
)
if exist "SetupOllama.ps1" copy /Y "SetupOllama.ps1" "dist\FlyGPT\SetupOllama.ps1" >nul
if exist "settings.json" copy /Y "settings.json" "dist\FlyGPT\settings.json" >nul
if exist "README_INSTALLATION.txt" copy /Y "README_INSTALLATION.txt" "dist\FlyGPT\README_INSTALLATION.txt" >nul

echo.
echo Build complete: dist\FlyGPT\FlyGPT.exe
echo Keep the whole dist\FlyGPT folder together.
echo To create the installer, open FlyGPT.iss with Inno Setup Compiler.
echo.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
