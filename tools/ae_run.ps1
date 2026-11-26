# Run a .jsx in the open After Effects and wait for the file it writes when done.
#   powershell -File tools/ae_run.ps1 -Jsx <script.jsx> -Done <file written at the end> [-Timeout 600]
# The script is copied to an ASCII temp path first: AfterFX.exe drops scripts whose path has accents.
param([string]$Jsx, [string]$Done, [int]$Timeout = 600, [string]$AfterExe = "")
# After Effects: -AfterExe <AfterFX.exe> (a project saved by a newer After needs that version), else studio.config.json
# "after_effects", else the running one, else the newest installed version
$cfg = Join-Path (Split-Path $PSScriptRoot -Parent) "studio.config.json"
$ae = $null  # (PowerShell names are case-insensitive: the parameter cannot be called $Ae)
if ($AfterExe -and (Test-Path $AfterExe)) { $ae = $AfterExe }
if (-not $ae -and (Test-Path $cfg)) { $c = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json; if ($c.after_effects -and (Test-Path $c.after_effects)) { $ae = $c.after_effects } }
if (-not $ae) { $ae = (Get-Process AfterFX -ErrorAction SilentlyContinue | Select-Object -First 1).Path }
if (-not $ae) { $ae = Get-ChildItem "C:\Program Files\Adobe\Adobe After Effects *\Support Files\AfterFX.exe" -ErrorAction SilentlyContinue | Sort-Object FullName | Select-Object -Last 1 -ExpandProperty FullName }
if (-not $ae) { "After Effects not found: python tools/studio.py set-after <path to AfterFX.exe>"; exit 1 }
# AE must already be open with its window: started cold by -s it runs headless, cannot save frames, then quits
# a different After version already open would receive the script instead: close it first if it has nothing to save
$ae = [IO.Path]::GetFullPath($ae)
if (Get-Process AfterFX -ErrorAction SilentlyContinue | Where-Object { $_.Path -ne $ae }) { "another After Effects version is open: close it and run again"; exit 1 }
if (-not (Get-Process AfterFX -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle })) {
  Start-Process -FilePath $ae | Out-Null
  $w = 0
  while (-not (Get-Process AfterFX -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*After Effects*" }) -and $w -lt 90) { Start-Sleep -Seconds 2; $w++ }
  Start-Sleep -Seconds 12
  "started After Effects"
}
$tmp = Join-Path $env:TEMP "ae_run"; New-Item -ItemType Directory -Force $tmp | Out-Null
$copy = Join-Path $tmp ("run_" + [IO.Path]::GetFileName($Jsx) -replace '[^A-Za-z0-9_.]', '_')
Copy-Item -LiteralPath $Jsx -Destination $copy -Force
if (Test-Path -LiteralPath $Done) { Remove-Item -LiteralPath $Done -Confirm:$false }
$code = "`$.evalFile(new File('" + $copy.Replace([string][char]92, '/') + "'));"
Start-Process -FilePath $ae -ArgumentList '-s', ('"' + $code + '"') | Out-Null
$t0 = Get-Date
# dialogs opened by the import (missing fonts of the mockup template) block the script: dismiss them while waiting
while (-not (Test-Path -LiteralPath $Done) -and ((Get-Date) - $t0).TotalSeconds -lt $Timeout) {
  Start-Sleep -Seconds 2
  & (Join-Path $PSScriptRoot "ae_win.ps1") -Close auto | Where-Object { $_ -like "*closed*" } | ForEach-Object { "dismissed a blocking dialog" }
}
Start-Sleep -Seconds 1
if (Test-Path -LiteralPath $Done) { "DONE in $([int]((Get-Date) - $t0).TotalSeconds)s" } else { "TIMEOUT after $Timeout s" }
