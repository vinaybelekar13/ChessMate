$files = @(".\index.html", ".\js\app.js", ".\js\puzzles.js", ".\js\book-reader.js")
$enc = [System.Text.UTF8Encoding]::new($false)

function U([int[]]$codes) {
    return -join ($codes | ForEach-Object { [char]$_ })
}

$rep = @(
    @((U @(0x00E2,0x20AC,0x201D)), (U @(0x2014))),
    @((U @(0x00E2,0x20AC,0x201C)), (U @(0x2013))),
    @((U @(0x00E2,0x20AC,0x00A6)), (U @(0x2026))),
    @((U @(0x00C2,0x00B7)), (U @(0x00B7))),
    @((U @(0x00E2,0x2020,0x2019)), (U @(0x2192))),
    @((U @(0x00E2,0x2020,0x201C)), (U @(0x2193))),
    @((U @(0x00C3,0x2014)), (U @(0x00D7))),
    @((U @(0x00E2,0x0161,0x00AA)), (U @(0x26AA))),
    @((U @(0x00E2,0x0161,0x00AB)), (U @(0x26AB))),
    @((U @(0x00E2,0x0153,0x201C)), (U @(0x2713))),
    @((U @(0x00E2,0x20A2,0x2022)), (U @(0x2022))),
    @((U @(0x00C2,0x00BD)), (U @(0x00BD))),
    @((U @(0x00E2,0x2030,0x2248)), (U @(0x2248))),
    @((U @(0x00E2,0x2021,0x2026)), (U @(0x21C5)))
)

foreach ($file in $files) {
    if (!(Test-Path -LiteralPath $file)) {
        Write-Host "Missing: $file" -ForegroundColor Yellow
        continue
    }

    $path = (Resolve-Path -LiteralPath $file).Path
    $original = [IO.File]::ReadAllText($path)
    $content = $original

    foreach ($pair in $rep) {
        $content = $content.Replace([string]$pair[0], [string]$pair[1])
    }

    if ($content -ne $original) {
        $backup = "$path.before-symbol-repair-v2"
        if (!(Test-Path -LiteralPath $backup)) {
            Copy-Item -LiteralPath $path -Destination $backup
        }
        [IO.File]::WriteAllText($path, $content, $enc)
        Write-Host "Repaired: $file" -ForegroundColor Green
    } else {
        Write-Host "No matching patterns: $file"
    }
}
Write-Host "Repair pass complete."
