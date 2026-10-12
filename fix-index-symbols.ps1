
$path = ".\index.html"
$backup = ".\index.html.before-index-symbol-fix"

if (!(Test-Path $backup)) {
    Copy-Item $path $backup
}

$content = [System.IO.File]::ReadAllText(
    (Resolve-Path $path).Path,
    [System.Text.Encoding]::UTF8
)

function U([int[]]$codes) {
    return -join ($codes | ForEach-Object { [char]$_ })
}

# Exact visible text replacements only.
$changes = @(
    @("ChessMate " + (U @(0x00E2,0x20AC,0x201D)) + " analyze",
      "ChessMate " + (U @(0x2014)) + " analyze"),

    @("starting" + (U @(0x00E2,0x20AC,0x00A6)),
      "starting" + (U @(0x2026))),

    @((U @(0x00E2,0x0161,0x00AA)) + " White",
      (U @(0x26AA)) + " White"),

    @((U @(0x00E2,0x0161,0x00AB)) + " Black",
      (U @(0x26AB)) + " Black"),

    @((U @(0x00E2,0x20AC,0x201C)),
      (U @(0x2013))),

    @("8" + (U @(0x00C3,0x2014)) + "8",
      "8" + (U @(0x00D7)) + "8"),

    @((U @(0x00E2,0x20AC,0x201D)),
      (U @(0x2014))),

    @("12 " + (U @(0x00C2,0x00B7)) + " fastest",
      "12 " + (U @(0x00B7)) + " fastest")
)

foreach ($change in $changes) {
    $content = $content.Replace(
        [string]$change[0],
        [string]$change[1]
    )
}

# Repair known navigation button contents by their stable HTML IDs.
$content = [regex]::Replace(
    $content,
    '(?s)(<button id="bStart"[^>]*>).*?(</button>)',
    ('$1' + (U @(0x23EE)) + '$2')
)
$content = [regex]::Replace(
    $content,
    '(?s)(<button id="bPrev"[^>]*>).*?(</button>)',
    ('$1' + (U @(0x25C0)) + '$2')
)
$content = [regex]::Replace(
    $content,
    '(?s)(<button id="bNext"[^>]*>).*?(</button>)',
    ('$1' + (U @(0x25B6)) + '$2')
)
$content = [regex]::Replace(
    $content,
    '(?s)(<button id="bEnd"[^>]*>).*?(</button>)',
    ('$1' + (U @(0x23ED)) + '$2')
)
$content = [regex]::Replace(
    $content,
    '(?s)(<button id="bFlip"[^>]*>).*?(</button>)',
    ('$1' + (U @(0x21C5)) + '$2')
)

[System.IO.File]::WriteAllText(
    (Resolve-Path $path).Path,
    $content,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "index.html text patch complete."
Write-Host "Backup: $backup"
