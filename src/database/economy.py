import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Tuple, List


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "economy.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_economy_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            user_id INTEGER,
            guild_id INTEGER,
            cash INTEGER DEFAULT 0,
            bank INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            voice_seconds INTEGER DEFAULT 0,
            arrest_until REAL,
            daily_cd REAL,
            work_cd REAL,
            weekly_cd REAL,
            rob_cd REAL,
            robberies_total INTEGER DEFAULT 0,
            robberies_success INTEGER DEFAULT 0,
            robberies_fail INTEGER DEFAULT 0,
            robberies_arrest INTEGER DEFAULT 0,
            messages_sent INTEGER DEFAULT 0,
            temp_roles_json TEXT NULL,
            PRIMARY KEY (user_id, guild_id)
        )
        """
    )
    
    # Add messages_sent column if it doesn't exist (migration)
    try:
        c.execute("ALTER TABLE accounts ADD COLUMN messages_sent INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    # Add notifications_enabled column if it doesn't exist (migration)
    try:
        c.execute("ALTER TABLE accounts ADD COLUMN notifications_enabled INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    # Add description column to role_listings if it doesn't exist (migration)
    try:
        c.execute("ALTER TABLE role_listings ADD COLUMN description TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        # Column already exists
        pass
    
    # Check if owned_custom_roles has id column, if not recreate table
    try:
        c.execute("SELECT id FROM owned_custom_roles LIMIT 1")
    except sqlite3.OperationalError:
        # Table doesn't have id column, need to recreate
        try:
            # Create backup table
            c.execute("CREATE TABLE owned_custom_roles_backup AS SELECT * FROM owned_custom_roles")
            # Drop old table
            c.execute("DROP TABLE owned_custom_roles")
            # Create new table with id
            c.execute("""
                CREATE TABLE owned_custom_roles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    guild_id INTEGER,
                    role_id INTEGER,
                    created_at REAL DEFAULT (julianday('now')),
                    UNIQUE(user_id, guild_id, role_id)
                )
            """)
            # Migrate data from backup
            c.execute("""
                INSERT INTO owned_custom_roles (user_id, guild_id, role_id, created_at)
                SELECT user_id, guild_id, role_id, julianday('now') FROM owned_custom_roles_backup
            """)
            # Drop backup table
            c.execute("DROP TABLE owned_custom_roles_backup")
        except sqlite3.OperationalError:
            # Table doesn't exist yet, will be created below
            pass
    
    # Shop roles table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS shop_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            role_id INTEGER,
            price INTEGER NOT NULL,
            stock INTEGER NULL
        )
        """
    )
    # Custom role requests
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_role_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            name TEXT,
            color TEXT,
            image_url TEXT,
            status TEXT,
            created_at REAL,
            reviewed_by INTEGER NULL,
            reviewed_at REAL NULL
        )
        """
    )
    # Owned custom roles
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS owned_custom_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            role_id INTEGER,
            created_at REAL DEFAULT (julianday('now')),
            UNIQUE(user_id, guild_id, role_id)
        )
        """
    )
    # Role listings
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS role_listings (
            role_id INTEGER,
            guild_id INTEGER,
            seller_user_id INTEGER,
            price INTEGER,
            max_sales INTEGER NULL,
            sales_done INTEGER DEFAULT 0,
            description TEXT DEFAULT '',
            PRIMARY KEY (role_id, guild_id)
        )
        """
    )
    
    # Role edit requests
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS role_edit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            role_id INTEGER,
            new_name TEXT,
            new_color TEXT,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            reviewed_by INTEGER NULL,
            reviewed_at REAL NULL
        )
        """
    )
    
    # Commit all changes
    conn.commit()
    conn.close()


