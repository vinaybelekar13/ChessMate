$files = @(".\index.html", ".\js\app.js", ".\js\puzzles.js", ".\js\book-reader.js")
foreach ($file in $files) {
    Write-Host "`n--- $file ---"
    Select-String -Path $file -Pattern '?|?|?|??' |
        Select-Object -First 8 LineNumber, Line
}
