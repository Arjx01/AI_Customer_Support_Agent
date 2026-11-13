import sqlite3
import sys

def run_query(sql: str, db_path: str = "orders.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        if sql.strip().upper().startswith(("SELECT", "PRAGMA")):
            col_names = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            if not rows:
                print("No rows returned.")
                return
            
            # Compute column widths for pretty tabular output
            widths = [len(c) for c in col_names]
            for r in rows:
                for i, val in enumerate(r):
                    widths[i] = max(widths[i], len(str(val)))
            
            # Header
            header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(col_names))
            separator = "-+-".join("-" * widths[i] for i in range(len(col_names)))
            print(header)
            print(separator)
            
            # Rows
            for r in rows:
                print(" | ".join(str(val).ljust(widths[i]) for i, val in enumerate(r)))
            print(f"\n({len(rows)} row{'s' if len(rows) != 1 else ''})")
        else:
            conn.commit()
            print(f"Query executed successfully. Rows affected: {cursor.rowcount}")
    except Exception as e:
        print(f"SQL Error: {e}", file=sys.stderr)
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        run_query(query)
    else:
        print("Interactive SQLite Terminal for orders.db (type 'exit' or Ctrl+C to quit)\n")
        while True:
            try:
                sql = input("sqlite> ").strip()
                if not sql:
                    continue
                if sql.lower() in ["exit", "quit", ".quit", ".exit"]:
                    break
                run_query(sql)
                print()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
