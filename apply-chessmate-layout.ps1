$ErrorActionPreference = "Stop"

$htmlPath = ".\index.html"
$cssPath  = ".\css\style.css"

$html = Get-Content $htmlPath -Raw
$css  = Get-Content $cssPath -Raw

# Ensure the expected ChessMate elements exist.
foreach ($id in @("board", "movelist", "magnusCoach")) {
    if ([regex]::Matches($html, "id=`"$id`"").Count -ne 1) {
        throw "Expected exactly one element with id=$id. No changes made."
    }
}

if ($html.Contains("CHESSMATE_PERMANENT_THREE_COLUMN_LAYOUT")) {
    throw "Layout patch already exists."
}

$script = @'
  <script>
  /* CHESSMATE_PERMANENT_THREE_COLUMN_LAYOUT */
  (() => {
    const grid = document.querySelector(".grid");
    const board = document.querySelector(".boardcard");
    const moves = document.querySelector(".movescard");
    const coach = document.querySelector(".coach");
    if (!grid || !board || !moves || !coach) return;
    grid.append(board, moves, coach);
  })();
  </script>
'@

$anchor = '  <script src="js/magnus-coach.js"></script>'
if (-not $html.Contains($anchor)) {
    throw "Script insertion anchor missing. No changes made."
}

$cssPatch = @'

/* CHESSMATE_PERMANENT_THREE_COLUMN_LAYOUT */
@media (min-width: 760px) {
  .grid {
    display: grid !important;
    grid-template-columns: minmax(0,1.4fr) minmax(155px,.72fr) minmax(190px,.9fr) !important;
    align-items: start !important;
    gap: 12px !important;
  }
  .grid > .leftcol, .grid > .rightcol {
    display: contents !important;
  }
  .grid > .boardcard {
    grid-column: 1 !important;
    grid-row: 1 !important;
    width: auto !important;
    min-width: 0 !important;
  }
  .grid > .movescard {
    grid-column: 2 !important;
    grid-row: 1 !important;
    width: auto !important;
    min-width: 0 !important;
    position: sticky;
    top: 10px;
  }
  .grid > .coach {
    grid-column: 3 !important;
    grid-row: 1 !important;
    width: auto !important;
    min-width: 0 !important;
    max-height: 75vh;
    overflow-y: auto;
  }
  .grid > .movescard .movelist {
    max-height: 65vh !important;
    overflow-y: auto !important;
  }
  .grid .review-header-card,
  .grid .review,
  .grid .live,
  .grid .explorer,
  .grid .phases,
  .grid .summary,
  .grid .advice,
  .grid .graphcard,
  .grid .legendcard {
    grid-column: 1 / -1 !important;
    min-width: 0;
  }
}
@media (max-width: 759px) {
  .grid {
    display: grid !important;
    grid-template-columns: minmax(0,1fr) !important;
  }
  .grid > .leftcol, .grid > .rightcol {
    display: contents !important;
  }
  .grid > .boardcard, .grid > .movescard, .grid > .coach {
    grid-column: 1 !important;
    grid-row: auto !important;
    position: static !important;
    max-height: none;
    min-width: 0 !important;
  }
}
/* END CHESSMATE_PERMANENT_THREE_COLUMN_LAYOUT */
'@

# Back up before writing.
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item $htmlPath "$htmlPath.backup-$stamp"
Copy-Item $cssPath "$cssPath.backup-$stamp"

$newHtml = $html.Replace($anchor, $script + "`r`n" + $anchor)

Set-Content $htmlPath $newHtml -Encoding UTF8
Add-Content $cssPath $cssPatch -Encoding UTF8

# Verify the patch was written.
if (-not (Select-String $htmlPath -Pattern "CHESSMATE_PERMANENT_THREE_COLUMN_LAYOUT" -Quiet)) {
    throw "HTML verification failed."
}
if (-not (Select-String $cssPath -Pattern "CHESSMATE_PERMANENT_THREE_COLUMN_LAYOUT" -Quiet)) {
    throw "CSS verification failed."
}

Write-Host "ChessMate layout patch applied. Backups created." -ForegroundColor Green