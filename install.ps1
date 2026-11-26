# motion-studio — instalação num PC Windows (uma vez por PC; pode rodar de novo para atualizar)
#   powershell -ExecutionPolicy Bypass -File install.ps1
# Instala o que faltar (Python, Node, Git, ffmpeg via winget), os pacotes Python e Node,
# liga as skills de terceiros, cria studio.config.json e roda o diagnóstico.
$ErrorActionPreference = "Continue"
$root = $PSScriptRoot
Set-Location $root
function Step($t) { Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Have($exe) { return [bool](Get-Command $exe -ErrorAction SilentlyContinue) }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }

Step "Programas (winget)"
if (-not (Have "winget")) { Write-Host "winget não encontrado: instale o 'App Installer' pela Microsoft Store e rode de novo." -ForegroundColor Red; exit 1 }
$apps = @(
  @{ exe = "python"; id = "Python.Python.3.14"; name = "Python 3.14" },
  @{ exe = "node";   id = "OpenJS.NodeJS.LTS";  name = "Node.js LTS" },
  @{ exe = "git";    id = "Git.Git";            name = "Git" },
  @{ exe = "ffmpeg"; id = "Gyan.FFmpeg";        name = "ffmpeg" }
)
foreach ($a in $apps) {
  if (Have $a.exe) { Write-Host "  ok  $($a.name)" }
  else {
    Write-Host "  instalando $($a.name)..."
    winget install -e --id $a.id --silent --accept-source-agreements --accept-package-agreements | Out-Null
    Refresh-Path
    if (Have $a.exe) { Write-Host "  ok  $($a.name)" } else { Write-Host "  !!  $($a.name): feche e abra o terminal e rode o install.ps1 de novo" -ForegroundColor Yellow }
  }
}

Step "Pacotes Python (transcrição na GPU, áudio, análise)"
python -m pip install --user --upgrade pip | Out-Null
python -m pip install --user -r "$root\requirements.txt"

Step "Pacotes Node (Playwright + Chromium, para storyboard e renders)"
npm install --no-fund --no-audit
npx --yes playwright install chromium

Step "Skills de terceiros (Remotion, HyperFrames) -> .claude\skills"
# Not in the repository (each one keeps its own author's license): restored at the versions pinned in skills-lock.json.
npx --yes skills experimental_install --agent claude-code
if ($LASTEXITCODE -ne 0) { Write-Host "  !!  skills de terceiros não instaladas (rede?). Rode de novo: npx skills experimental_install" -ForegroundColor Yellow }
$src = Join-Path $root ".agents\skills"
$dst = Join-Path $root ".claude\skills"
New-Item -ItemType Directory -Force $dst | Out-Null
if (Test-Path $src) {
  foreach ($d in Get-ChildItem $src -Directory) {
    $link = Join-Path $dst $d.Name
    if (Test-Path $link) {
      $item = Get-Item $link -Force
      if ($item.LinkType -and -not (Test-Path (Join-Path $link "SKILL.md"))) { Remove-Item $link -Force -Recurse -Confirm:$false }
    }
    if (-not (Test-Path $link)) { New-Item -ItemType Junction -Path $link -Target $d.FullName | Out-Null; Write-Host "  ligada  $($d.Name)" }
  }
}

Step "Configuração deste PC (studio.config.json)"
$cfg = Join-Path $root "studio.config.json"
if (-not (Test-Path $cfg)) {
  # the After Effects that is open now wins (a beta may be installed next to the version in use); else the newest
  $ae = (Get-Process AfterFX -ErrorAction SilentlyContinue | Select-Object -First 1).Path
  if (-not $ae) { $ae = Get-ChildItem "C:\Program Files\Adobe\Adobe After Effects *\Support Files\AfterFX.exe" -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -Last 1 -ExpandProperty FullName }
  Write-Host "  After Effects: $ae  (abra o After que você usa antes de instalar, ou troque com: python tools\studio.py set-after <AfterFX.exe>)"
  $obj = [ordered]@{ after_effects = $(if ($ae) { $ae.Replace('\', '/') } else { $null }); clients = @{} }
  $json = $obj | ConvertTo-Json -Depth 5
  [IO.File]::WriteAllText($cfg, $json, (New-Object Text.UTF8Encoding $false))
  Write-Host "  criado: $cfg"
} else { Write-Host "  já existe: $cfg (não foi alterado)" }

Step "Diagnóstico"
$env:PYTHONIOENCODING = "utf-8"
python "$root\tools\studio.py" doctor

Write-Host ""
Write-Host "Próximos passos:" -ForegroundColor Green
Write-Host "  1. Registe os clientes deste PC:  python tools\studio.py add-client <slug> ""<pasta do cliente>"""
Write-Host "     (ou um cliente novo:            python tools\studio.py new-client <slug> ""<pasta>"" --name ""Nome"")"
Write-Host "  2. Instale as fontes de cada cliente (pasta brand\fonts > botão direito > Instalar para todos os usuários)."
Write-Host "  3. Abra a pasta motion-studio no Claude (app > Code > abrir pasta) e siga o GUIA.md."
