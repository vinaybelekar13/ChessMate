/* =========================================================
   ChessMate Book Reader - Independent Chess Board
   Inspired by the Barabosik visual language.
   This module does NOT import Barabosik board.js.
   ========================================================= */

const PIECE_BASE = "../vendor/pieces/cburnett/";

const FILES = ["a","b","c","d","e","f","g","h"];

const PIECE_FILES = {
    wP: "wP.svg",
    wN: "wN.svg",
    wB: "wB.svg",
    wR: "wR.svg",
    wQ: "wQ.svg",
    wK: "wK.svg",
    bP: "bP.svg",
    bN: "bN.svg",
    bB: "bB.svg",
    bR: "bR.svg",
    bQ: "bQ.svg",
    bK: "bK.svg"
};

export class BookBoard {

    constructor(element, options = {}) {
        this.element = element;

        this.fen = options.fen ||
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

        this.flip = Boolean(options.flip);
        this.lastMove = options.lastMove || null;

        this.selected = null;
        this.targets = [];

        this.dragging = null;

        this.arrows = [];

        this.onMove = options.onMove || (() => {});
        this.onSelect = options.onSelect || (() => {});
        this.onPositionChange = options.onPositionChange || (() => {});

        this.board = this.createBoard();

        this.render();
    }

    /* -----------------------------------------------------
       PUBLIC API
       ----------------------------------------------------- */

    setPosition(fen) {
        this.fen = fen;
        this.selected = null;
        this.targets = [];
        this.lastMove = null;
        this.render();
        this.onPositionChange(this.fen);
    }

    getPosition() {
        return this.fen;
    }

    setFlip(value) {
        this.flip = Boolean(value);
        this.render();
    }

    toggleFlip() {
        this.flip = !this.flip;
        this.render();
    }

    setLastMove(move) {
        this.lastMove = move || null;
        this.render();
    }

    clearSelection() {
        this.selected = null;
        this.targets = [];
        this.render();
    }

    clearArrows() {
        this.arrows = [];
        this.render();
    }

    reset() {
        this.setPosition(
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        );
    }

    /* -----------------------------------------------------
       BOARD CREATION
       ----------------------------------------------------- */

    createBoard() {

        this.element.innerHTML = "";

        this.element.classList.add("book-board-shell");

        const board = document.createElement("div");

        board.className = "book-board";

        board.addEventListener("contextmenu", event => {
            event.preventDefault();
        });

        board.addEventListener("mousedown", event => {
            this.handleMouseDown(event);
        });

        board.addEventListener("click", event => {
            this.handleClick(event);
        });

        board.addEventListener("dragstart", event => {
            event.preventDefault();
        });

        this.element.appendChild(board);

        return board;
    }

    /* -----------------------------------------------------
       FEN
       ----------------------------------------------------- */

    parseFen(fen) {

        const fields = String(fen).trim().split(/\s+/);

        const placement = fields[0] || "8/8/8/8/8/8/8/8";
        const side = fields[1] || "w";

        const rows = placement.split("/");

        const squares = {};

        for (let rankIndex = 0; rankIndex < 8; rankIndex++) {

            const row = rows[rankIndex] || "8";

            let fileIndex = 0;

            for (const char of row) {

                if (/[1-8]/.test(char)) {

                    fileIndex += Number(char);

                } else {

                    if (fileIndex < 8) {

                        const square =
                            FILES[fileIndex] + (8 - rankIndex);

                        squares[square] = char;
                    }

                    fileIndex++;
                }
            }
        }

        return {
            squares,
            side
        };
    }

    /* -----------------------------------------------------
       RENDER
       ----------------------------------------------------- */

