from pathlib import Path
import sys
import json
import re
import subprocess
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from database.database import SessionLocal
from database.models import (
    Game,
    GameMove,
    Motif,
    TrainingPosition,
    ProfileSnapshot,
)
from coach.service import get_game_coaching, get_move_coaching, get_position_coaching
from typing import Any, Optional
from pydantic import BaseModel
from analysis.move_parser import parse_game_with_clock


app = FastAPI(
    title="ChessMate Report API",
    version="2.0.0",
    description="Local ChessMate chess analytics and report API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


PLAYER = "vinayayayay"
WINDOW = 300


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "chessmate-report-api",
        "version": "2.0.0",
    }


def pct(part, total):
    if not total:
        return 0.0
    return round((part / total) * 100.0, 2)


def average(values):
    values = [float(v) for v in values if v is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def player_color(game):
    white = (game.white or "").strip().lower()
    black = (game.black or "").strip().lower()

    if white == PLAYER:
        return "white"
    if black == PLAYER:
        return "black"
    return None


def player_result(game):
    color = player_color(game)

    if color == "white":
        if game.result == "1-0":
            return "win"
        if game.result == "0-1":
            return "loss"
        return "draw"

    if color == "black":
        if game.result == "0-1":
            return "win"
        if game.result == "1-0":
            return "loss"
        return "draw"

    return "unknown"


def clean_termination(value):
    text = (value or "").strip().lower()

    if "checkmate" in text:
        return "checkmate"
    if "resignation" in text:
        return "resignation"
    if "on time" in text:
        return "time"
    if "abandoned" in text:
        return "abandoned"
    if "repetition" in text:
        return "repetition"
    if "stalemate" in text:
        return "stalemate"
    if "insufficient material" in text:
        return "insufficient_material"
    if "agreement" in text:
        return "agreement"

    return "other"


def build_report(session):
    snapshot = session.scalars(
        select(ProfileSnapshot)
        .order_by(ProfileSnapshot.id.desc())
        .limit(1)
    ).first()

    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail="No profile snapshot available",
        )

    summary = snapshot.summary

    if isinstance(summary, str):
        summary = json.loads(summary)

    games = session.scalars(
        select(Game)
        .order_by(Game.played_at.desc(), Game.id.desc())
        .limit(WINDOW)
    ).all()

    game_ids = [game.id for game in games]

    moves = []

    if game_ids:
        moves = session.scalars(
            select(GameMove)
            .where(GameMove.game_id.in_(game_ids))
            .order_by(GameMove.game_id.asc(), GameMove.ply.asc())
        ).all()

    motifs = []

    if game_ids:
        motifs = session.scalars(
            select(Motif)
            .where(Motif.game_id.in_(game_ids))
        ).all()

    training_positions = []

    if game_ids:
        training_positions = session.scalars(
            select(TrainingPosition)
            .where(TrainingPosition.game_id.in_(game_ids))
        ).all()

    moves_by_game = defaultdict(list)

    for move in moves:
        moves_by_game[move.game_id].append(move)

    motifs_by_game = defaultdict(list)

    for motif in motifs:
        motifs_by_game[motif.game_id].append(motif)

    # ------------------------------------------------------------
    # Overall move classifications
    # ------------------------------------------------------------

    classifications = Counter()
    player_move_cpl = []
    player_move_accuracy = []

    blunders = 0
    mistakes = 0
    inaccuracies = 0
    best_moves = 0

    critical_moves = 0
    time_pressure_moves = 0

    thinking_times = []

    for game in games:
        color = player_color(game)

        if color is None:
            continue

        expected_color = "w" if color == "white" else "b"

        for move in moves_by_game[game.id]:
            if move.color != expected_color:
                continue

            classification = (move.classification or "unknown").lower()
            classifications[classification] += 1

            if classification == "blunder":
                blunders += 1
            elif classification == "mistake":
                mistakes += 1
            elif classification == "inaccuracy":
                inaccuracies += 1
            elif classification == "best":
                best_moves += 1

            if move.is_critical:
                critical_moves += 1

            if (
                move.thinking_time is not None
                and move.thinking_time >= 20
            ):
                time_pressure_moves += 1

            if move.thinking_time is not None:
                thinking_times.append(float(move.thinking_time))

            if (
                move.centipawn_loss is not None
                and float(move.centipawn_loss) < 100000.0
            ):
                player_move_cpl.append(float(move.centipawn_loss))

            if move.accuracy is not None:
                player_move_accuracy.append(float(move.accuracy))

    # ------------------------------------------------------------
    # Phase statistics
    # ------------------------------------------------------------

    phase_data = defaultdict(
        lambda: {
            "moves": 0,
            "cpl": [],
            "accuracy": [],
            "blunders": 0,
            "mistakes": 0,
            "inaccuracies": 0,
        }
    )

    valid_phases = {"opening", "middlegame", "endgame"}

    for game in games:
        color = player_color(game)

        if color is None:
            continue

        expected_color = "w" if color == "white" else "b"

        for move in moves_by_game[game.id]:
            if move.color != expected_color:
                continue

            phase = (move.phase or "unknown").lower()

            if phase not in valid_phases:
                continue

            item = phase_data[phase]
            item["moves"] += 1

            if (
                move.centipawn_loss is not None
                and float(move.centipawn_loss) < 100000.0
            ):
                item["cpl"].append(float(move.centipawn_loss))

            if move.accuracy is not None:
                item["accuracy"].append(float(move.accuracy))

            classification = (move.classification or "").lower()

            if classification == "blunder":
                item["blunders"] += 1
            elif classification == "mistake":
                item["mistakes"] += 1
            elif classification == "inaccuracy":
                item["inaccuracies"] += 1

    phases = {}

    for phase in ["opening", "middlegame", "endgame"]:
        item = phase_data[phase]

        phases[phase] = {
            "moves": item["moves"],
            "average_cpl": average(item["cpl"]),
            "accuracy": average(item["accuracy"]),
            "blunders": item["blunders"],
            "mistakes": item["mistakes"],
            "inaccuracies": item["inaccuracies"],
        }

    # ------------------------------------------------------------
    # Color performance
    # ------------------------------------------------------------

    color_stats = {}

    for color_name in ["white", "black"]:
        color_games = [
            game
            for game in games
            if player_color(game) == color_name
        ]

        wins = sum(
            1 for game in color_games
            if player_result(game) == "win"
        )

        draws = sum(
            1 for game in color_games
            if player_result(game) == "draw"
        )

        losses = sum(
            1 for game in color_games
            if player_result(game) == "loss"
        )

        color_cpl = []
        color_accuracy = []

        for game in color_games:
            expected_color = "w" if color_name == "white" else "b"

            for move in moves_by_game[game.id]:
                if move.color != expected_color:
                    continue

                if (
                    move.centipawn_loss is not None
                    and float(move.centipawn_loss) < 100000.0
                ):
                    color_cpl.append(float(move.centipawn_loss))

                if move.accuracy is not None:
                    color_accuracy.append(float(move.accuracy))

        color_stats[color_name] = {
            "games": len(color_games),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "win_rate": pct(wins, len(color_games)),
            "accuracy": average(color_accuracy),
            "average_cpl": average(color_cpl),
        }

    # ------------------------------------------------------------
    # Time-control performance
    # ------------------------------------------------------------

    time_control_data = defaultdict(
        lambda: {
            "games": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
        }
    )

    for game in games:
        result = player_result(game)
        tc = game.time_control or "unknown"

        item = time_control_data[tc]
        item["games"] += 1

        if result == "win":
            item["wins"] += 1
        elif result == "draw":
            item["draws"] += 1
        elif result == "loss":
            item["losses"] += 1

    time_controls = []

    for tc, item in sorted(
        time_control_data.items(),
        key=lambda x: x[1]["games"],
        reverse=True,
    ):
        time_controls.append({
            "time_control": tc,
            **item,
            "win_rate": pct(item["wins"], item["games"]),
        })

    # ------------------------------------------------------------
    # Opening performance
    # ------------------------------------------------------------

    opening_data = defaultdict(
        lambda: {
            "games": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "eco": None,
        }
    )

    for game in games:
        opening = (game.opening or "Unknown").strip() or "Unknown"
        item = opening_data[opening]

        item["games"] += 1
        item["eco"] = game.eco

        result = player_result(game)

        if result == "win":
            item["wins"] += 1
        elif result == "draw":
            item["draws"] += 1
        elif result == "loss":
            item["losses"] += 1

    openings = []

    for opening, item in sorted(
        opening_data.items(),
        key=lambda x: x[1]["games"],
        reverse=True,
    ):
        openings.append({
            "opening": opening,
            "eco": item["eco"],
            **item,
            "win_rate": pct(item["wins"], item["games"]),
        })

    # ------------------------------------------------------------
    # Terminations
    # ------------------------------------------------------------

    termination_data = Counter()

    for game in games:
        termination_data[clean_termination(game.termination)] += 1

    terminations = [
        {
            "termination": name,
            "games": count,
            "share": pct(count, len(games)),
        }
        for name, count in termination_data.most_common()
    ]

    # ------------------------------------------------------------
    # Motif statistics
    # ------------------------------------------------------------

    motif_data = defaultdict(
        lambda: {
            "count": 0,
            "severity": Counter(),
            "games": set(),
        }
    )

    for motif in motifs:
        name = motif.motif or "unknown"

        motif_data[name]["count"] += 1
        motif_data[name]["games"].add(motif.game_id)

        severity = (motif.severity or "unknown").lower()
        motif_data[name]["severity"][severity] += 1

    motif_stats = []

    for name, item in motif_data.items():
        motif_stats.append({
            "motif": name,
            "count": item["count"],
            "share": pct(item["count"], len(motifs)),
            "games": len(item["games"]),
            "severity": dict(item["severity"]),
        })

    motif_stats.sort(
        key=lambda x: x["count"],
        reverse=True,
    )

    # ------------------------------------------------------------
    # Game summaries
    # ------------------------------------------------------------

    game_summaries = []

    for game in games:
        result = player_result(game)
        color = player_color(game)

        game_moves = [
            move
            for move in moves_by_game[game.id]
            if (
                color == "white"
                and move.color == "w"
            )
            or (
                color == "black"
                and move.color == "b"
            )
        ]

        valid_cpl = [
            float(move.centipawn_loss)
            for move in game_moves
            if (
                move.centipawn_loss is not None
                and float(move.centipawn_loss) < 100000.0
            )
        ]

        accuracies = [
            float(move.accuracy)
            for move in game_moves
            if move.accuracy is not None
        ]

        game_summaries.append({
            "id": game.id,
            "uuid": game.chesscom_uuid,
            "url": game.url,
            "played_at": (
                game.played_at.isoformat()
                if game.played_at
                else None
            ),
            "opponent": (
                game.black
                if color == "white"
                else game.white
            ),
            "color": color,
            "result": result,
            "white": game.white,
            "black": game.black,
            "white_rating": game.white_rating,
            "black_rating": game.black_rating,
            "time_control": game.time_control,
            "eco": game.eco,
            "opening": game.opening,
            "termination": clean_termination(game.termination),
            "accuracy": average(accuracies),
            "average_cpl": average(valid_cpl),
            "blunders": sum(
                1
                for move in game_moves
                if (move.classification or "").lower() == "blunder"
            ),
            "mistakes": sum(
                1
                for move in game_moves
                if (move.classification or "").lower() == "mistake"
            ),
            "inaccuracies": sum(
                1
                for move in game_moves
                if (move.classification or "").lower() == "inaccuracy"
            ),
            "critical_moves": sum(
                1 for move in game_moves
                if move.is_critical
            ),
            "moves": len(game_moves),
        })

    # ------------------------------------------------------------
    # Final response
    # ------------------------------------------------------------

    return {
        "snapshot_id": snapshot.id,
        "generated_at": snapshot.generated_at,
        "profile": summary,
        "statistics": {
            "games": len(games),
            "wins": sum(
                1 for game in games
                if player_result(game) == "win"
            ),
            "draws": sum(
                1 for game in games
                if player_result(game) == "draw"
            ),
            "losses": sum(
                1 for game in games
                if player_result(game) == "loss"
            ),
            "win_rate": pct(
                sum(
                    1 for game in games
                    if player_result(game) == "win"
                ),
                len(games),
            ),
            "accuracy": average(player_move_accuracy),
            "average_cpl": average(player_move_cpl),
            "blunders": blunders,
            "mistakes": mistakes,
            "inaccuracies": inaccuracies,
            "best_moves": best_moves,
            "critical_moves": critical_moves,
            "average_thinking_time": average(thinking_times),
            "time_pressure_moves": time_pressure_moves,
        },
        "phases": phases,
        "colors": color_stats,
        "time_controls": time_controls,
        "openings": openings,
        "classifications": dict(classifications),
        "motifs": motif_stats,
        "terminations": terminations,
        "training": {
            "positions": len(training_positions),
            "solved": sum(
                1
                for position in training_positions
                if position.solved
            ),
            "unsolved": sum(
                1
                for position in training_positions
                if not position.solved
            ),
        },
        "games": game_summaries,
    }



