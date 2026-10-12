const API_URL = "http://127.0.0.1:8787/api/report";

const $ = (id) => document.getElementById(id);

function number(value, digits = 0) {
    return Number(value || 0).toFixed(digits);
}

function esc(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function resultClass(result) {
    if (result === "win") return "result-win";
    if (result === "loss") return "result-loss";
    return "result-draw";
}

function titleCase(value) {
    return String(value || "")
        .replaceAll("_", " ")
        .replace(/\b\w/g, (c) => c.toUpperCase());
}

function showStatus(message) {
    const el = $("report-status");
    el.textContent = message;
    el.classList.add("show");

    clearTimeout(showStatus.timer);
    showStatus.timer = setTimeout(() => {
        el.classList.remove("show");
    }, 2500);
}

function renderHeadline(data) {
    const s = data.statistics;

    $("stat-accuracy").textContent = `${number(s.accuracy, 2)}%`;
    $("stat-cpl").textContent = number(s.average_cpl, 2);
    $("stat-wins").textContent = s.wins;
    $("stat-losses").textContent = s.losses;
    $("stat-win-rate").textContent = `${number(s.win_rate, 2)}% win rate`;
    $("stat-draws").textContent = `${s.draws} draws`;

    $("snapshot-id").textContent = `#${data.snapshot_id}`;
    $("report-subtitle").textContent =
        `${s.games} games / rolling performance profile`;
}

function renderPhases(data) {
    const phases = data.phases;
    const order = ["opening", "middlegame", "endgame"];

    $("phase-list").innerHTML = order.map((name) => {
        const p = phases[name] || {};
        return `
            <div class="phase-row">
                <span class="phase-name">${titleCase(name)}</span>
                <div class="bar">
                    <i style="width:${Math.max(0, Math.min(100, p.accuracy || 0))}%"></i>
                </div>
                <span class="metric-right">
                    ${number(p.accuracy, 1)}%
                    <small>accuracy</small>
                </span>
                <span class="metric-right">
                    ${number(p.average_cpl, 1)}
                    <small>CPL</small>
                </span>
            </div>
        `;
    }).join("");
}

function renderColors(data) {
    $("color-list").innerHTML =
        ["white", "black"].map((color) => {
            const c = data.colors[color] || {};
            return `
                <div class="color-card">
                    <h4>${color}</h4>
                    <strong>${number(c.win_rate, 1)}%</strong>
                    <p>
                        ${c.games} games /
                        ${c.wins}W ${c.draws}D ${c.losses}L
                        ? ${number(c.accuracy, 1)}% accuracy
                    </p>
                </div>
            `;
        }).join("");
}

function renderClassifications(data) {
    const order = [
        "best",
        "excellent",
        "good",
        "inaccuracy",
        "mistake",
        "blunder",
    ];

    const values = order.map((key) => data.classifications[key] || 0);
    const max = Math.max(...values, 1);

    $("classification-list").innerHTML = order.map((key) => {
        const value = data.classifications[key] || 0;

        return `
            <div class="classification-row">
                <span>${titleCase(key)}</span>
                <div class="bar">
                    <i style="width:${(value / max) * 100}%"></i>
                </div>
                <strong>${value}</strong>
            </div>
        `;
    }).join("");
}

function renderMotifs(data) {
    const motifs = data.motifs || [];

    $("motif-total").textContent =
        `${motifs.reduce((sum, item) => sum + item.count, 0)} events`;

    $("motif-list").innerHTML = motifs.slice(0, 10).map((item) => {
        const severity = item.severity || {};
        const count = item.count || 0;
        const max = motifs[0]?.count || 1;

        const motifKey = String(item.motif || "")
            .toLowerCase()
            .replaceAll(" ", "_");

        return `
            <button
                class="motif-row motif-row-clickable"
                type="button"
                data-motif="${esc(motifKey)}"
                title="View the actual positions where this happened"
            >
                <span class="motif-name">
                    ${titleCase(item.motif)}
                </span>

                <div class="bar">
                    <i style="width:${(count / max) * 100}%"></i>
                </div>

                <span class="motif-count">
                    ${count}
                    <small>
                        ${severity.blunder || 0} blunders
                    </small>
                </span>

                <span class="motif-share">
                    ${number(item.share, 1)}%
                </span>

                <span class="motif-open">
                    VIEW POSITIONS
                </span>
            </button>
        `;
    }).join("");
}

function openMotifPositions(motif) {
    const modalId = "motif-position-modal";

    let modal = $(modalId);

    if (!modal) {
        modal = document.createElement("div");
        modal.id = modalId;
        modal.className = "motif-position-modal";

        modal.innerHTML = `
            <div class="motif-modal-backdrop" data-motif-close></div>

            <section
                class="motif-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="motif-modal-title"
            >
                <div class="motif-modal-header">
                    <div>
                        <span class="section-label">
                            WEAKNESS EXAMPLES
                        </span>

                        <h2 id="motif-modal-title">
                            Motif positions
                        </h2>

                        <p id="motif-modal-summary">
                            Loading positions...
                        </p>
                    </div>

                    <button
                        class="motif-modal-close"
                        type="button"
                        data-motif-close
                        aria-label="Close"
                    >
                        ×
                    </button>
                </div>

                <div
                    class="motif-position-list"
                    id="motif-position-list"
                ></div>

                <div
                    class="motif-position-footer"
                    id="motif-position-footer"
                ></div>
            </section>
        `;

        document.body.appendChild(modal);

        modal.addEventListener("click", (event) => {
            const close = event.target.closest("[data-motif-close]");

            if (close) {
                closeMotifPositions();
                return;
            }

            const positionButton =
                event.target.closest("[data-position-fen]");

            if (!positionButton) return;

            const gameId =
                Number(positionButton.dataset.gameId);

            const ply =
                Number(positionButton.dataset.ply);

            if (!Number.isInteger(gameId) || gameId <= 0) return;
            if (!Number.isFinite(ply)) return;

            const url =
                `index.html#game=${encodeURIComponent(gameId)}&ply=${encodeURIComponent(ply)}`;

            window.location.href = url;
        });
    }

    modal.dataset.motif = motif;
    modal.dataset.offset = "0";

    modal.classList.add("open");

    loadMotifPositions(motif, 0, false);
}

async function loadMotifPositions(
    motif,
    offset = 0,
    append = false
) {
    const list = $("motif-position-list");
    const footer = $("motif-position-footer");
    const summary = $("motif-modal-summary");

    if (!list || !footer || !summary) return;

    if (!append) {
        list.innerHTML = `
            <div class="motif-loading">
                <div class="motif-spinner"></div>
                <span>Finding your positions...</span>
            </div>
        `;
    }

    try {
        const response = await fetch(
            `${API_URL.replace(
                "/api/report",
                "/api/report/motifs"
            )}?motif=${encodeURIComponent(motif)}&limit=80&offset=${offset}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        summary.textContent =
            `${number(data.total)} recorded positions ` +
            `for ${titleCase(motif)}. ` +
            `Select any position to open it directly in ChessMate.`;

        const html = (data.events || []).map((event) => {
            const date = event.played_at
                ? new Date(
                    event.played_at
                ).toLocaleDateString()
                : "Unknown date";

            const playerColor =
                event.color === "w"
                    ? "White"
                    : "Black";

            const classification =
                event.classification
                    ? titleCase(event.classification)
                    : "Motif";

            const severity =
                event.severity
                    ? titleCase(event.severity)
                    : classification;

            const opponent =
                event.color === "w"
                    ? event.black
                    : event.white;

            return `
                <button
                    type="button"
                    class="motif-position-card"
                    data-game-id="${esc(event.game_id)}"
                    data-ply="${esc(event.ply)}"
                    data-position-fen="${esc(
                        event.fen_before
                    )}"
                >
                    <div class="motif-position-main">

                        <div class="motif-position-top">
                            <strong>
                                ${esc(
                                    event.white || "White"
                                )}
                                <span>vs</span>
                                ${esc(
                                    event.black || "Black"
                                )}
                            </strong>

                            <span class="
                                motif-position-result
                                ${event.result === "1-0"
                                    ? "win"
                                    : event.result === "0-1"
                                        ? "loss"
                                        : "draw"}
                            ">
                                ${esc(
                                    event.result || "--"
                                )}
                            </span>
                        </div>

                        <div class="motif-position-meta">
                            ${esc(date)}
                            ·
                            ${playerColor}
                            ·
                            Move ${event.move_number}
                            ·
                            ${esc(event.san || "--")}
                        </div>

                        <div class="motif-position-tags">
                            <span class="
                                motif-tag
                                ${String(
                                    event.classification || ""
                                ).toLowerCase()}
                            ">
                                ${esc(classification)}
                            </span>

                            <span class="motif-tag">
                                ${esc(severity)}
                            </span>

                            ${
                                event.phase
                                    ? `
                                        <span class="motif-tag">
                                            ${esc(
                                                titleCase(
                                                    event.phase
                                                )
                                            )}
                                        </span>
                                    `
                                    : ""
                            }
                        </div>
                    </div>

                    <div class="motif-position-action">
                        <span>VIEW BOARD</span>
                        <strong>→</strong>
                    </div>
                </button>
            `;
        }).join("");

        if (!append) {
            list.innerHTML = "";
        }

        list.insertAdjacentHTML("beforeend", html);

        const loaded =
            offset + (data.events || []).length;

        footer.innerHTML = `
            <div class="motif-loaded">
                Showing
                <strong>${loaded}</strong>
                of
                <strong>${data.total}</strong>
            </div>

            <div class="motif-footer-actions">
                ${
                    data.has_more
                        ? `
                            <button
                                type="button"
                                class="motif-load-more"
                                data-motif-more
                            >
                                LOAD MORE
                            </button>
                        `
                        : `
                            <span class="motif-all-loaded">
                                ALL POSITIONS LOADED
                            </span>
                        `
                }
            </div>
        `;

        const modal = $("motif-position-modal");

        if (modal) {
            modal.dataset.offset = String(loaded);
        }

    } catch (error) {

        console.error(
            "ChessMate motif position error:",
            error
        );

        if (!append) {
            list.innerHTML = `
                <div class="motif-error">
                    <strong>
                        Could not load positions
                    </strong>

                    <span>
                        Make sure the ChessMate Report API
                        is running on port 8787.
                    </span>
                </div>
            `;
        }
    }
}

function closeMotifPositions() {
    const modal = $("motif-position-modal");

    if (!modal) return;

    modal.classList.remove("open");
}

document.addEventListener("click", (event) => {

    const motifRow =
        event.target.closest(
            ".motif-row-clickable"
        );

    if (
        motifRow &&
        motifRow.dataset.motif
    ) {
        openMotifPositions(
            motifRow.dataset.motif
        );

        return;
    }

    const moreButton =
        event.target.closest(
            "[data-motif-more]"
        );

    if (moreButton) {
        const modal =
            $("motif-position-modal");

        if (!modal) return;

        const motif =
            modal.dataset.motif;

        const offset =
            Number(
                modal.dataset.offset || 0
            );

        loadMotifPositions(
            motif,
            offset,
            true
        );
    }
});

document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;

    closeMotifPositions();
});

function renderOpenings(data) {
    const openings = data.openings || [];

    $("opening-list").innerHTML = openings.slice(0, 8).map((item) => {
        const name = String(item.opening || "Unknown")
            .replace(/^https?:\/\/www\.chess\.com\/openings\//, "")
            .replaceAll("-", " ");

        return `
            <div class="rank-row">
                <div class="rank-main">
                    <strong>${esc(titleCase(name))}</strong>
                    <small>${esc(item.eco || "Unknown")} / ${item.games} games</small>
                </div>
                <div class="rank-value">
                    ${number(item.win_rate, 1)}%
                    <small>${item.wins}W ${item.losses}L</small>
                </div>
            </div>
        `;
    }).join("");
}

function renderTimeControls(data) {
    $("time-control-list").innerHTML =
        (data.time_controls || []).slice(0, 8).map((item) => `
            <div class="rank-row">
                <div class="rank-main">
                    <strong>${esc(item.time_control)}</strong>
                    <small>${item.games} games</small>
                </div>
                <div class="rank-value">
                    ${number(item.win_rate, 1)}%
                    <small>${item.wins}W ${item.losses}L</small>
                </div>
            </div>
        `).join("");
}

function renderTerminations(data) {
    $("termination-list").innerHTML =
        (data.terminations || []).map((item) => `
            <div class="termination-row">
                <div class="termination-main">
                    <strong>${titleCase(item.termination)}</strong>
                </div>
                <div class="termination-value">
                    ${item.games}
                    <small>${number(item.share, 1)}%</small>
                </div>
            </div>
        `).join("");
}

function renderTraining(data) {
    const t = data.training || {};

    $("training-card").innerHTML = `
        <div class="training-number">
            <strong>${t.positions || 0}</strong>
            <span>positions generated</span>
        </div>
        <div class="training-status">
            ${t.solved || 0} solved<br>
            ${t.unsolved || 0} unsolved
        </div>
    `;
}

function renderGames(data) {
    const body = $("game-table-body");

    body.innerHTML = (data.games || []).slice(0, 50).map((game) => {
        const date = game.played_at
            ? new Date(game.played_at).toLocaleDateString()
            : "--";

        return `
            <tr class="game-row-clickable" data-game-id="${esc(game.id)}" style="cursor: pointer;" title="Open in ChessMate with Magnus Coach">
                <td>${esc(date)}</td>
                <td>${esc(game.opponent || "--")}</td>
                <td>${esc(game.color || "--")}</td>
                <td class="${resultClass(game.result)}">
                    ${esc(game.result || "--")}
                </td>
                <td>${esc(game.eco || "--")}</td>
                <td>${number(game.accuracy, 1)}%</td>
                <td>${number(game.average_cpl, 1)}</td>
                <td>${game.blunders || 0}</td>
            </tr>
        `;
    }).join("");
}

if ($("game-table-body")) {
    $("game-table-body").addEventListener("click", (event) => {
        const row = event.target.closest(".game-row-clickable");
        if (!row) return;
        const gameId = Number(row.dataset.gameId);
        if (Number.isInteger(gameId) && gameId > 0) {
            window.location.href = `index.html#game=${encodeURIComponent(gameId)}`;
        }
    });
}

