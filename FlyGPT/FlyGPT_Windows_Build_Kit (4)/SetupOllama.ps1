$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName PresentationFramework
$Model = 'qwen2.5:0.5b'
$InstallerUrl = 'https://ollama.com/download/OllamaSetup.exe'
$TempInstaller = Join-Path $env:TEMP 'FlyGPT-OllamaSetup.exe'

function Show-Problem([string]$Message) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show($Message, 'FlyGPT setup', 'OK', 'Warning') | Out-Null
}

try {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        $answer = [System.Windows.MessageBox]::Show(
            "Ollama is required to run FlyGPT's local AI. Setup will download the official Ollama installer and open it. Continue?",
            'Install Ollama for FlyGPT', 'YesNo', 'Question'
        )
        if ($answer -ne 'Yes') { exit 0 }

        Invoke-WebRequest -Uri $InstallerUrl -OutFile $TempInstaller
        $process = Start-Process -FilePath $TempInstaller -Wait -PassThru
        if ($process.ExitCode -ne 0) {
            Show-Problem "The Ollama installer returned exit code $($process.ExitCode). Install Ollama manually, then run this setup again."
            exit 1
        }
        Remove-Item $TempInstaller -Force -ErrorAction SilentlyContinue
    }

    # The installer may update PATH; refresh it for this process.
    $possiblePaths = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
        (Join-Path $env:ProgramFiles 'Ollama\ollama.exe')
    )
    $ollamaExe = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if (-not $ollamaExe) {
        $ollamaExe = $possiblePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $ollamaExe) {
        Show-Problem 'Ollama was not found after installation. Restart Windows or install Ollama manually, then run SetupOllama.ps1 again.'
        exit 1
    }

    # Start the local server if the Ollama desktop app has not already started it.
    try {
        Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 | Out-Null
    } catch {
        Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }

    $pull = Start-Process -FilePath $ollamaExe -ArgumentList @('pull', $Model) -Wait -PassThru -NoNewWindow
    if ($pull.ExitCode -ne 0) {
        Show-Problem "The model download failed. Check your internet connection and free disk space, then run SetupOllama.ps1 again."
        exit 1
    }

    Show-Problem "FlyGPT's AI model ($Model) is ready. You can now open FlyGPT."
} catch {
    Show-Problem "Setup could not finish: $($_.Exception.Message)`n`nCheck your internet connection and try again."
    exit 1
}