def parse_unparsed_games():
    """
    Parse only games that do not have any GameMove rows yet.

    The PGN -> GameMove conversion remains owned by move_parser.py.
    This helper only orchestrates the existing parser during refresh.
    """
    session = SessionLocal()

    try:
        games = session.scalars(
            select(Game).order_by(
                Game.played_at.asc(),
                Game.id.asc(),
            )
        ).all()

        parsed_games = 0
        parsed_moves = 0

        for game in games:
            existing_move = session.scalar(
                select(GameMove.id)
                .where(GameMove.game_id == game.id)
                .limit(1)
            )

            if existing_move is not None:
                continue

            moves = parse_game_with_clock(game)

            for data in moves:
                session.add(
                    GameMove(
                        game_id=game.id,
                        ply=data["ply"],
                        move_number=data["move_number"],
                        color=data["color"],
                        san=data["san"],
                        uci=data["uci"],
                        fen_before=data["fen_before"],
                        fen_after=data["fen_after"],
                        phase=data["phase"],
                        clock_seconds=data["clock_seconds"],
                        thinking_time=data["thinking_time"],
                    )
                )

            parsed_games += 1
            parsed_moves += len(moves)

        session.commit()

        return {
            "games": parsed_games,
            "moves": parsed_moves,
        }

    finally:
        session.close()


