# 一键启动（Windows PowerShell）
# 用法：  .\scripts\start.ps1
#        .\scripts\start.ps1 -Port 8080

param(
    [int]$Port = 8000,
    [string]$HostAddr = "127.0.0.1"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[1/3] 创建虚拟环境 ..." -ForegroundColor Cyan
    try {
        python -m venv .venv
    } catch {
        Write-Host "venv 创建失败（常见原因：路径含中文）。改用 --without-pip 方式 ..." -ForegroundColor Yellow
        python -m venv --without-pip .venv
        python -m pip --python .\.venv\Scripts\python.exe install -r requirements.txt
    }
}

$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path ".venv\Lib\site-packages\fastapi")) {
    Write-Host "[2/3] 安装依赖 ..." -ForegroundColor Cyan
    & $py -m pip install -r requirements.txt
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "已生成 .env，请按需修改模型配置后重新运行。" -ForegroundColor Yellow
}

Write-Host "[3/3] 启动服务： http://${HostAddr}:${Port}" -ForegroundColor Green
& $py -m uvicorn app.main:app --host $HostAddr --port $Port
