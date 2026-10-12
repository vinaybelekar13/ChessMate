$files = @(".\index.html", ".\js\app.js", ".\js\puzzles.js", ".\js\book-reader.js")
$utf8 = [System.Text.UTF8Encoding]::new($false)
$replacements = @(
    @([string]([char]0x00C3) + [char]0x00A2 + [char]0x00E2 + [char]0x20AC + [char]0x201C, [string][char]0x2014),
    @([string][char]0x00E2 + [char]0x20AC + [char]0x201C, [string][char]0x2014),
    @([string][char]0x00E2 + [char]0x20AC + [char]0x2013, [string][char]0x2013),
    @([string][char]0x00E2 + [char]0x20AC + [char]0x00A6, [string][char]0x2026),
    @([string][char]0x00C2 + [char]0x00B7, [string][char]0x00B7),
    @("8" + [char]0x00C3 + [char]0x2014 + "8", "8" + [char]0x00D7 + "8"),
    @([string][char]0x00C2 + [char]0x00BD, [string][char]0x00BD),
    @([string][char]0x00E2 + [char]0x2030 + [char]0x2248, [string][char]0x2248)
)
foreach ($file in $files) {
    if (!(Test-Path -LiteralPath $file)) { Write-Host "Missing: $file"; continue }
    $path = (Resolve-Path -LiteralPath $file).Path
    $original = [IO.File]::ReadAllText($path)
    $content = $original
    foreach ($pair in $replacements) { $content = $content.Replace([string]$pair[0], [string]$pair[1]) }
    if ($content -ne $original) {
        $backup = "$path.before-symbol-repair"
        if (!(Test-Path -LiteralPath $backup)) { Copy-Item -LiteralPath $path -Destination $backup }
        [IO.File]::WriteAllText($path, $content, $utf8)
        Write-Host "Repaired: $file" -ForegroundColor Green
    } else { Write-Host "No changes: $file" }
}
Write-Host "Finished."