    render() {

        const position = this.parseFen(this.fen);

        this.board.innerHTML = "";

        const displayFiles = this.flip
            ? [...FILES].reverse()
            : FILES;

        const displayRanks = this.flip
            ? [1,2,3,4,5,6,7,8]
            : [8,7,6,5,4,3,2,1];

        for (const rank of displayRanks) {

            for (const file of displayFiles) {

                const squareName = `${file}${rank}`;

                const square = document.createElement("div");

                square.className = "book-square";

                square.dataset.square = squareName;

                const fileIndex = FILES.indexOf(file);

                const dark =
                    (fileIndex + rank) % 2 === 0;

                square.classList.add(
                    dark ? "book-dark" : "book-light"
                );

                if (this.selected === squareName) {
                    square.classList.add("book-selected");
                }

                if (this.targets.includes(squareName)) {
                    square.classList.add("book-target");
                }

                if (this.lastMove) {

                    if (
                        this.lastMove.from === squareName ||
                        this.lastMove.to === squareName
                    ) {
                        square.classList.add("book-last-move");
                    }
                }

                const piece = position.squares[squareName];

                if (piece) {

                    const color =
                        piece === piece.toUpperCase()
                            ? "w"
                            : "b";

                    const type = piece.toUpperCase();

                    const pieceKey = `${color}${type}`;

                    const img = document.createElement("img");

                    img.className = "book-piece";

                    img.draggable = false;

                    img.alt = pieceKey;

                    img.src =
                        PIECE_BASE +
                        PIECE_FILES[pieceKey];

                    img.onerror = () => {
                        img.style.display = "none";
                    };

                    square.appendChild(img);
                }

                if (this.targets.includes(squareName)) {

                    const dot = document.createElement("span");

                    dot.className =
                        position.squares[squareName]
                            ? "book-capture-ring"
                            : "book-move-dot";

                    square.appendChild(dot);
                }

                if (
                    this.selected &&
                    this.targets.includes(squareName)
                ) {

                    square.classList.add("book-legal");
                }

                this.board.appendChild(square);
            }
        }

        this.renderArrows();
    }

    /* -----------------------------------------------------
       CLICK
       ----------------------------------------------------- */

    handleClick(event) {

        const square =
            event.target.closest(".book-square");

        if (!square) return;

        const squareName = square.dataset.square;

        if (!this.selected) {

            this.selectSquare(squareName);

            return;
        }

        if (squareName === this.selected) {

            this.clearSelection();

            return;
        }

        if (this.targets.includes(squareName)) {

            const move = {
                from: this.selected,
                to: squareName
            };

            this.selected = null;
            this.targets = [];

            this.lastMove = move;

            this.render();

            this.onMove(move);

            return;
        }

        this.selectSquare(squareName);
    }

    /* -----------------------------------------------------
       SELECT
       ----------------------------------------------------- */

    selectSquare(square) {

        const position = this.parseFen(this.fen);

        const piece =
            position.squares[square];

        if (!piece) {

            this.selected = null;
            this.targets = [];

            this.render();

            return;
        }

        const pieceSide =
            piece === piece.toUpperCase()
                ? "w"
                : "b";

        if (pieceSide !== position.side) {

            return;
        }

        this.selected = square;

        this.targets =
            this.calculatePseudoLegalTargets(
                square,
                position
            );

        this.onSelect(square);

        this.render();
    }

    /* -----------------------------------------------------
       MOVE GENERATION
       ----------------------------------------------------- */

