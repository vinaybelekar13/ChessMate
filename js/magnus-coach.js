(function (global) {
    "use strict";

    const DEFAULT_API_BASE = "http://127.0.0.1:8787";
    let apiBase = DEFAULT_API_BASE;

    function normalizeBaseUrl(value) {
        const base = String(value || DEFAULT_API_BASE).trim().replace(/\/+$/, "");

        if (!/^https?:\/\//i.test(base)) {
            throw new Error("Magnus Coach API URL must begin with http:// or https://.");
        }

        return base;
    }

    async function request(path) {
        let response;

        try {
            response = await fetch(`${apiBase}${path}`, {
                method: "GET",
                headers: { "Accept": "application/json" }
            });
        } catch (error) {
            throw new Error(
                `Magnus Coach API is unreachable at ${apiBase}. ` +
                "Check that the report API is running. " +
                `Details: ${error.message}`
            );
        }

        if (!response.ok) {
            const body = await response.text().catch(() => "");
            throw new Error(
                `Magnus Coach API returned HTTP ${response.status}` +
                (body ? `: ${body.slice(0, 300)}` : "")
            );
        }

        return response.json();
    }

    function requireId(value, name) {
        const id = String(value ?? "").trim();

        if (!id || !/^[a-zA-Z0-9_-]+$/.test(id)) {
            throw new Error(`A valid ${name} is required.`);
        }

        return encodeURIComponent(id);
    }

    async function getGame(gameId) {
        const id = requireId(gameId, "game ID");
        return request(`/api/coach/games/${id}`);
    }

    async function getMove(moveId) {
        const id = requireId(moveId, "move ID");
        return request(`/api/coach/moves/${id}`);
    }

    async function getMoveAtPly(gameId, ply) {
        const number = Number(ply);

        if (!Number.isInteger(number) || number < 1) {
            throw new Error("Ply must be a positive integer.");
        }

        const game = await getGame(gameId);
        const moves = Array.isArray(game.moves) ? game.moves : [];

        const move = moves.find(
            item => Number(item?.context?.ply) === number
        );

        if (!move) {
            throw new Error(
                `Move at ply ${number} was not found in game ${gameId}.`
            );
        }

        return move;
    }

    async function getExplanationAtPly(gameId, ply) {
        const move = await getMoveAtPly(gameId, ply);

        return {
            gameId,
            ply: Number(ply),
            context: move.context ?? null,
            classification: move.classification ?? null,
            reasoning: move.reasoning ?? null,
            explanation: move.explanation ?? null,
            consequence: move.consequence ?? null,
            motifs: move.motifs ?? [],
            similarMistakes: move.similar_mistakes ?? []
        };
    }

    async function getPosition(fen, move = null) {
        if (!fen || typeof fen !== "string") {
            throw new Error("A valid FEN string is required.");
        }
        let path = `/api/coach/position?fen=${encodeURIComponent(fen.trim())}`;
        if (move) {
            path += `&move=${encodeURIComponent(String(move).trim())}`;
        }
        return request(path);
    }

    async function health() {
        return request("/api/health");
    }

    function configure(options) {
        if (options?.apiBase) {
            apiBase = normalizeBaseUrl(options.apiBase);
        }

        return { apiBase };
    }

    global.ChessMateMagnusAPI = Object.freeze({
        configure,
        health,
        getGame,
        getMove,
        getMoveAtPly,
        getExplanationAtPly,
        getPosition,
        getApiBase: () => apiBase
    });
})(window);
