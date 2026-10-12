from pathlib import Path
import re
import requests
import chess.pgn
from io import StringIO
from datetime import datetime
from sqlalchemy import select

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.database import SessionLocal
from database.models import Game

USERNAME = 'vinayayayay'
BASE_URL = f'https://api.chess.com/pub/player/{USERNAME}'
HEADERS = {'User-Agent': 'ChessMate Report/1.0'}

def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text

def get_archives():
    data = requests.get(f'{BASE_URL}/games/archives', headers=HEADERS, timeout=30).json()
    return data.get('archives', [])

def game_uuid(link):
    if not link:
        return None
    match = re.search(r'/([0-9]+)$', link)
    return match.group(1) if match else link

def parse_datetime(headers):
    date = headers.get('UTCDate')
    time = headers.get('UTCTime', '00:00:00')
    if not date:
        return None
    try:
        return datetime.strptime(f'{date} {time}', '%Y.%m.%d %H:%M:%S')
    except ValueError:
        return None

def import_archive(session, archive_url):
    pgn_text = fetch(archive_url + '/pgn')
    stream = StringIO(pgn_text)
    imported = 0
    skipped = 0

    while True:
        game = chess.pgn.read_game(stream)
        if game is None:
            break

        headers = game.headers
        link = headers.get('Link')
        uuid = game_uuid(link)

        if not uuid:
            skipped += 1
            continue

        existing = session.scalar(
            select(Game).where(Game.chesscom_uuid == uuid)
        )

        if existing:
            skipped += 1
            continue

        result = headers.get('Result')
        white = headers.get('White')
        black = headers.get('Black')

        game_row = Game(
            chesscom_uuid=uuid,
            url=link,
            pgn=str(game),
            played_at=parse_datetime(headers),
            white=white,
            black=black,
            white_rating=int(headers['WhiteElo']) if headers.get('WhiteElo', '').isdigit() else None,
            black_rating=int(headers['BlackElo']) if headers.get('BlackElo', '').isdigit() else None,
            result=result,
            time_control=headers.get('TimeControl'),
            eco=headers.get('ECO'),
            opening=headers.get('ECOUrl'),
            termination=headers.get('Termination'),
            analyzed=False,
        )

        session.add(game_row)
        imported += 1

    session.commit()

    return imported, skipped

def main():
    archives = get_archives()
    print(f"Archives found: {len(archives)}")

    session = SessionLocal()
    total_imported = 0
    total_skipped = 0
    total_archives = 0

    try:
        # Fetch newest months first. We only need enough recent games
        # to maintain the rolling 300-game window.
        for archive in reversed(archives):
            print(f"Fetching: {archive}")
            imported, skipped = import_archive(session, archive)

            total_imported += imported
            total_skipped += skipped
            total_archives += 1

            current_count = session.scalar(
                select(Game).count()
            ) if False else session.query(Game).count()

            print(
                f"  imported={imported}, "
                f"skipped={skipped}, "
                f"db_games={current_count}"
            )

            if current_count >= 300:
                break

        games = session.scalars(
            select(Game).order_by(
                Game.played_at.desc(),
                Game.id.desc()
            )
        ).all()

        removed = 0

        if len(games) > 300:
            for old_game in games[300:]:
                session.delete(old_game)
                removed += 1

            session.commit()

        kept = min(len(games), 300)

        print(
            f"Archives fetched: {total_archives}"
        )
        print(
            f"Rolling limit: kept={kept}, "
            f"removed={removed}"
        )

    finally:
        session.close()

    print()
    print("CHESSCOM_IMPORT_OK")
    print("Imported:", total_imported)
    print("Skipped:", total_skipped)
    print("Games kept:", kept)


if __name__ == '__main__':
    main()