    calculatePseudoLegalTargets(square, position) {

        const piece = position.squares[square];

        if (!piece) return [];

        const color =
            piece === piece.toUpperCase()
                ? "w"
                : "b";

        const type = piece.toUpperCase();

        const file =
            FILES.indexOf(square[0]);

        const rank =
            Number(square[1]);

        const result = [];

        const add = (df, dr) => {

            const nf = file + df;
            const nr = rank + dr;

            if (
                nf < 0 ||
                nf > 7 ||
                nr < 1 ||
                nr > 8
            ) return;

            const target =
                `${FILES[nf]}${nr}`;

            const targetPiece =
                position.squares[target];

            if (!targetPiece) {

                result.push(target);

                return true;
            }

            const targetColor =
                targetPiece === targetPiece.toUpperCase()
                    ? "w"
                    : "b";

            if (targetColor !== color) {
                result.push(target);
            }

            return false;
        };

        const slide = (df, dr) => {

            let nf = file + df;
            let nr = rank + dr;

            while (
                nf >= 0 &&
                nf < 8 &&
                nr >= 1 &&
                nr <= 8
            ) {

                const target =
                    `${FILES[nf]}${nr}`;

                const targetPiece =
                    position.squares[target];

                if (!targetPiece) {

                    result.push(target);

                } else {

                    const targetColor =
                        targetPiece === targetPiece.toUpperCase()
                            ? "w"
                            : "b";

                    if (targetColor !== color) {
                        result.push(target);
                    }

                    break;
                }

                nf += df;
                nr += dr;
            }
        };

        if (type === "P") {

            const direction =
                color === "w" ? 1 : -1;

            const oneRank =
                rank + direction;

            if (
                oneRank >= 1 &&
                oneRank <= 8
            ) {

                const one =
                    `${FILES[file]}${oneRank}`;

                if (!position.squares[one]) {

                    result.push(one);

                    const startRank =
                        color === "w" ? 2 : 7;

                    const twoRank =
                        rank + direction * 2;

                    const two =
                        `${FILES[file]}${twoRank}`;

                    if (
                        rank === startRank &&
                        !position.squares[two]
                    ) {
                        result.push(two);
                    }
                }

                for (const df of [-1, 1]) {

                    const nf = file + df;

                    if (
                        nf < 0 ||
                        nf > 7
                    ) continue;

                    const capture =
                        `${FILES[nf]}${oneRank}`;

                    const targetPiece =
                        position.squares[capture];

                    if (
                        targetPiece &&
                        (
                            targetPiece ===
                                targetPiece.toUpperCase()
                                ? "w"
                                : "b"
                        ) !== color
                    ) {

                        result.push(capture);
                    }
                }
            }
        }

        if (type === "N") {

            for (const [df, dr] of [
                [1,2],
                [2,1],
                [2,-1],
                [1,-2],
                [-1,-2],
                [-2,-1],
                [-2,1],
                [-1,2]
            ]) {
                add(df, dr);
            }
        }

        if (type === "B") {

            slide(1,1);
            slide(1,-1);
            slide(-1,1);
            slide(-1,-1);
        }

        if (type === "R") {

            slide(1,0);
            slide(-1,0);
            slide(0,1);
            slide(0,-1);
        }

        if (type === "Q") {

            slide(1,1);
            slide(1,-1);
            slide(-1,1);
            slide(-1,-1);

            slide(1,0);
            slide(-1,0);
            slide(0,1);
            slide(0,-1);
        }

        if (type === "K") {

            for (const [df, dr] of [
                [1,1],
                [1,0],
                [1,-1],
                [0,1],
                [0,-1],
                [-1,1],
                [-1,0],
                [-1,-1]
            ]) {
                add(df, dr);
            }
        }

        return result;
    }

    /* -----------------------------------------------------
       DRAG
       ----------------------------------------------------- */

