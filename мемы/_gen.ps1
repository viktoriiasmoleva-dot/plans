# Meme generator: bakes captions into template images with GDI+.
# Reads _config.json (UTF-8). Positions are % of image size.
# Output: JPEG files named in config ("out"), quality from config.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$dir = $PSScriptRoot
$cfgPath = Join-Path $dir '_config.json'
$cfg = [System.IO.File]::ReadAllText($cfgPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json

try {
  $family = New-Object System.Drawing.FontFamily('Impact')
} catch {
  $family = New-Object System.Drawing.FontFamily('Arial Black')
}

function Wrap-Lines([System.Drawing.Graphics]$g, [string]$text, [System.Drawing.Font]$font, [float]$maxW) {
  $lines = New-Object System.Collections.Generic.List[string]
  foreach ($para in ($text -split "`n")) {
    $words = $para -split '\s+' | Where-Object { $_ -ne '' }
    $cur = ''
    foreach ($w in $words) {
      $cand = if ($cur) { "$cur $w" } else { $w }
      if (($g.MeasureString($cand, $font).Width -gt $maxW) -and $cur) {
        $lines.Add($cur); $cur = $w
      } else { $cur = $cand }
    }
    if ($cur) { $lines.Add($cur) }
  }
  return ,$lines
}

$jpegCodec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() |
  Where-Object { $_.MimeType -eq 'image/jpeg' }

foreach ($item in $cfg.items) {
  $srcPath = Join-Path $dir $item.src
  if (-not (Test-Path $srcPath)) { Write-Output ("SKIP (no src) " + $item.src); continue }
  $bmp = [System.Drawing.Bitmap]::FromFile($srcPath)
  $W = $bmp.Width; $H = $bmp.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
  $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias

  foreach ($b in $item.boxes) {
    $text = if ($b.PSObject.Properties['caps'] -and $b.caps -eq $false) { $b.text } else { $b.text.ToUpper([System.Globalization.CultureInfo]::GetCultureInfo('ru-RU')) }
    $dark = ($b.PSObject.Properties['dark'] -and $b.dark -eq $true)
    $maxW = $b.w / 100.0 * $W
    $baseFontPx = if ($b.PSObject.Properties['size']) { $b.size / 100.0 * $H } else { [Math]::Min($H * 0.095, $maxW * 0.62) }
    $fontPx = $baseFontPx
    $lines = $null; $font = $null; $lineH = 0
    for ($i = 0; $i -lt 12; $i++) {
      if ($font) { $font.Dispose() }
      $font = New-Object System.Drawing.Font($family, $fontPx, [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
      $lines = Wrap-Lines $g $text $font ($maxW * 0.96)
      $lineH = $fontPx * 1.16
      $blockH = $lines.Count * $lineH
      $maxLineW = ($lines | ForEach-Object { $g.MeasureString($_, $font).Width } | Measure-Object -Maximum).Maximum
      if (($blockH -le $H * 0.46) -and ($maxLineW -le $maxW)) { break }
      $fontPx *= 0.87
    }

    $cx = ($b.l + $b.w / 2) / 100.0 * $W
    $y = $b.t / 100.0 * $H
    $fmt = New-Object System.Drawing.StringFormat
    $fmt.Alignment = [System.Drawing.StringAlignment]::Center
    $fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
    $penW = [Math]::Max(2.0, $fontPx * 0.13)

    foreach ($line in $lines) {
      $rect = New-Object System.Drawing.RectangleF(($cx - $maxW / 2 - $fontPx), $y, ($maxW + 2 * $fontPx), $lineH)
      $gp = New-Object System.Drawing.Drawing2D.GraphicsPath
      $gp.AddString($line, $family, [int][System.Drawing.FontStyle]::Regular, $fontPx, $rect, $fmt)
      if (-not $dark) {
        $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::Black, [float]$penW)
        $pen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
        $g.DrawPath($pen, $gp)
        $pen.Dispose()
        $g.FillPath([System.Drawing.Brushes]::White, $gp)
      } else {
        $g.FillPath([System.Drawing.Brushes]::Black, $gp)
      }
      $gp.Dispose()
      $y += $lineH
    }
    if ($font) { $font.Dispose() }
  }

  $g.Dispose()
  $ep = New-Object System.Drawing.Imaging.EncoderParameters(1)
  $ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]$cfg.quality)
  $outPath = Join-Path $dir $item.out
  $bmp.Save($outPath, $jpegCodec, $ep)
  $ep.Dispose()
  $bmp.Dispose()
  Write-Output ("OK " + $item.out + " " + $W + "x" + $H)
}
