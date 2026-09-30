param([switch]$NoOpen)
$ErrorActionPreference = 'Stop'
$panelRoot = Split-Path -Parent $PSScriptRoot
$panelPython = Join-Path $panelRoot '.venv\Scripts\python.exe'
$panelUrl = 'http://127.0.0.1:8766/'
$panelNote = 'C:\Users\Home\Documents\Flora\Flora\Jurisprudência.md'

function Get-PanelStatus {
    try { Invoke-RestMethod -Uri ($panelUrl + 'api/status') -TimeoutSec 2 }
    catch { return $null }
}

try {
    if (-not (Test-Path -LiteralPath $panelPython)) { throw 'Ambiente Python do Flora-MCP não encontrado.' }
    $panelConfig = & $panelPython -c 'import hashlib,json; from flora_mcp.config import load_config; c=load_config(); print(json.dumps(dict(directory=str(c.data_dir),key=hashlib.sha256(str(c.db_path.resolve()).encode()).hexdigest())))'
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível ler a configuração do Flora-MCP.' }
    $panelConfig = $panelConfig | ConvertFrom-Json
    $panelState = Get-PanelStatus
    if (-not $panelState) {
        if (Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue) {
            throw 'A porta 8766 está em uso por outro serviço. Nenhum processo foi encerrado.'
        }
        $panelLogs = Join-Path $panelConfig.directory 'panel-logs'
        New-Item -ItemType Directory -Path $panelLogs -Force | Out-Null
        $panelArguments = '-m flora_mcp.panel --port 8766 --data-dir "{0}"' -f $panelConfig.directory
        $panelProcess = Start-Process -FilePath $panelPython -ArgumentList $panelArguments -WorkingDirectory $panelRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $panelLogs 'stdout.log') -RedirectStandardError (Join-Path $panelLogs 'stderr.log')
        for ($panelAttempt = 0; $panelAttempt -lt 30; $panelAttempt++) {
            Start-Sleep -Milliseconds 250
            $panelState = Get-PanelStatus
            if ($panelState) { break }
            if ($panelProcess.HasExited) { throw "O painel encerrou ao iniciar. Consulte $panelLogs\stderr.log" }
        }
    }
    if (-not $panelState -or $panelState.app -ne 'flora-jurisprudencia' -or $panelState.version -ne '1' -or $panelState.acervo_key -ne $panelConfig.key) {
        throw 'Não foi possível confirmar o painel e o acervo corretos na porta 8766.'
    }
    if (-not $NoOpen) {
        $panelUri = 'obsidian://open?path=' + [uri]::EscapeDataString($panelNote)
        Start-Process $panelUri
    }
    Write-Output $panelUrl
}
catch {
    if (-not $NoOpen) {
        $panelShell = New-Object -ComObject WScript.Shell
        $null = $panelShell.Popup($_.Exception.Message, 0, 'Jurisprudência Flora', 16)
    }
    throw
}