    handleMouseDown(event) {

        const square =
            event.target.closest(".book-square");

        if (!square) return;

        if (event.button === 2) {

            this.handleRightClick(square.dataset.square);

            return;
        }

        if (event.button !== 0) return;

        const squareName =
            square.dataset.square;

        const position =
            this.parseFen(this.fen);

        const piece =
            position.squares[squareName];

        if (!piece) return;

        const pieceSide =
            piece === piece.toUpperCase()
                ? "w"
                : "b";

        if (pieceSide !== position.side) {
            return;
        }

        this.dragging = squareName;

        this.selectSquare(squareName);

        const moveHandler = moveEvent => {

            const target =
                document.elementFromPoint(
                    moveEvent.clientX,
                    moveEvent.clientY
                );

            const targetSquare =
                target?.closest(".book-square");

            this.board
                .querySelectorAll(".book-drag-over")
                .forEach(el =>
                    el.classList.remove("book-drag-over")
                );

            if (targetSquare) {

                targetSquare.classList.add(
                    "book-drag-over"
                );
            }
        };

        const upHandler = upEvent => {

            document.removeEventListener(
                "mousemove",
                moveHandler
            );

            document.removeEventListener(
                "mouseup",
                upHandler
            );

            const target =
                document.elementFromPoint(
                    upEvent.clientX,
                    upEvent.clientY
                );

            const targetSquare =
                target?.closest(".book-square");

            this.board
                .querySelectorAll(".book-drag-over")
                .forEach(el =>
                    el.classList.remove("book-drag-over")
                );

            if (
                targetSquare &&
                this.targets.includes(
                    targetSquare.dataset.square
                )
            ) {

                const move = {
                    from: this.dragging,
                    to: targetSquare.dataset.square
                };

                this.selected = null;
                this.targets = [];
                this.lastMove = move;

                this.render();

                this.onMove(move);

            } else {

                this.render();
            }

            this.dragging = null;
        };

        document.addEventListener(
            "mousemove",
            moveHandler
        );

        document.addEventListener(
            "mouseup",
            upHandler
        );
    }

    /* -----------------------------------------------------
       RIGHT CLICK ARROWS
       ----------------------------------------------------- */

    handleRightClick(square) {

        if (!this.arrowStart) {

            this.arrowStart = square;

            return;
        }

        if (this.arrowStart === square) {

            this.arrowStart = null;

            return;
        }

        const existing =
            this.arrows.find(
                arrow =>
                    arrow.from === this.arrowStart &&
                    arrow.to === square
            );

        if (existing) {

            this.arrows =
                this.arrows.filter(
                    arrow => arrow !== existing
                );

        } else {

            this.arrows.push({
                from: this.arrowStart,
                to: square
            });
        }

        this.arrowStart = null;

        this.render();
    }

    /* -----------------------------------------------------
       ARROWS
       ----------------------------------------------------- */

    renderArrows() {

        if (!this.arrows.length) return;

        const overlay =
            document.createElement("div");

        overlay.className =
            "book-arrow-layer";

        for (const arrow of this.arrows) {

            const from =
                this.board.querySelector(
                    `[data-square="${arrow.from}"]`
                );

            const to =
                this.board.querySelector(
                    `[data-square="${arrow.to}"]`
                );

            if (!from || !to) continue;

            const svg =
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    "svg"
                );

            svg.setAttribute(
                "class",
                "book-arrow-svg"
            );

            const line =
                document.createElementNS(
                    "http://www.w3.org/2000/svg",
                    "line"
                );

            const fromRect =
                from.getBoundingClientRect();

            const toRect =
                to.getBoundingClientRect();

            const boardRect =
                this.board.getBoundingClientRect();

            const x1 =
                fromRect.left -
                boardRect.left +
                fromRect.width / 2;

            const y1 =
                fromRect.top -
                boardRect.top +
                fromRect.height / 2;

            const x2 =
                toRect.left -
                boardRect.left +
                toRect.width / 2;

            const y2 =
                toRect.top -
                boardRect.top +
                toRect.height / 2;

            line.setAttribute("x1", x1);
            line.setAttribute("y1", y1);
            line.setAttribute("x2", x2);
            line.setAttribute("y2", y2);

            line.setAttribute(
                "class",
                "book-arrow"
            );

            svg.setAttribute(
                "viewBox",
                `0 0 ${this.board.clientWidth} ${this.board.clientHeight}`
            );

            svg.appendChild(line);

            overlay.appendChild(svg);
        }

        this.board.appendChild(overlay);
    }
}