def get_or_create_account(user_id: int, guild_id: int) -> Tuple[int, int, int, int, int, Optional[float], Optional[float], Optional[float], Optional[float]]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT cash, bank, xp, level, voice_seconds, arrest_until, daily_cd, work_cd, weekly_cd, rob_cd, robberies_total, robberies_success, robberies_fail, robberies_arrest FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    if not row:
        c.execute("""
            INSERT INTO accounts (user_id, guild_id, cash, bank, xp, level, voice_seconds, 
                                arrest_until, daily_cd, work_cd, weekly_cd, rob_cd, 
                                robberies_total, robberies_success, robberies_fail, 
                                robberies_arrest, messages_sent, temp_roles_json)
            VALUES (?, ?, 0, 0, 0, 1, 0, NULL, NULL, NULL, NULL, NULL, 0, 0, 0, 0, 0, NULL)
        """, (user_id, guild_id))
        conn.commit()
        c.execute("SELECT cash, bank, xp, level, voice_seconds, arrest_until, daily_cd, work_cd, weekly_cd, rob_cd, robberies_total, robberies_success, robberies_fail, robberies_arrest FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = c.fetchone()
    conn.close()
    return row  # type: ignore


def set_money(user_id: int, guild_id: int, cash: Optional[int] = None, bank: Optional[int] = None):
    conn = get_connection()
    c = conn.cursor()
    if cash is not None:
        if cash < 0:
            cash = 0
        c.execute("UPDATE accounts SET cash=? WHERE user_id=? AND guild_id=?", (cash, user_id, guild_id))
    if bank is not None:
        if bank < 0:
            bank = 0
        c.execute("UPDATE accounts SET bank=? WHERE user_id=? AND guild_id=?", (bank, user_id, guild_id))
    conn.commit()
    conn.close()


def add_xp(user_id: int, guild_id: int, amount: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET xp = MAX(0, xp + ?) WHERE user_id=? AND guild_id=?", (amount, user_id, guild_id))
    conn.commit()
    conn.close()


def set_temp_role(user_id: int, guild_id: int, role_id: int, until_ts: float):
    import json
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT temp_roles_json FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    temp = {}
    if row and row[0]:
        try:
            temp = json.loads(row[0])
        except Exception:
            temp = {}
    temp[str(role_id)] = until_ts
    c.execute("UPDATE accounts SET temp_roles_json=? WHERE user_id=? AND guild_id=?", (json.dumps(temp), user_id, guild_id))
    conn.commit()
    conn.close()


def get_expired_temp_roles(guild_id: int, now_ts: float):
    import json
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, temp_roles_json FROM accounts WHERE guild_id=?", (guild_id,))
    rows = c.fetchall()
    conn.close()
    results = []
    for user_id, blob in rows:
        if not blob:
            continue
        try:
            data = json.loads(blob)
        except Exception:
            continue
        expired = [int(rid) for rid, until in data.items() if until and until <= now_ts]
        if expired:
            results.append((user_id, expired))
    return results


def remove_temp_roles(user_id: int, guild_id: int, role_ids: list[int]):
    import json
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT temp_roles_json FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    temp = {}
    if row and row[0]:
        try:
            temp = json.loads(row[0])
        except Exception:
            temp = {}
    for rid in role_ids:
        temp.pop(str(rid), None)
    c.execute("UPDATE accounts SET temp_roles_json=? WHERE user_id=? AND guild_id=?", (json.dumps(temp), user_id, guild_id))
    conn.commit()
    conn.close()


def add_cash(user_id: int, guild_id: int, amount: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET cash = MAX(0, cash + ?) WHERE user_id=? AND guild_id=?", (amount, user_id, guild_id))
    conn.commit()
    conn.close()


def add_bank(user_id: int, guild_id: int, amount: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET bank = MAX(0, bank + ?) WHERE user_id=? AND guild_id=?", (amount, user_id, guild_id))
    conn.commit()
    conn.close()


def transfer_cash_to_bank(user_id: int, guild_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT cash FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False
    c.execute("UPDATE accounts SET cash=cash-?, bank=bank+? WHERE user_id=? AND guild_id=?", (amount, amount, user_id, guild_id))
    conn.commit()
    conn.close()
    return True


def transfer_bank_to_cash(user_id: int, guild_id: int, amount: int) -> bool:
    if amount <= 0:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT bank FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    if not row or row[0] < amount:
        conn.close()
        return False
    c.execute("UPDATE accounts SET bank=bank-?, cash=cash+? WHERE user_id=? AND guild_id=?", (amount, amount, user_id, guild_id))
    conn.commit()
    conn.close()
    return True


def set_cooldown(user_id: int, guild_id: int, field: str, next_ts: float):
    if field not in ("daily_cd", "work_cd", "weekly_cd", "rob_cd"):
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"UPDATE accounts SET {field}=? WHERE user_id=? AND guild_id=?", (next_ts, user_id, guild_id))
    conn.commit()
    conn.close()


def get_cooldowns(user_id: int, guild_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT daily_cd, work_cd, weekly_cd, rob_cd, arrest_until FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    conn.close()
    return row


def add_voice_seconds(user_id: int, guild_id: int, seconds: int):
    if seconds <= 0:
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET voice_seconds = voice_seconds + ? WHERE user_id=? AND guild_id=?", (seconds, user_id, guild_id))
    conn.commit()
    conn.close()


def set_arrest(user_id: int, guild_id: int, until_ts: Optional[float]):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET arrest_until=? WHERE user_id=? AND guild_id=?", (until_ts, user_id, guild_id))
    conn.commit()
    conn.close()


def inc_robbery_stat(user_id: int, guild_id: int, success: Optional[bool] = None, arrest: bool = False):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET robberies_total = robberies_total + 1 WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    if success is True:
        c.execute("UPDATE accounts SET robberies_success = robberies_success + 1 WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    elif success is False:
        c.execute("UPDATE accounts SET robberies_fail = robberies_fail + 1 WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    if arrest:
        c.execute("UPDATE accounts SET robberies_arrest = robberies_arrest + 1 WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    conn.commit()
    conn.close()


def get_rob_stats(user_id: int, guild_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT robberies_total, robberies_success, robberies_fail, robberies_arrest FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    conn.close()
    return row or (0, 0, 0, 0)


def get_top_by_balance(guild_id: int, limit: int = 10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, (cash + bank) AS total, cash, bank FROM accounts WHERE guild_id=? ORDER BY total DESC LIMIT ?", (guild_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def get_top_by_level(guild_id: int, limit: int = 10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, level, xp FROM accounts WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT ?", (guild_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def get_top_by_voice(guild_id: int, limit: int = 10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, voice_seconds FROM accounts WHERE guild_id=? ORDER BY voice_seconds DESC LIMIT ?", (guild_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def get_rank_by_balance(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) + 1 FROM accounts a WHERE a.guild_id = ? AND (a.cash + a.bank) > (SELECT cash + bank FROM accounts WHERE user_id=? AND guild_id=?)", (guild_id, user_id, guild_id))
    rank = c.fetchone()[0]
    conn.close()
    return int(rank)


def get_rank_by_level(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) + 1 FROM accounts a WHERE a.guild_id = ? AND (a.level, a.xp) > (SELECT level, xp FROM accounts WHERE user_id=? AND guild_id=?)", (guild_id, user_id, guild_id))
    rank = c.fetchone()[0]
    conn.close()
    return int(rank)


def get_rank_by_voice(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) + 1 FROM accounts a WHERE a.guild_id = ? AND a.voice_seconds > (SELECT voice_seconds FROM accounts WHERE user_id=? AND guild_id=?)", (guild_id, user_id, guild_id))
    rank = c.fetchone()[0]
    conn.close()
    return int(rank)


def get_top_by_messages(guild_id: int, limit: int = 10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, messages_sent FROM accounts WHERE guild_id=? ORDER BY messages_sent DESC LIMIT ?", (guild_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def get_top_by_robberies(guild_id: int, limit: int = 10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, robberies_success, robberies_fail FROM accounts WHERE guild_id=? ORDER BY robberies_success DESC LIMIT ?", (guild_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


def get_rank_by_messages(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) + 1 FROM accounts a WHERE a.guild_id = ? AND a.messages_sent > (SELECT messages_sent FROM accounts WHERE user_id=? AND guild_id=?)", (guild_id, user_id, guild_id))
    rank = c.fetchone()[0]
    conn.close()
    return int(rank)


def get_rank_by_robberies(user_id: int, guild_id: int) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) + 1 FROM accounts a WHERE a.guild_id = ? AND a.robberies_success > (SELECT robberies_success FROM accounts WHERE user_id=? AND guild_id=?)", (guild_id, user_id, guild_id))
    rank = c.fetchone()[0]
    conn.close()
    return int(rank)


# Shop helpers
def get_shop_items(guild_id: int, order: str = 'price_desc', limit: int = 5, offset: int = 0):
    order_clause = {
        'price_desc': 'price DESC',
        'price_asc': 'price ASC',
        'availability': 'CASE WHEN stock IS NULL THEN 0 ELSE 1 END, stock DESC'
    }.get(order, 'price DESC')
    conn = get_connection()
    c = conn.cursor()
    c.execute(f"SELECT id, role_id, price, stock FROM shop_roles WHERE guild_id=? ORDER BY {order_clause} LIMIT ? OFFSET ?", (guild_id, limit, offset))
    rows = c.fetchall()
    conn.close()
    return rows


def purchase_shop_item(guild_id: int, user_id: int, item_id: int) -> tuple[bool, str, int, int]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT role_id, price, stock FROM shop_roles WHERE id=? AND guild_id=?", (item_id, guild_id))
    row = c.fetchone()
    if not row:
        conn.close()
        return False, "Товар не найден.", 0, 0
    role_id, price, stock = row
    # check bank funds
    c.execute("SELECT bank FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    bank_row = c.fetchone()
    if not bank_row or bank_row[0] < price:
        conn.close()
        return False, "Недостаточно средств в банке.", role_id, price
    # update stock
    if stock is not None:
        if stock <= 0:
            conn.close()
            return False, "Нет в наличии.", role_id, price
        c.execute("UPDATE shop_roles SET stock = stock - 1 WHERE id=?", (item_id,))
    # deduct
    c.execute("UPDATE accounts SET bank = bank - ? WHERE user_id=? AND guild_id=?", (price, user_id, guild_id))
    conn.commit()
    conn.close()
    return True, "Покупка успешна.", role_id, price


# Unified market (shop + user listings)
def get_market_items(guild_id: int, order: str = 'price_desc', limit: int = 5, offset: int = 0):
    order_clause = {
        'price_desc': 'price DESC',
        'price_asc': 'price ASC',
        'availability': 'avail DESC, price DESC'
    }.get(order, 'price DESC')
    conn = get_connection()
    c = conn.cursor()
    # availability for listings: remaining = (max_sales - sales_done) or NULL for unlimited
    c.execute(
        f"""
        SELECT 'shop' as kind, id, role_id, price, stock AS avail, NULL as seller_user_id, '' as description
        FROM shop_roles WHERE guild_id=?
        UNION ALL
        SELECT 'listing' as kind, NULL as id, role_id, price,
               CASE WHEN max_sales IS NULL THEN NULL ELSE (max_sales - sales_done) END AS avail,
               seller_user_id, COALESCE(description, '') as description
        FROM role_listings WHERE guild_id=?
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
        """,
        (guild_id, guild_id, limit, offset)
    )
    rows = c.fetchall()
    conn.close()
    # Normalize to list of dicts
    items = []
    for kind, id_or_null, role_id, price, avail, seller_user_id, description in rows:
        items.append({
            'kind': kind,
            'id': id_or_null,  # only for shop
            'role_id': role_id,
            'price': price,
            'stock': avail,
            'seller_user_id': seller_user_id,
            'description': description,
        })
    return items


def purchase_market_item(guild_id: int, buyer_user_id: int, kind: str, id_or_role: int) -> tuple[bool, str, int, int]:
    conn = get_connection()
    c = conn.cursor()
    if kind == 'shop':
        c.execute("SELECT role_id, price, stock FROM shop_roles WHERE id=? AND guild_id=?", (id_or_role, guild_id))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "Товар не найден.", 0, 0
        role_id, price, stock = row
        # funds
        c.execute("SELECT bank FROM accounts WHERE user_id=? AND guild_id=?", (buyer_user_id, guild_id))
        bank_row = c.fetchone()
        if not bank_row or bank_row[0] < price:
            conn.close()
            return False, "Недостаточно средств в банке.", role_id, price
        if stock is not None and stock <= 0:
            conn.close()
            return False, "Нет в наличии.", role_id, price
        if stock is not None:
            c.execute("UPDATE shop_roles SET stock = stock - 1 WHERE id=?", (id_or_role,))
        c.execute("UPDATE accounts SET bank = bank - ? WHERE user_id=? AND guild_id=?", (price, buyer_user_id, guild_id))
        conn.commit()
        conn.close()
        return True, "Покупка успешна.", role_id, price
    else:
        # listing: id_or_role is role_id key
        c.execute("SELECT seller_user_id, price, max_sales, sales_done FROM role_listings WHERE role_id=? AND guild_id=?", (id_or_role, guild_id))
        row = c.fetchone()
        if not row:
            conn.close()
            return False, "Лот не найден.", 0, 0
        seller_user_id, price, max_sales, sales_done = row
        # funds buyer
        c.execute("SELECT bank FROM accounts WHERE user_id=? AND guild_id=?", (buyer_user_id, guild_id))
        bank_row = c.fetchone()
        if not bank_row or bank_row[0] < price:
            conn.close()
            return False, "Недостаточно средств в банке.", id_or_role, price
        # stock check
        if max_sales is not None and sales_done >= max_sales:
            conn.close()
            return False, "Лимит продаж достигнут.", id_or_role, price
        # transfer funds
        c.execute("UPDATE accounts SET bank = bank - ? WHERE user_id=? AND guild_id=?", (price, buyer_user_id, guild_id))
        c.execute("UPDATE accounts SET bank = bank + ? WHERE user_id=? AND guild_id=?", (price, seller_user_id, guild_id))
        # increment sales
        c.execute("UPDATE role_listings SET sales_done = sales_done + 1 WHERE role_id=? AND guild_id=?", (id_or_role, guild_id))
        conn.commit()
        conn.close()
        return True, "Покупка успешна.", id_or_role, price


# Custom roles
def add_custom_role_request(user_id: int, guild_id: int, name: str, color: str, image_url: str) -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO custom_role_requests (user_id, guild_id, name, color, image_url, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (user_id, guild_id, name, color, image_url, datetime.utcnow().timestamp()),
    )
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return int(req_id)


def set_request_status(req_id: int, status: str, reviewed_by: int | None = None):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE custom_role_requests SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
        (status, reviewed_by, datetime.utcnow().timestamp(), req_id),
    )
    conn.commit()
    conn.close()


def get_request(req_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, user_id, guild_id, name, color, image_url, status FROM custom_role_requests WHERE id=?", (req_id,))
    row = c.fetchone()
    conn.close()
    return row


def add_owned_custom_role(user_id: int, guild_id: int, role_id: int):
    conn = get_connection()
    c = conn.cursor()
    
    # Check if id column exists
    try:
        c.execute("INSERT OR IGNORE INTO owned_custom_roles (user_id, guild_id, role_id, created_at) VALUES (?, ?, ?, julianday('now'))", (user_id, guild_id, role_id))
    except sqlite3.OperationalError:
        # Fallback for old table structure
        c.execute("INSERT OR IGNORE INTO owned_custom_roles (user_id, guild_id, role_id) VALUES (?, ?, ?)", (user_id, guild_id, role_id))
    
    conn.commit()
    conn.close()


def get_owned_custom_roles(user_id: int, guild_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT role_id FROM owned_custom_roles WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows


def get_owned_custom_roles_with_info(user_id: int, guild_id: int):
    """Get owned custom roles with their database IDs and creation info"""
    conn = get_connection()
    c = conn.cursor()
    
    # Check if id column exists
    try:
        c.execute("SELECT id, role_id, created_at FROM owned_custom_roles WHERE user_id=? AND guild_id=? ORDER BY created_at DESC", (user_id, guild_id))
        rows = c.fetchall()
    except sqlite3.OperationalError:
        # Fallback if id column doesn't exist yet
        c.execute("SELECT role_id FROM owned_custom_roles WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        role_rows = c.fetchall()
        # Create fake data with sequential IDs
        rows = [(i+1, row[0], 0.0) for i, row in enumerate(role_rows)]
    
    conn.close()
    return rows


def create_role_listing(guild_id: int, role_id: int, seller_user_id: int, price: int, max_sales: int | None, description: str = ''):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO role_listings (role_id, guild_id, seller_user_id, price, max_sales, sales_done, description) VALUES (?, ?, ?, ?, ?, COALESCE((SELECT sales_done FROM role_listings WHERE role_id=? AND guild_id=?), 0), ?)",
              (role_id, guild_id, seller_user_id, price, max_sales, role_id, guild_id, description))
    conn.commit()
    conn.close()


def update_role_listing(guild_id: int, role_id: int, price: int | None = None, max_sales: int | None = None):
    conn = get_connection()
    c = conn.cursor()
    if price is not None:
        c.execute("UPDATE role_listings SET price=? WHERE role_id=? AND guild_id=?", (price, role_id, guild_id))
    if max_sales is not None:
        c.execute("UPDATE role_listings SET max_sales=? WHERE role_id=? AND guild_id=?", (max_sales, role_id, guild_id))
    conn.commit()
    conn.close()


def remove_role_listing(guild_id: int, role_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM role_listings WHERE role_id=? AND guild_id=?", (role_id, guild_id))
    conn.commit()
    conn.close()


# Role edit requests
def add_role_edit_request(user_id: int, guild_id: int, role_id: int, new_name: str, new_color: str) -> int:
    """Create a new role edit request"""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO role_edit_requests (user_id, guild_id, role_id, new_name, new_color, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (user_id, guild_id, role_id, new_name, new_color, datetime.utcnow().timestamp()),
    )
    req_id = c.lastrowid
    conn.commit()
    conn.close()
    return int(req_id)


def get_role_edit_request(req_id: int):
    """Get role edit request by ID"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, user_id, guild_id, role_id, new_name, new_color, status FROM role_edit_requests WHERE id=?", (req_id,))
    row = c.fetchone()
    conn.close()
    return row


def set_role_edit_request_status(req_id: int, status: str, reviewed_by: int | None = None):
    """Update role edit request status"""
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "UPDATE role_edit_requests SET status=?, reviewed_by=?, reviewed_at=? WHERE id=?",
        (status, reviewed_by, datetime.utcnow().timestamp(), req_id),
    )
    conn.commit()
    conn.close()


def get_notifications_enabled(user_id: int, guild_id: int) -> bool:
    """Получить статус уведомлений пользователя"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT notifications_enabled FROM accounts WHERE user_id=? AND guild_id=?", (user_id, guild_id))
    row = c.fetchone()
    conn.close()
    
    if row is None:
        # Если аккаунт не существует, создаем его с уведомлениями по умолчанию
        get_or_create_account(user_id, guild_id)
        return True
    
    return bool(row[0])


def set_notifications_enabled(user_id: int, guild_id: int, enabled: bool):
    """Установить статус уведомлений пользователя"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        UPDATE accounts 
        SET notifications_enabled = ? 
        WHERE user_id = ? AND guild_id = ?
    """, (int(enabled), user_id, guild_id))
    conn.commit()
    conn.close()


def get_users_with_notifications_enabled(guild_id: int) -> List[Tuple[int, int]]:
    """Получить список пользователей с включенными уведомлениями"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT user_id, guild_id 
        FROM accounts 
        WHERE guild_id = ? AND notifications_enabled = 1
    """, (guild_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def cleanup_invalid_listings(guild_id: int, valid_role_owners: dict[int, list[int]]):
    """Удаляет листинги ролей, которыми пользователи больше не владеют"""
    conn = get_connection()
    c = conn.cursor()
    
    # Получаем все листинги
    c.execute("SELECT role_id, seller_user_id FROM role_listings WHERE guild_id=?", (guild_id,))
    listings = c.fetchall()
    
    to_remove = []
    for role_id, seller_user_id in listings:
        # Проверяем, владеет ли пользователь этой ролью
        if seller_user_id not in valid_role_owners or role_id not in valid_role_owners[seller_user_id]:
            to_remove.append(role_id)
    
    # Удаляем недействительные листинги
    if to_remove:
        c.execute("DELETE FROM role_listings WHERE guild_id=? AND role_id IN ({})".format(','.join('?' * len(to_remove))), (guild_id, *to_remove))
        conn.commit()
    
    conn.close()
    return len(to_remove)


def add_shop_role(guild_id: int, role_id: int, price: int, stock: int = None, description: str = ''):
    """Добавляет роль в магазин (админская функция)"""
    conn = get_connection()
    c = conn.cursor()
    
    # Проверяем, не существует ли уже эта роль в магазине
    c.execute("SELECT id FROM shop_roles WHERE guild_id=? AND role_id=?", (guild_id, role_id))
    if c.fetchone():
        conn.close()
        return False, "Роль уже есть в магазине"
    
    # Добавляем роль в магазин
    c.execute("INSERT INTO shop_roles (guild_id, role_id, price, stock) VALUES (?, ?, ?, ?)", 
              (guild_id, role_id, price, stock))
    conn.commit()
    conn.close()
    return True, "Роль успешно добавлена в магазин"