@app.post("/api/report/refresh")
def refresh_report():
    sync_script = ROOT / "sync" / "chesscom.py"
    batch_script = ROOT / "analysis" / "batch_analyzer.py"
    profile_script = ROOT / "profile" / "profile_engine.py"

    try:
        sync_result = subprocess.run(
            [sys.executable, str(sync_script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )

        if sync_result.returncode != 0:
            raise RuntimeError(
                "Chess.com sync failed: "
                + (sync_result.stderr or sync_result.stdout)[-1200:]
            )

        sync_output = sync_result.stdout or ""

        parser_result = parse_unparsed_games()
        parsed_games = parser_result["games"]
        parsed_moves = parser_result["moves"]

        imported_match = re.search(
            r"Imported:\s*(\d+)",
            sync_output,
        )

        imported = (
            int(imported_match.group(1))
            if imported_match
            else 0
        )

        batch_result = subprocess.run(
            [sys.executable, str(batch_script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=1800,
        )

        if batch_result.returncode != 0:
            raise RuntimeError(
                "Game analysis failed: "
                + (batch_result.stderr or batch_result.stdout)[-1200:]
            )

        batch_output = batch_result.stdout or ""

        completed_match = re.search(
            r"Completed:\s*(\d+)",
            batch_output,
        )

        analyzed = (
            int(completed_match.group(1))
            if completed_match
            else 0
        )

        profile_result = subprocess.run(
            [sys.executable, str(profile_script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )

        if profile_result.returncode != 0:
            raise RuntimeError(
                "Profile rebuild failed: "
                + (profile_result.stderr or profile_result.stdout)[-1200:]
            )

        return {
            "status": "ok",
            "imported": imported,
            "parsed_games": parsed_games,
            "parsed_moves": parsed_moves,
            "analyzed": analyzed,
            "message": (
                f"Refresh complete: {imported} new games imported, "
                f"{parsed_games} games parsed, "
                f"{analyzed} games analyzed."
            ),
        }

    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail=f"Refresh timed out: {exc}",
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        )


@app.get("/api/report")
def report():
    session = SessionLocal()

    try:
        return build_report(session)
    finally:
        session.close()



@app.get("/api/report/games/{game_id}")
def report_game(game_id: int):
    """
    Return the complete PGN for a report game so ChessMate can
    open the original game and navigate to a specific ply.
    """
    session = SessionLocal()

    try:
        game = session.scalar(
            select(Game).where(Game.id == game_id)
        )

        if game is None:
            raise HTTPException(
                status_code=404,
                detail="Game not found",
            )

        return {
            "id": game.id,
            "pgn": game.pgn,
            "white": game.white,
            "black": game.black,
            "result": game.result,
            "url": game.url,
            "chesscom_uuid": game.chesscom_uuid,
        }

    finally:
        session.close()

@app.get("/api/report/motifs")
def motif_positions(
    motif: str,
    limit: int = 80,
    offset: int = 0,
):
    """
    Return concrete game positions for a recurring motif.

    Each event is connected:
        Motif -> GameMove -> FEN -> Game
    so the frontend can open the exact position in ChessMate.
    """

    session = SessionLocal()

    try:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))

        motif_key = str(motif or "").strip().lower()

        if not motif_key:
            raise HTTPException(
                status_code=400,
                detail="Motif is required",
            )

        games = session.scalars(
            select(Game).where(
                (Game.white.ilike(PLAYER))
                | (Game.black.ilike(PLAYER))
            )
        ).all()

        game_ids = [game.id for game in games]

        if not game_ids:
            return {
                "motif": motif_key,
                "total": 0,
                "offset": offset,
                "limit": limit,
                "events": [],
            }

        total = session.scalar(
            select(__import__("sqlalchemy").func.count(Motif.id))
            .where(
                Motif.game_id.in_(game_ids),
                Motif.motif == motif_key,
            )
        ) or 0

        motifs = session.scalars(
            select(Motif)
            .where(
                Motif.game_id.in_(game_ids),
                Motif.motif == motif_key,
            )
            .order_by(Motif.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()

        move_ids = [
            item.move_id
            for item in motifs
            if item.move_id is not None
        ]

        moves = {}

        if move_ids:
            move_rows = session.scalars(
                select(GameMove)
                .where(GameMove.id.in_(move_ids))
            ).all()

            moves = {
                move.id: move
                for move in move_rows
            }

        games_by_id = {
            game.id: game
            for game in games
        }

        events = []

        for item in motifs:
            move = moves.get(item.move_id)
            game = games_by_id.get(item.game_id)

            if move is None or game is None:
                continue

            events.append({
                "motif": item.motif,
                "description": item.description,
                "severity": item.severity,

                "game_id": game.id,
                "game_uuid": game.chesscom_uuid,

                "white": game.white,
                "black": game.black,
                "result": game.result,
                "played_at": (
                    game.played_at.isoformat()
                    if game.played_at
                    else None
                ),
                "opening": game.opening,
                "eco": game.eco,
                "time_control": game.time_control,
                "game_url": game.url,

                "move_id": move.id,
                "ply": move.ply,
                "move_number": move.move_number,
                "color": move.color,
                "san": move.san,

                "fen_before": move.fen_before,
                "fen_after": move.fen_after,

                "phase": move.phase,
                "classification": move.classification,
                "accuracy": move.accuracy,
                "centipawn_loss": move.centipawn_loss,
                "best_move": move.best_move,
                "best_pv": move.best_pv,
            })

        return {
            "motif": motif_key,
            "total": int(total),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(motifs) < int(total),
            "events": events,
        }

    finally:
        session.close()



# ---------------------------------------------------------------------------
# Coach API
# ---------------------------------------------------------------------------

@app.get("/api/coach/games/{game_id}")
def coach_game(game_id: int):
    result = get_game_coaching(game_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Game not found")

    return result


@app.get("/api/coach/moves/{move_id}")
def coach_move(move_id: int):
    result = get_move_coaching(move_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Move not found")

    return result


class PositionCoachingRequest(BaseModel):
    fen: str
    move: Optional[str] = None


@app.get("/api/coach/position")
def coach_position_get(fen: str, move: Optional[str] = None):
    if not fen or not fen.strip():
        raise HTTPException(status_code=400, detail="FEN parameter is required")
    result = get_position_coaching(fen=fen, move_uci=move)
    if not result.get("is_valid", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid FEN position"))
    return result


@app.post("/api/coach/position")
def coach_position_post(req: PositionCoachingRequest):
    if not req.fen or not req.fen.strip():
        raise HTTPException(status_code=400, detail="FEN parameter is required")
    result = get_position_coaching(fen=req.fen, move_uci=req.move)
    if not result.get("is_valid", False):
        raise HTTPException(status_code=400, detail=result.get("error", "Invalid FEN position"))
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.report_api:app",
        host="127.0.0.1",
        port=8787,
        reload=False,
    )