function renderSummary(data) {
    const profile = data.profile || {};
    const motifSummary = profile.motif_summary || {};

    const strongest = profile.strongest_phase || "opening";
    const weakest = profile.weakest_phase || "endgame";
    const weakness = motifSummary.biggest_weakness || profile.weakest_motif;

    $("profile-summary").textContent =
        `${data.statistics.games} games analyzed. ` +
        `Strongest phase: ${titleCase(strongest)}. ` +
        `Weakest phase: ${titleCase(weakest)}. ` +
        `Primary recurring weakness: ${titleCase(weakness || "not available")}.`;
}

async function loadReport() {
    const button = $("refresh-report");
    const icon = $("refresh-icon");

    button.classList.add("busy");
    icon.textContent = "R";

    try {
        const response = await fetch(`${API_URL}?t=${Date.now()}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        renderHeadline(data);
        renderSummary(data);
        renderPhases(data);
        renderColors(data);
        renderClassifications(data);
        renderMotifs(data);
        renderOpenings(data);
        renderTimeControls(data);
        renderTerminations(data);
        renderTraining(data);
        renderGames(data);

        showStatus("Report updated");
    } catch (error) {
        console.error("ChessMate report error:", error);
        showStatus("Could not load Report API");
    } finally {
        button.classList.remove("busy");
        icon.textContent = "R";
    }
}

async function refreshGames() {
    const button = $("refresh-report");
    const icon = $("refresh-icon");
    const label = button.querySelector("span:last-child");

    button.classList.add("busy");
    icon.textContent = "...";

    if (label) {
        label.textContent = "Syncing Games...";
    }

    showStatus("Checking Chess.com for new games...");

    try {
        const response = await fetch(
            "http://127.0.0.1:8787/api/report/refresh",
            {
                method: "POST"
            }
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.detail || `HTTP ${response.status}`);
        }

        showStatus(
            result.message || "Games synchronized successfully"
        );

        await loadReport();

    } catch (error) {
        console.error("ChessMate game refresh error:", error);
        showStatus(`Refresh failed: ${error.message}`);
    } finally {
        button.classList.remove("busy");
        icon.textContent = "R";

        if (label) {
            label.textContent = "Refresh Games";
        }
    }
}

$("refresh-report").addEventListener("click", refreshGames);

loadReport();


