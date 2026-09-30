[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = 'Flora-MCP-Atualizar',
    [datetime]$At = '07:15',
    [ValidateRange(1,31)][int]$TjscDays = 7,
    [string]$DataDir
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TaskPython = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
$UpdateScript = Join-Path $PSScriptRoot 'update_once.py'
if (-not (Test-Path -LiteralPath $TaskPython)) { throw 'Execute uv sync --frozen antes de agendar.' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw 'Já existe uma tarefa com esse nome. Não será substituída.'
}
$ConfigPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not $DataDir) {
    $DataDir = & $ConfigPython -c 'from flora_mcp.config import load_config; print(load_config().data_dir)'
    if ($LASTEXITCODE -ne 0) { throw 'Configure flora.local.toml antes de agendar.' }
}
if (-not [IO.Path]::IsPathRooted($DataDir) -or -not (Test-Path -LiteralPath (Join-Path $DataDir 'acervo.sqlite'))) {
    throw 'Banco inexistente ou caminho não absoluto. Nenhuma tarefa será registrada.'
}
$Action = New-ScheduledTaskAction -Execute $TaskPython -Argument ('"{0}" --data-dir "{1}" --tjsc-days {2}' -f $UpdateScript,$DataDir,$TjscDays) -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
if ($PSCmdlet.ShouldProcess($TaskName, 'Registrar atualização diária sem iniciar agora')) {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description 'Coleta fontes oficiais STJ e TJSC para o Flora-MCP; não utiliza LLM.'
}
