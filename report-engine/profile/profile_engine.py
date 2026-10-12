from pathlib import Path
import sys
import json
import math
from collections import Counter, defaultdict
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from database.database import SessionLocal
from database.models import Game, GameMove, Motif, ProfileSnapshot


PLAYER = "vinayayayay"
WINDOW = 300


def safe_avg(values):
    values = [float(v) for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else 0.0


def pct(part, total):
    return round((part / total) * 100.0, 2) if total else 0.0


def classify_time_control(value):
    if not value:
        return "unknown"

    value = str(value).strip()

    try:
        base = value.split("+", 1)[0]
        seconds = float(base)

        if seconds < 180:
            return "bullet"
        if seconds < 600:
            return "blitz"
        if seconds < 1800:
            return "rapid"
        return "classical"
    except (ValueError, TypeError):
        return "unknown"


def parse_base_time(value):
    if not value:
        return 0.0

    try:
        return float(str(value).split("+", 1)[0])
    except (ValueError, TypeError):
        return 0.0


def player_result(game):
    white = (game.white or "").strip().lower()
    is_white = white == PLAYER

    if game.result == "1/2-1/2":
        return "draws", is_white

    if game.result == "1-0":
        return ("wins" if is_white else "losses"), is_white

    if game.result == "0-1":
        return ("losses" if is_white else "wins"), is_white

    return "unknown", is_white


def is_player_move(move, is_white):
    return (move.color == "w") == is_white


def profile_cpl_values(moves):
    # 100000 is the intentional mate-loss penalty used by the
    # move analyzer. Keep it out of ordinary CPL averages.
    return [
        move.centipawn_loss
        for move in moves
        if move.centipawn_loss is not None
        and float(move.centipawn_loss) < 100000.0
    ]


def phase_stats(moves):
    buckets = defaultdict(lambda: {
        "moves": 0,
        "accuracy": [],
        "cpl": [],
        "blunders": 0,
        "mistakes": 0,
        "inaccuracies": 0,
    })

    for move in moves:
        phase = move.phase or "middlegame"
        row = buckets[phase]

        row["moves"] += 1

        if move.accuracy is not None:
            row["accuracy"].append(move.accuracy)

        if move.centipawn_loss is not None:
            row["cpl"].append(move.centipawn_loss)

        if move.classification == "blunder":
            row["blunders"] += 1
        elif move.classification == "mistake":
            row["mistakes"] += 1
        elif move.classification == "inaccuracy":
            row["inaccuracies"] += 1

    result = {}

    for phase, row in buckets.items():
        result[phase] = {
            "moves": row["moves"],
            "accuracy": safe_avg(row["accuracy"]),
            "cpl": safe_avg(row["cpl"]),
            "blunders": row["blunders"],
            "mistakes": row["mistakes"],
            "inaccuracies": row["inaccuracies"],
        }

    return result


def build_profile():
    session = SessionLocal()

    try:
        games = session.scalars(
            select(Game)
            .where(
                Game.white.ilike(PLAYER) |
                Game.black.ilike(PLAYER)
            )
            .order_by(
                Game.played_at.desc(),
                Game.id.desc(),
            )
            .limit(WINDOW)
        ).all()

        games.reverse()

        if not games:
            raise RuntimeError("NO_GAMES_FOUND")

        game_ids = [game.id for game in games]

        moves = session.scalars(
            select(GameMove)
            .where(GameMove.game_id.in_(game_ids))
            .order_by(GameMove.game_id, GameMove.ply)
        ).all()

        motifs = session.scalars(
            select(Motif)
            .where(Motif.game_id.in_(game_ids))
        ).all()

        moves_by_game = defaultdict(list)

        for move in moves:
            moves_by_game[move.game_id].append(move)

        overall = {
            "wins": 0,
            "draws": 0,
            "losses": 0,
        }

        by_color = {
            "white": {"wins": 0, "draws": 0, "losses": 0, "games": 0},
            "black": {"wins": 0, "draws": 0, "losses": 0, "games": 0},
        }

        by_time_control = defaultdict(
            lambda: {
                "games": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "accuracy": [],
                "cpl": [],
                "blunders": 0,
            }
        )

        by_rating_bucket = defaultdict(
            lambda: {
                "games": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "accuracy": [],
            }
        )

        opening_stats = defaultdict(
            lambda: {
                "games": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "accuracy": [],
                "cpl": [],
            }
        )

        phase_totals = defaultdict(
            lambda: {
                "accuracy": [],
                "cpl": [],
                "blunders": 0,
                "mistakes": 0,
                "inaccuracies": 0,
                "moves": 0,
            }
        )

        motif_counts = Counter()
        motif_severity = Counter()
        motif_metrics = defaultdict(lambda: {
            "count": 0,
            "cpl": [],
            "blunders": 0,
            "mistakes": 0,
            "inaccuracies": 0,
            "loss_games": 0,
            "win_games": 0,
        })

        termination_counts = Counter()

        game_result_by_id = {}
        game_color_by_id = {}

        game_summaries = []

        total_accuracy = []
        total_cpl = []

        total_blunders = 0
        total_mistakes = 0
        total_inaccuracies = 0
        total_mate_losses = 0

        pressure_moves = 0
        pressure_blunders = 0
        pressure_mistakes = 0
        pressure_accuracy = []

        recent_results = []

        for game in games:
            result, is_white = player_result(game)

            if result not in ("wins", "draws", "losses"):
                continue

            overall[result] += 1
            game_result_by_id[game.id] = result
            game_color_by_id[game.id] = "white" if is_white else "black"

            termination = (game.termination or "unknown").strip().lower()
            termination_counts[termination] += 1

            color = "white" if is_white else "black"
            by_color[color]["games"] += 1
            by_color[color][result] += 1

            game_moves = moves_by_game.get(game.id, [])

            # Profile only the player's own moves. Opponent moves must
            # never contribute to personal accuracy, CPL, phase,
            # classification, or time-pressure statistics.
            player_moves = [
                move
                for move in game_moves
                if is_player_move(move, is_white)
            ]

            accuracies = [
                move.accuracy
                for move in player_moves
                if move.accuracy is not None
            ]

            cpls = profile_cpl_values(player_moves)

            game_accuracy = safe_avg(accuracies)
            game_cpl = safe_avg(cpls)

            mate_losses = sum(
                1 for move in player_moves
                if move.centipawn_loss is not None
                and float(move.centipawn_loss) >= 100000.0
                and move.classification == "blunder"
            )

            blunders = sum(
                1 for move in player_moves
                if move.classification == "blunder"
            )

            mistakes = sum(
                1 for move in player_moves
                if move.classification == "mistake"
            )

            inaccuracies = sum(
                1 for move in player_moves
                if move.classification == "inaccuracy"
            )

            total_accuracy.extend(accuracies)
            total_cpl.extend(cpls)

            total_blunders += blunders
            total_mistakes += mistakes
            total_inaccuracies += inaccuracies
            total_mate_losses += mate_losses

            time_format = classify_time_control(game.time_control)

            tf = by_time_control[time_format]
            tf["games"] += 1
            tf[result] += 1

            if accuracies:
                tf["accuracy"].append(game_accuracy)

            if cpls:
                tf["cpl"].append(game_cpl)

            tf["blunders"] += blunders

            opponent_rating = (
                game.black_rating
                if is_white
                else game.white_rating
            )

            if opponent_rating:
                bucket_start = int(opponent_rating // 100) * 100
                bucket = f"{bucket_start}-{bucket_start + 99}"

                rb = by_rating_bucket[bucket]
                rb["games"] += 1
                rb[result] += 1

                if game_accuracy:
                    rb["accuracy"].append(game_accuracy)

            opening_key = game.opening or game.eco or "Unknown"

            op = opening_stats[opening_key]
            op["games"] += 1
            op[result] += 1

            if game_accuracy:
                op["accuracy"].append(game_accuracy)

            if game_cpl:
                op["cpl"].append(game_cpl)

            for move in player_moves:
                phase = move.phase or "middlegame"

                ps = phase_totals[phase]
                ps["moves"] += 1

                if move.accuracy is not None:
                    ps["accuracy"].append(move.accuracy)

                if (
                    move.centipawn_loss is not None
                    and float(move.centipawn_loss) < 100000.0
                ):
                    ps["cpl"].append(move.centipawn_loss)

                if move.classification == "blunder":
                    ps["blunders"] += 1
                elif move.classification == "mistake":
                    ps["mistakes"] += 1
                elif move.classification == "inaccuracy":
                    ps["inaccuracies"] += 1

                base_time = parse_base_time(game.time_control)

                if move.clock_seconds is not None and base_time > 0:
                    pressure_threshold = max(15.0, base_time * 0.10)

                    if move.clock_seconds <= pressure_threshold:
                        pressure_moves += 1

                        if move.accuracy is not None:
                            pressure_accuracy.append(move.accuracy)

                        if move.classification == "blunder":
                            pressure_blunders += 1
                        elif move.classification == "mistake":
                            pressure_mistakes += 1

            recent_results.append({
                "game_id": game.id,
                "played_at": (
                    game.played_at.isoformat()
                    if game.played_at
                    else None
                ),
                "result": result,
                "accuracy": game_accuracy,
                "cpl": game_cpl,
            })

            game_summaries.append({
                "game_id": game.id,
                "played_at": (
                    game.played_at.isoformat()
                    if game.played_at
                    else None
                ),
                "white": game.white,
                "black": game.black,
                "result": game.result,
                "player_result": result,
                "color": color,
                "time_control": game.time_control,
                "time_format": time_format,
                "opponent_rating": opponent_rating,
                "accuracy": game_accuracy,
                "cpl": game_cpl,
                "blunders": blunders,
                "mistakes": mistakes,
                "inaccuracies": inaccuracies,
                "mate_losses": mate_losses,
            })

        move_by_id = {
            move.id: move
            for move in moves
        }

        for motif in motifs:
            name = motif.motif or "unknown"
            motif_counts[name] += 1

            if motif.severity:
                motif_severity[
                    f"{name}:{motif.severity}"
                ] += 1

            metric = motif_metrics[name]
            metric["count"] += 1

            move = move_by_id.get(motif.move_id)

            if move is not None:
                if (
                    move.centipawn_loss is not None
                    and float(move.centipawn_loss) < 100000.0
                ):
                    metric["cpl"].append(float(move.centipawn_loss))

                if move.classification == "blunder":
                    metric["blunders"] += 1
                elif move.classification == "mistake":
                    metric["mistakes"] += 1
                elif move.classification == "inaccuracy":
                    metric["inaccuracies"] += 1

            game_result = game_result_by_id.get(motif.game_id)

            if game_result == "losses":
                metric["loss_games"] += 1
            elif game_result == "wins":
                metric["win_games"] += 1

        phase_result = {}

        for phase, row in phase_totals.items():
            phase_result[phase] = {
                "moves": row["moves"],
                "accuracy": safe_avg(row["accuracy"]),
                "cpl": safe_avg(row["cpl"]),
                "blunders": row["blunders"],
                "mistakes": row["mistakes"],
                "inaccuracies": row["inaccuracies"],
            }

        phase_ranking = sorted(
            phase_result.items(),
            key=lambda item: item[1]["accuracy"],
            reverse=True,
        )

        strongest_phase = phase_ranking[0][0] if phase_ranking else None
        weakest_phase = phase_ranking[-1][0] if phase_ranking else None

        motif_ranking = motif_counts.most_common()

        motif_result = []

        for name, count in motif_ranking:
            metric = motif_metrics[name]

            avg_cpl = safe_avg(metric["cpl"])

            blunder_rate = pct(
                metric["blunders"],
                count,
            )

            mistake_rate = pct(
                metric["mistakes"],
                count,
            )

            loss_rate = pct(
                metric["loss_games"],
                count,
            )

            severity_score = (
                (blunder_rate * 0.45)
                + (mistake_rate * 0.20)
                + (min(avg_cpl, 500.0) / 5.0 * 0.20)
                + (loss_rate * 0.15)
            )

            motif_result.append({
                "motif": name,
                "count": count,
                "share": pct(count, len(motifs)),
                "average_cpl": avg_cpl,
                "blunders": metric["blunders"],
                "mistakes": metric["mistakes"],
                "inaccuracies": metric["inaccuracies"],
                "blunder_rate": blunder_rate,
                "mistake_rate": mistake_rate,
                "loss_rate": loss_rate,
                "weakness_score": round(severity_score, 2),
            })

        motif_result.sort(
            key=lambda row: (
                row["weakness_score"],
                row["count"],
            ),
            reverse=True,
        )

        weakest_motif = (
            motif_result[0]["motif"]
            if motif_result
            else None
        )

        strongest_motif = (
            min(
                motif_result,
                key=lambda row: (
                    row["weakness_score"],
                    -row["count"],
                ),
            )["motif"]
            if motif_result
            else None
        )

        color_result = {}

        for color, row in by_color.items():
            games_count = row["games"]

            color_result[color] = {
                **row,
                "win_rate": pct(row["wins"], games_count),
                "score_rate": round(
                    (
                        row["wins"] + 0.5 * row["draws"]
                    ) / games_count * 100,
                    2,
                ) if games_count else 0.0,
            }

        time_result = {}

        for time_format, row in by_time_control.items():
            time_result[time_format] = {
                "games": row["games"],
                "wins": row["wins"],
                "draws": row["draws"],
                "losses": row["losses"],
                "win_rate": pct(row["wins"], row["games"]),
                "score_rate": round(
                    (
                        row["wins"] + 0.5 * row["draws"]
                    ) / row["games"] * 100,
                    2,
                ) if row["games"] else 0.0,
                "accuracy": safe_avg(row["accuracy"]),
                "cpl": safe_avg(row["cpl"]),
                "blunders_per_game": round(
                    row["blunders"] / row["games"], 2
                ) if row["games"] else 0.0,
            }

        opening_result = []

        for opening, row in opening_stats.items():
            opening_result.append({
                "opening": opening,
                "games": row["games"],
                "wins": row["wins"],
                "draws": row["draws"],
                "losses": row["losses"],
                "win_rate": pct(row["wins"], row["games"]),
                "score_rate": round(
                    (
                        row["wins"] + 0.5 * row["draws"]
                    ) / row["games"] * 100,
                    2,
                ) if row["games"] else 0.0,
                "accuracy": safe_avg(row["accuracy"]),
                "cpl": safe_avg(row["cpl"]),
            })

        opening_result.sort(
            key=lambda row: (
                row["games"],
                row["score_rate"],
            ),
            reverse=True,
        )

        rating_result = []

        for bucket, row in by_rating_bucket.items():
            rating_result.append({
                "rating_bucket": bucket,
                "games": row["games"],
                "wins": row["wins"],
                "draws": row["draws"],
                "losses": row["losses"],
                "win_rate": pct(row["wins"], row["games"]),
                "accuracy": safe_avg(row["accuracy"]),
            })

        rating_result.sort(key=lambda row: row["rating_bucket"])

        longest_loss_streak = 0
        current_loss_streak = 0

        for item in recent_results:
            if item["result"] == "losses":
                current_loss_streak += 1
                longest_loss_streak = max(
                    longest_loss_streak,
                    current_loss_streak,
                )
            else:
                current_loss_streak = 0

        recent_window = recent_results[-10:]

        recent_accuracy = safe_avg(
            item["accuracy"]
            for item in recent_window
            if item["accuracy"] is not None
        )

        older_window = recent_results[:-10]

        older_accuracy = safe_avg(
            item["accuracy"]
            for item in older_window
            if item["accuracy"] is not None
        )

        trend_delta = round(
            recent_accuracy - older_accuracy,
            2,
        ) if recent_window and older_window else 0.0

        training_priorities = []

        if weakest_phase:
            training_priorities.append({
                "priority": 1,
                "area": weakest_phase,
                "reason": (
                    f"Lowest average accuracy among the analyzed phases: "
                    f"{phase_result[weakest_phase]['accuracy']:.2f}%."
                ),
            })

        if motif_ranking:
            motif_name, motif_count = motif_ranking[0]

            training_priorities.append({
                "priority": 2,
                "area": motif_name,
                "reason": (
                    f"Most frequently detected recurring motif: "
                    f"{motif_count} occurrences."
                ),
            })

        if pressure_moves:
            pressure_rate = pct(
                pressure_blunders + pressure_mistakes,
                pressure_moves,
            )

            training_priorities.append({
                "priority": 3,
                "area": "time_pressure",
                "reason": (
                    f"{pressure_rate:.1f}% of pressure moves became "
                    f"mistakes or blunders."
                ),
            })

        if longest_loss_streak >= 3:
            training_priorities.append({
                "priority": 4,
                "area": "streak_management",
                "reason": (
                    f"Longest analyzed losing streak was "
                    f"{longest_loss_streak} games."
                ),
            })

        summary = {
            "window": WINDOW,
            "player": PLAYER,
            "generated_at": datetime.utcnow().isoformat(),
            "games": {
                "analyzed": len(game_summaries),
                "wins": overall["wins"],
                "draws": overall["draws"],
                "losses": overall["losses"],
                "win_rate": pct(
                    overall["wins"],
                    len(game_summaries),
                ),
                "score_rate": round(
                    (
                        overall["wins"]
                        + 0.5 * overall["draws"]
                    )
                    / len(game_summaries) * 100,
                    2,
                ) if game_summaries else 0.0,
            },
            "accuracy": {
                "average": safe_avg(total_accuracy),
                "average_cpl": safe_avg(total_cpl),
                "blunders_per_game": round(
                    total_blunders / len(game_summaries), 2
                ) if game_summaries else 0.0,
                "mistakes_per_game": round(
                    total_mistakes / len(game_summaries), 2
                ) if game_summaries else 0.0,
                "inaccuracies_per_game": round(
                    total_inaccuracies / len(game_summaries), 2
                ) if game_summaries else 0.0,
                "mate_losses": total_mate_losses,
                "mate_losses_per_game": round(
                    total_mate_losses / len(game_summaries), 2
                ) if game_summaries else 0.0,
            },
            "color": color_result,
            "time_controls": time_result,
            "rating_buckets": rating_result,
            "phases": phase_result,
            "strongest_phase": strongest_phase,
            "weakest_phase": weakest_phase,
            "motifs": motif_result,
            "motif_summary": {
                "total_events": len(motifs),
                "most_common": (
                    motif_ranking[0][0]
                    if motif_ranking
                    else None
                ),
                "biggest_weakness": weakest_motif,
                "strongest_area": strongest_motif,
            },
            "terminations": [
                {
                    "termination": name,
                    "games": count,
                    "share": pct(
                        count,
                        len(game_summaries),
                    ),
                }
                for name, count in termination_counts.most_common()
            ],
            "openings": opening_result[:30],
            "time_pressure": {
                "moves": pressure_moves,
                "blunders": pressure_blunders,
                "mistakes": pressure_mistakes,
                "accuracy": safe_avg(pressure_accuracy),
            },
            "form": {
                "recent_games": recent_window,
                "recent_accuracy": recent_accuracy,
                "previous_accuracy": older_accuracy,
                "accuracy_delta": trend_delta,
                "longest_loss_streak": longest_loss_streak,
            },
            "training_priorities": training_priorities,
            "games_detail": game_summaries,
        }

        snapshot = ProfileSnapshot(
            games_analyzed=len(game_summaries),
            wins=overall["wins"],
            draws=overall["draws"],
            losses=overall["losses"],
            win_rate=summary["games"]["win_rate"],
            average_accuracy=summary["accuracy"]["average"],
            average_cpl=summary["accuracy"]["average_cpl"],
            blunders_per_game=summary["accuracy"]["blunders_per_game"],
            mistakes_per_game=summary["accuracy"]["mistakes_per_game"],
            inaccuracies_per_game=summary["accuracy"]["inaccuracies_per_game"],
            strongest_phase=strongest_phase,
            weakest_phase=weakest_phase,
            strongest_motif=strongest_motif,
            weakest_motif=weakest_motif,
            summary=json.dumps(
                summary,
                separators=(",", ":"),
            ),
        )

        session.add(snapshot)
        session.commit()

        print("PROFILE_ENGINE_OK")
        print("Games:", len(game_summaries))
        print("Wins:", overall["wins"])
        print("Draws:", overall["draws"])
        print("Losses:", overall["losses"])
        print("Average accuracy:", summary["accuracy"]["average"])
        print("Average CPL:", summary["accuracy"]["average_cpl"])
        print("Strongest phase:", strongest_phase)
        print("Weakest phase:", weakest_phase)
        print("Top motif:", strongest_motif)
        print("Loss streak:", longest_loss_streak)
        print("Time-pressure moves:", pressure_moves)
        print("Snapshot ID:", snapshot.id)

    finally:
        session.close()


if __name__ == "__main__":
    build_profile()
