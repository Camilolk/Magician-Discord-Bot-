"""Find exact Telegram message identifiers for a PDF already indexed by Magician.

Usage: python find_telegram_pdf.py "example filename"
This script never downloads files or changes the authorization manifest.
"""
import argparse
import sqlite3
from database import DB_PATH


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="Part of the PDF filename")
    parser.add_argument("--limit", type=int, default=15, help="Máximo de resultados (1-200)")
    args = parser.parse_args()
    if not 1 <= args.limit <= 200:
        parser.error("--limit debe estar entre 1 y 200")
    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """SELECT title, telegram_chat_id, telegram_message_id
               FROM novels WHERE title LIKE ? ESCAPE '\\'
               ORDER BY telegram_message_id DESC LIMIT ?""",
            ("%" + args.filename.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", args.limit),
        ).fetchall()
    if not rows:
        print("No se encontró ese archivo en magician.db")
        return
    for title, chat_id, message_id in rows:
        print(f"{title} | chat_id={chat_id} | message_id={message_id}")


if __name__ == "__main__":
    main()
