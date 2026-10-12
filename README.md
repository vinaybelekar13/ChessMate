# ChessMate

ChessMate is a browser-based chess project with board interaction, game analysis, puzzle features, book/position reading, and chessboard image recognition.

## Main pages

- `index.html` — main chess interface
- `book-reader.html` — chess book and position reader
- `puzzles.html` — puzzles interface
- `report.html` — game analysis report

## Local development

Use a local HTTP server to serve the project directory. Some browser features, model files, and WebAssembly assets may not work when opening HTML files directly using `file://`.

Check `package.json` for the project's available scripts and dependencies.

## Native scanner

The optional Windows scanner source is located in `native/ChessMateSnipper`. Build it using the .NET SDK and the project file provided there.

## Models and runtime assets

The board-recognition model and runtime assets are stored in `models/`, `public/models/`, `ort/`, and `public/ort/`.
