$ErrorActionPreference = "Stop"

$root = (Get-Location).Path

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $root "_mojibake-backup-$stamp"

New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null

$extensions = @(
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".html",
    ".css",
    ".json"
)

$excluded = '\\(node_modules|\.git|\.venv|venv|__pycache__|_mojibake-backup-)\\'

$files = Get-ChildItem $root -Recurse -File |
    Where-Object {
        $_.Extension -in $extensions -and
        $_.FullName -notmatch $excluded
    }

$utf8 = New-Object System.Text.UTF8Encoding($false)

$cp1252 = [System.Text.Encoding]::GetEncoding(
    1252,
    [System.Text.EncoderExceptionFallback]::new(),
    [System.Text.DecoderExceptionFallback]::new()
)

function Get-MojibakeScore {
    param(
        [string]$Text
    )

    $chars = @(
        [char]0x00C3
        [char]0x00C2
        [char]0x00E2
        [char]0x00F0
    )

    $score = 0

    foreach ($c in $chars) {
        $score += ([regex]::Matches(
            $Text,
            [regex]::Escape([string]$c)
        )).Count
    }

    return $score
}

$changed = @()

foreach ($file in $files) {

    $original = [System.IO.File]::ReadAllText(
        $file.FullName,
        $utf8
    )

    $text = $original

    $initialScore = Get-MojibakeScore $text

    if ($initialScore -eq 0) {
        continue
    }

    for ($pass = 1; $pass -le 4; $pass++) {

        $beforeScore = Get-MojibakeScore $text

        if ($beforeScore -eq 0) {
            break
        }

        try {

            $bytes = $cp1252.GetBytes($text)

            $candidate = $utf8.GetString($bytes)

            $afterScore = Get-MojibakeScore $candidate

            if ($afterScore -lt $beforeScore) {
                $text = $candidate
            }
            else {
                break
            }

        }
        catch {
            break
        }
    }

    if ($text -eq $original) {
        continue
    }

    $relative = $file.FullName.Substring(
        $root.Length
    ).TrimStart('\')

    $backup = Join-Path $backupRoot $relative

    $backupDirectory = Split-Path $backup -Parent

    New-Item `
        -ItemType Directory `
        -Path $backupDirectory `
        -Force |
        Out-Null

    Copy-Item `
        -LiteralPath $file.FullName `
        -Destination $backup `
        -Force

    [System.IO.File]::WriteAllText(
        $file.FullName,
        $text,
        $utf8
    )

    $changed += $relative
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host " CHESSMATE MOJIBAKE REPAIR" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Files changed: $($changed.Count)" -ForegroundColor Green

foreach ($item in ($changed | Sort-Object)) {
    Write-Host "  FIXED: $item"
}

Write-Host ""
Write-Host "Backup:" -ForegroundColor Yellow
Write-Host $backupRoot

Write-Host ""
Write-Host "Running verification..." -ForegroundColor Cyan

$remaining = @()

foreach ($file in $files) {

    if (-not (Test-Path -LiteralPath $file.FullName)) {
        continue
    }

    $content = [System.IO.File]::ReadAllText(
        $file.FullName,
        $utf8
    )

    if ((Get-MojibakeScore $content) -gt 0) {
        $remaining += $file.FullName
    }
}

Write-Host ""

if ($remaining.Count -eq 0) {

    Write-Host `
        "SUCCESS: No primary mojibake markers remain." `
        -ForegroundColor Green

}
else {

    Write-Host `
        "WARNING: Some files still contain suspicious markers." `
        -ForegroundColor Yellow

    foreach ($file in $remaining) {
        Write-Host "  $file"
    }
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green