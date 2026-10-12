
$path = (Resolve-Path ".\index.html").Path
$backup = ".\index.html.before-index-symbol-v3"

if (!(Test-Path $backup)) {
    Copy-Item $path $backup
}

$utf8 = [System.Text.UTF8Encoding]::new($false)
$html = [System.IO.File]::ReadAllText($path, $utf8)

# Replace complete elements using stable IDs, regardless of corrupted text.
$replacements = @(
    @{
        Pattern = '(?s)<span class="statuschip" id="engineStatus">.*?</span>'
        Value   = '<span class="statuschip" id="engineStatus">starting&#x2026;</span>'
    },
    @{
        Pattern = '(?s)<button class="pick on" id="pickWhite">.*?</button>'
        Value   = '<button class="pick on" id="pickWhite">&#x26AA; White</button>'
    },
    @{
        Pattern = '(?s)<button class="pick" id="pickBlack">.*?</button>'
        Value   = '<button class="pick" id="pickBlack">&#x26AB; Black</button>'
    },
    @{
        Pattern = '(?s)<button id="edFlip" class="mini">.*?</button>'
        Value   = '<button id="edFlip" class="mini">&#x21C5; Flip</button>'
    },
    @{
        Pattern = '(?s)<button id="bStart" title="Start \(Home\)">.*?</button>'
        Value   = '<button id="bStart" title="Start (Home)">&#x23EE;</button>'
    },
    @{
        Pattern = '(?s)<button id="bPrev"[^>]*>.*?</button>'
        Value   = '<button id="bPrev" title="Previous arrow key">&#x25C0;</button>'
    },
    @{
        Pattern = '(?s)<button id="bNext"[^>]*>.*?</button>'
        Value   = '<button id="bNext" title="Next arrow key">&#x25B6;</button>'
    },
    @{
        Pattern = '(?s)<button id="bEnd"[^>]*>.*?</button>'
        Value   = '<button id="bEnd" title="End (End)">&#x23ED;</button>'
    },
    @{
        Pattern = '(?s)<button id="bFlip"[^>]*>.*?</button>'
        Value   = '<button id="bFlip" title="Flip board (f)">&#x21C5;</button>'
    }
)

foreach ($item in $replacements) {
    $updated = [regex]::Replace($html, $item.Pattern, $item.Value)

    if ($updated -eq $html) {
        Write-Warning "No match for: $($item.Pattern)"
    }

    $html = $updated
}

# Replace only the corrupted display text in the screenshot hint.
$html = [regex]::Replace(
    $html,
    '(?s)(<div class="scanhint">).*?(</div>)',
    '$1Crop the screenshot to <b>just the 8&#xD7;8 board</b> (no app window or coordinates) &#x2014; a Lichess/Chess.com board reads best. It is read automatically, then you confirm and fix it on an editable board.$2'
)

# Repair the visible scan button label without changing its input.
$html = [regex]::Replace(
    $html,
    '(?s)(<label class="filebtn">).*?(<input type="file" id="scanFile"[^>]*/>.*?</label>)',
    '$1&#x1F4F7; Scan a screenshot$2'
)



[System.IO.File]::WriteAllText($path, $html, $utf8)
Write-Host "Targeted HTML symbol repair complete."
Write-Host "Backup: $backup"
