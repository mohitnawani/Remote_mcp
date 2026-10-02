from pathlib import Path
import json
import os
import sqlite3
import tempfile

import aiosqlite
from fastmcp import FastMCP


TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "expenses.db")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_PATH = PROJECT_ROOT / "categories.json"

mcp = FastMCP("ExpenseTracker")


def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
            """
        )
        c.execute(
            "INSERT OR IGNORE INTO expenses(date, amount, category) VALUES ('2000-01-01', 0, 'test')"
        )
        c.execute("DELETE FROM expenses WHERE category = 'test'")


init_db()


@mcp.tool()
async def add_expense(date, amount, category, subcategory="", note=""):
    """Add a new expense entry to the database."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
                (date, amount, category, subcategory, note),
            )
            expense_id = cur.lastrowid
            await c.commit()
            return {
                "status": "success",
                "id": expense_id,
                "message": "Expense added successfully",
            }
    except Exception as e:
        if "readonly" in str(e).lower():
            return {
                "status": "error",
                "message": "Database is in read-only mode. Check file permissions.",
            }
        return {"status": "error", "message": f"Database error: {str(e)}"}


@mcp.tool()
async def list_expenses(start_date, end_date):
    """List expense entries within an inclusive date range."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """
                SELECT id, date, amount, category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
                """,
                (start_date, end_date),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": f"Error listing expenses: {str(e)}"}


@mcp.tool()
async def summarize(start_date, end_date, category=None):
    """Summarize expenses by category within an inclusive date range."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            query = """
                SELECT category, SUM(amount) AS total_amount, COUNT(*) as count
                FROM expenses
                WHERE date BETWEEN ? AND ?
            """
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY total_amount DESC"

            cur = await c.execute(query, params)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in await cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": f"Error summarizing expenses: {str(e)}"}


@mcp.resource("expense:///categories", mime_type="application/json")
def categories():
    try:
        return CATEGORIES_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        default_categories = {
            "categories": [
                "Food & Dining",
                "Transportation",
                "Shopping",
                "Entertainment",
                "Bills & Utilities",
                "Healthcare",
                "Travel",
                "Education",
                "Business",
                "Other",
            ]
        }
        return json.dumps(default_categories, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Could not load categories: {str(e)}"})


def main():
    print(f"Database path: {DB_PATH}")
    mcp.run(transport="http", host="0.0.0.0", port=8000)
