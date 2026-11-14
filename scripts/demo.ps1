<#
Windows 一键演示编排。

默认执行离线 Mock 彩排并启动同源 FastAPI 服务：
  powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1

真实模型必须显式指定 -Mode real；缺少 DS_BASE_URL、DS_API_KEY 或 DS_MODEL 时直接失败，
不会自动降级为 Mock。
#>
[CmdletBinding()]
param(
    [ValidateSet('mock', 'real')]
    [string]$Mode = 'mock',
    [int]$Port = 8000,
    [switch]$SkipBuild,
    [switch]$OpenBrowser,
    [switch]$NoAuth,
    [switch]$StopOnExit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$VenvPython = Join-Path $Repo '.venv\Scripts\python.exe'
$ServerStdout = Join-Path $Repo 'var\demo\server.stdout.log'
$ServerStderr = Join-Path $Repo 'var\demo\server.stderr.log'
$HealthUrl = "http://127.0.0.1:$Port/api/v1/health"
$WebUrl = "http://127.0.0.1:$Port/"

function Stop-DemoServer {
    param([int]$ProcessId)
    if ($ProcessId -gt 0) {
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            Write-Host "停止演示服务 (PID $ProcessId)..."
            Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )
    Write-Host "`n== $Title ==" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "步骤失败：$Title（退出码 $LASTEXITCODE）"
    }
}

function Get-PasswordSha256 {
    if ($env:API_AUTH_PASSWORD_SHA256 -and $env:API_AUTH_PASSWORD_SHA256 -match '^[0-9a-fA-F]{64}$') {
        return $env:API_AUTH_PASSWORD_SHA256
    }

    $password = $env:DEMO_PASSWORD
    if (-not $password) {
        $secure = Read-Host '请输入演示账号密码（不会写入仓库）' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try {
            $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        finally {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
    if (-not $password) { throw '演示密码不能为空。' }

    $bytes = [Text.Encoding]::UTF8.GetBytes($password)
    $hash = [Security.Cryptography.SHA256]::Create().ComputeHash($bytes)
    return ([BitConverter]::ToString($hash) -replace '-', '').ToLowerInvariant()
}

function Assert-PortFree {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        $owners = ($listener | Select-Object -ExpandProperty OwningProcess -Unique) -join ', '
        throw "端口 $Port 已被占用（PID $owners）。请先停止旧服务，或用 -Port 指定其他端口。"
    }
}

function Wait-Health {
    for ($i = 0; $i -lt 30; $i++) {
        try {
            $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
            if ($response.status -eq 'ok') { return $response }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "服务未能在 15 秒内通过健康检查：$HealthUrl。请查看 $ServerStderr"
}

if ($Port -lt 1 -or $Port -gt 65535) { throw 'Port 必须在 1 到 65535 之间。' }
if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "找不到 $VenvPython。请先创建虚拟环境并安装依赖。"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw '找不到 npm。请先安装 Node.js 18+。'
}
if (-not $NoAuth -and -not (Test-Path -LiteralPath (Join-Path $Repo 'web\src\pages\auth\LoginPage.tsx'))) {
    throw '当前工作树前端没有登录页。请先切到包含最新登录功能的 main，或用 -NoAuth 做无登录链路检查。'
}
Assert-PortFree
if ($Mode -eq 'real') {
    foreach ($name in @('DS_BASE_URL', 'DS_API_KEY', 'DS_MODEL')) {
        if (-not [Environment]::GetEnvironmentVariable($name)) {
            throw "真实模式缺少 $name。请在当前 PowerShell 进程设置后重试；不会自动切换到 Mock。"
        }
    }
}

$serverPid = 0
try {
    if (-not $SkipBuild) {
        if (-not (Test-Path -LiteralPath (Join-Path $Repo 'web\node_modules'))) {
            Invoke-Step '安装前端依赖' { npm --prefix web ci }
        }
        Invoke-Step '构建前端' { npm --prefix web run build }
    }

    $demoArgs = @('-m', 'engine.demo', 'all', '--reset')
    if ($Mode -eq 'mock') {
        $demoArgs += @('--dev', '--visitors-dir', 'sim/visitors')
        $demoArgs += '--mock'
        # 小规模彩排让评委机在一分钟左右得到完整报告。真实运行不缩减来访数。
        $demoArgs += @('--n-a', '3', '--n-b', '3', '--n-c', '3', '--max-sessions', '3')
    }
    else {
        # 已在启动前检查 DS_*；这里保留正式分组，不缩减来访数量。
    }
    Invoke-Step "执行 $Mode 完整演示彩排" { & $VenvPython @demoArgs }

    $env:API_DATA_SOURCE = 'files'
    $env:API_SERVE_WEB = '1'
    if ($NoAuth) {
        $env:API_AUTH_MODE = 'none'
        Remove-Item Env:API_AUTH_PASSWORD_SHA256 -ErrorAction SilentlyContinue
    }
    else {
        $env:API_AUTH_MODE = 'demo'
        $env:API_AUTH_USERNAME = if ($env:API_AUTH_USERNAME) { $env:API_AUTH_USERNAME } else { 'demo' }
        $env:API_AUTH_PASSWORD_SHA256 = Get-PasswordSha256
    }

    New-Item -ItemType Directory -Path (Split-Path $ServerStdout) -Force | Out-Null
    Remove-Item -LiteralPath $ServerStdout, $ServerStderr -Force -ErrorAction SilentlyContinue
    Assert-PortFree
    $serverArgs = @('-m', 'uvicorn', 'api.main:app', '--host', '127.0.0.1', '--port', [string]$Port)
    $server = Start-Process -FilePath $VenvPython -ArgumentList $serverArgs -WorkingDirectory $Repo `
        -RedirectStandardOutput $ServerStdout -RedirectStandardError $ServerStderr -WindowStyle Hidden -PassThru
    $serverPid = $server.Id
    $health = Wait-Health

    Write-Host "`n演示服务已启动：$WebUrl" -ForegroundColor Green
    Write-Host "健康检查：$HealthUrl"
    Write-Host "引擎彩排模式：$Mode；API 数据源：$($health.data_source)；API 执行模式：$($health.execution_mode)"
    if (-not $NoAuth) {
        Write-Host '登录账号：使用部署方提供的演示账号（密码未写入脚本或日志）'
    }
    Write-Host "服务日志：$ServerStdout / $ServerStderr"

    if ($OpenBrowser) {
        Start-Process $WebUrl
    }
    if (-not $StopOnExit) {
        Write-Host '服务将保持运行。评委演示结束后按 Enter 停止服务。'
        [void](Read-Host)
    }
}
finally {
    if ($serverPid -gt 0) { Stop-DemoServer -ProcessId $serverPid }
}
