<#
  ATLAS RESEARCH — news-agent-install.ps1
  Cài agent tin tức lên máy Windows có GPU (máy chạy studio YouTube / ComfyUI):
    - tác vụ "AtlasNews-Scan": mỗi 60 phút quét VnExpress, viết lại qua OpenRouter,
      vẽ ảnh bằng GPU (ComfyUI + FLUX.2 klein qua lib\images.py), gửi nháp Telegram;
    - tác vụ "AtlasNews-Bot": luôn chạy khi đăng nhập, bấm Duyệt thì commit + push.

  Chạy trong PowerShell (không cần quyền Administrator):
    powershell -ExecutionPolicy Bypass -File scripts\news-agent-install.ps1 `
        -RepoDir D:\atlas-news\repo

  Idempotent. Lần đầu script clone repo + tạo news_agent\.env rồi dừng để bạn điền;
  điền xong chạy lại để đăng ký tác vụ.
#>
param(
    [string]$RepoDir = "D:\atlas-news\repo",
    [string]$RepoUrl = "https://github.com/Hoang-Minh-Nghia/atlas-research-deploy.git",
    [string]$Branch = "main",
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
function Log($m)  { Write-Host "[news-agent] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[news-agent][warn] $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "[news-agent][error] $m" -ForegroundColor Red; exit 1 }

# ---- 1. Kiểm tra công cụ ----
foreach ($cmd in @("git", $Python)) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Die "Không tìm thấy '$cmd' trong PATH." }
}
& $Python -c "import sys; sys.exit(sys.version_info < (3, 10))"
if ($LASTEXITCODE -ne 0) { Die "Cần Python >= 3.10." }

# ---- 2. Clone riêng cho agent (agent tự reset --hard, đừng sửa tay ở đây) ----
if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
    Log "Clone $RepoUrl vào $RepoDir"
    New-Item -ItemType Directory -Force -Path (Split-Path $RepoDir) | Out-Null
    git clone -q $RepoUrl $RepoDir
    if ($LASTEXITCODE -ne 0) { Die "Clone thất bại — kiểm tra quyền GitHub (Git Credential Manager) rồi chạy lại." }
}
git -C $RepoDir fetch -q origin $Branch
git -C $RepoDir checkout -q -B $Branch "origin/$Branch"
git -C $RepoDir config user.name "Atlas News Bot"
git -C $RepoDir config user.email "news-bot@atlas-research.invalid"
git -C $RepoDir config core.autocrlf false
$AgentDir = Join-Path $RepoDir "news_agent"
if (-not (Test-Path $AgentDir)) { Die "Nhánh $Branch chưa có thư mục news_agent\ — merge code agent vào nhánh này trước." }

# ---- 3. Virtualenv (đặt ngoài repo) ----
$StateDir = Join-Path $env:LOCALAPPDATA "atlas-news"
$Venv = Join-Path $StateDir "venv"
New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    Log "Tạo virtualenv $Venv"
    & $Python -m venv $Venv
}
$VPy = Join-Path $Venv "Scripts\python.exe"
& $VPy -m pip install -q --upgrade pip
& $VPy -m pip install -q -r (Join-Path $AgentDir "requirements.txt")

# ---- 4. File cấu hình ----
$EnvFile = Join-Path $StateDir "atlas-news.env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $AgentDir ".env.example") $EnvFile
    (Get-Content $EnvFile -Encoding UTF8) `
        -replace '^REPO_DIR=.*', "REPO_DIR=$($RepoDir -replace '\\','/')" `
        -replace '^GIT_BRANCH=.*', "GIT_BRANCH=$Branch" |
        Set-Content $EnvFile -Encoding UTF8
    Log "Đã tạo $EnvFile"
}
if (Select-String -Path $EnvFile -Pattern "__CHANGE_ME" -Quiet) {
    Warn "$EnvFile còn giá trị __CHANGE_ME__ — điền OPENROUTER_API_KEY, TELEGRAM_* rồi chạy lại script."
    exit 0
}

# ---- 5. Tác vụ Task Scheduler ----
$common = @{ WorkingDirectory = $RepoDir }
$envArg = "set ATLAS_NEWS_ENV=$EnvFile&& set PYTHONIOENCODING=utf-8&&"
$LogDir = Join-Path $StateDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$scanCmd = "/c $envArg `"$VPy`" -m news_agent.scan >> `"$LogDir\scan.log`" 2>&1"
$botCmd  = "/c $envArg `"$VPy`" -m news_agent.bot >> `"$LogDir\bot.log`" 2>&1"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45)
$scanTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours((Get-Date).Hour + 1) `
    -RepetitionInterval (New-TimeSpan -Minutes 60)
Register-ScheduledTask -TaskName "AtlasNews-Scan" -Force -Settings $settings -Trigger $scanTrigger `
    -Action (New-ScheduledTaskAction -Execute "cmd.exe" -Argument $scanCmd @common) `
    -Description "Atlas Research: quét tin VnExpress mỗi giờ, gửi nháp lên Telegram" | Out-Null

$botSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName "AtlasNews-Bot" -Force -Settings $botSettings `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) `
    -Action (New-ScheduledTaskAction -Execute "cmd.exe" -Argument $botCmd @common) `
    -Description "Atlas Research: bot Telegram duyệt bài" | Out-Null
Start-ScheduledTask -TaskName "AtlasNews-Bot"

Log "Đã đăng ký AtlasNews-Scan (mỗi 60 phút) và AtlasNews-Bot (khi đăng nhập, đang chạy)."
Log "Chạy thử ngay:  Start-ScheduledTask AtlasNews-Scan"
Log "Xem log:        Get-Content `"$LogDir\bot.log`" -Wait"
