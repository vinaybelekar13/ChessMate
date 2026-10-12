$files = @(
  @{Path=".\js\app.js"; Start=2400; End=2535},
  @{Path=".\js\board.js"; Start=1; End=240},
  @{Path=".\tests\drag.test.mjs"; Start=1; End=160}
)
foreach ($f in $files) {
  "`r`n========== $($f.Path):$($f.Start)-$($f.End) =========="
  $content = Get-Content $f.Path
  for ($i = $f.Start; $i -le [Math]::Min($f.End, $content.Length); $i++) {
    "{0,5}: {1}" -f $i, $content[$i-1]
  }
} | Out-File -Encoding utf8 .\drag_handler_review.txt
notepad .\drag_handler_review.txt
