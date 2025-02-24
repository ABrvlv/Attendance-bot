import sqlite3

DB_CONN = {}
def get_guild_db(guild_id):
    if guild_id not in DB_CONN:
        db_path = f"guilds/{guild_id}.db"
        conn = sqlite3.connect(db_path, isolation_level=None)
        conn.execute("PRAGMA synchronous = FULL")
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            total_balance INTEGER DEFAULT 0,
            join_date INTEGER
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS giveaways (
            message_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            prize TEXT NOT NULL,
            points INTEGER NOT NULL,
            end_time INTEGER NOT NULL
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            giveaway_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (giveaway_id) REFERENCES giveaways(message_id) ON DELETE CASCADE
        )
        """)
        conn.commit()
        DB_CONN[guild_id] = (conn, cursor)
    return DB_CONN[guild_id]

