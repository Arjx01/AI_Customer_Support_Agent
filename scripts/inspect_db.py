import sqlite3
import json

con = sqlite3.connect('orders.db')
cur = con.cursor()
tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]
print('Tables:', tables)

for t in tables:
    print(f'\n==============================')
    print(f'Table: {t}')
    print('==============================')
    schema = cur.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
    print('CREATE TABLE statement:\n', schema)
    print('\nColumns (cid, name, type, notnull, dflt_value, pk):')
    for col in cur.execute(f"PRAGMA table_info({t});").fetchall():
        print(" ", col)
    print('\nForeign Keys (id, seq, table, from, to, on_update, on_delete, match):')
    for fk in cur.execute(f"PRAGMA foreign_key_list({t});").fetchall():
        print(" ", fk)
    print('\nSample rows:')
    rows = cur.execute(f"SELECT * FROM {t}").fetchall()
    print(f"Total row count: {len(rows)}")
    for row in rows[:5]:
        print(" ", row)

con.close()
