<#
Sample a picture down to the colour grid the dot-matrix portrait is drawn from.

    powershell -ExecutionPolicy Bypass -File scripts/sample_portrait.ps1 -Image me.jpg

Writes scripts/portrait.json, which gen_art.py turns into assets/portrait.svg.
It is a separate step because it needs an image decoder, and Windows ships one
(System.Drawing) while the Python here has none; the JSON is committed so
gen_art.py itself stays dependency-free. Swap the picture by rerunning this
with another -Image, then `python scripts/gen_art.py`.

A square crop works best. Each cell is the area average of its block of
pixels (HighQualityBicubic downscale), not a single sampled pixel, so fine
texture does not turn into noise.
#>
param(
    [Parameter(Mandatory = $true)][string]$Image,
    [int]$Cols = 56,
    [string]$Out = ""
)
# Windows PowerShell 5.1 has no $PSScriptRoot while binding parameters.
if (-not $Out) { $Out = Join-Path $PSScriptRoot "portrait.json" }

Add-Type -AssemblyName System.Drawing

$src = [System.Drawing.Image]::FromFile((Resolve-Path $Image))
try {
    $rows = [int][math]::Round($Cols * $src.Height / $src.Width)
    $small = New-Object System.Drawing.Bitmap $Cols, $rows
    $g = [System.Drawing.Graphics]::FromImage($small)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.DrawImage($src, 0, 0, $Cols, $rows)
    $g.Dispose()

    $lines = for ($y = 0; $y -lt $rows; $y++) {
        $cells = for ($x = 0; $x -lt $Cols; $x++) {
            $c = $small.GetPixel($x, $y)
            '"{0:X2}{1:X2}{2:X2}"' -f $c.R, $c.G, $c.B
        }
        "  [" + ($cells -join ",") + "]"
    }
    $small.Dispose()
}
finally {
    $src.Dispose()
}

$json = "{`n `"cols`": $Cols,`n `"rows`": $rows,`n `"cells`": [`n" + ($lines -join ",`n") + "`n ]`n}`n"
[IO.File]::WriteAllText($Out, $json, (New-Object System.Text.UTF8Encoding $false))
Write-Output "wrote $Out ($Cols x $rows)"
