```python
from pathlib import Path
import sqlite3
import shutil
import sys

ROOT = Path(__file__).resolve().parent
DB = ROOT / "zcharge.db"
BACKUP = ROOT / "zcharge.db.backup"

CONFIG = {
    "enabled": "1",
    "capacity_limit": "50",
    "recharging_limit": "48",
    "temperature_limit": "800",
    "charging_switch_path": "/sys/class/qcom-battery/input_suspend",
    "charging_switch_on": "0",
    "charging_switch_off": "1",
}


def main() -> None:
    if not DB.is_file():
        raise SystemExit(f"zcharge.db non trovato: {DB}")

    # Backup del DB originale
    shutil.copy2(DB, BACKUP)

    conn = sqlite3.connect(DB)

    try:
        cur = conn.cursor()

        # Mostra cosa c'è prima
        print("Configurazione PRIMA:")
        cur.execute("SELECT key, value FROM zcharge_config ORDER BY key")
        for key, value in cur.fetchall():
            print(f"  {key} = {value}")

        # Aggiorna le chiavi esistenti.
        # Il DB ufficiale le contiene già; INSERT viene usato solo
        # nel caso mancasse una chiave.
        for key, value in CONFIG.items():
            cur.execute(
                "SELECT 1 FROM zcharge_config WHERE key = ? LIMIT 1",
                (key,),
            )

            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO zcharge_config (key, value) VALUES (?, ?)",
                    (key, value),
                )
            else:
                cur.execute(
                    "UPDATE zcharge_config SET value = ? WHERE key = ?",
                    (value, key),
                )

        conn.commit()

        print("\nConfigurazione DOPO:")
        cur.execute("SELECT key, value FROM zcharge_config ORDER BY key")
        for key, value in cur.fetchall():
            print(f"  {key} = {value}")

    finally:
        conn.close()

    print(f"\nOK: {DB}")
    print(f"Backup: {BACKUP}")


if __name__ == "__main__":
    try:
        main()
    except sqlite3.Error as e:
        print(f"Errore SQLite: {e}", file=sys.stderr)
        raise SystemExit(1)
```
