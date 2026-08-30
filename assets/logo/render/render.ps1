param(
  [Parameter(Mandatory=$true)][string]$Svg,
  [Parameter(Mandatory=$true)][string]$Out,
  [int]$Size = 512,
  [string]$Bg = "transparent"
)
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$svgFull = (Resolve-Path $Svg).Path
$outFull = [System.IO.Path]::GetFullPath($Out)
$bgCss = if ($Bg -eq "transparent") { "transparent" } else { $Bg }
$html = @"
<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;height:100%;background:$bgCss;display:grid;place-items:center;overflow:hidden}
img{width:${Size}px;height:${Size}px;object-fit:contain}
</style></head><body><img src="file:///$($svgFull -replace '\\','/')"></body></html>
"@
$tmpHtml = [System.IO.Path]::Combine($env:TEMP, "dsh_logo_render.html")
[System.IO.File]::WriteAllText($tmpHtml, $html, [System.Text.Encoding]::UTF8)
$profileDir = [System.IO.Path]::Combine($env:TEMP, "dsh_edge_profile")
New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
& $edge --headless=new --disable-gpu --no-first-run --no-default-browser-check --user-data-dir="$profileDir" --hide-scrollbars --force-device-scale-factor=1 --default-background-color=00000000 --window-size="$Size,$Size" --screenshot="$outFull" "file:///$($tmpHtml -replace '\\','/')" 2>$null | Out-Null
if (Test-Path $outFull) { "rendered: $outFull" } else { "FAILED" }
