import os
import pyodbc
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "UVT_DB")
DB_USER = os.getenv("DB_USER", "sa")
DB_PASS = os.getenv("DB_PASS", "")

drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
SELECTED_DRIVER = drivers[0] if drivers else "SQL Server"

CONN_STR = (
    f"DRIVER={{{SELECTED_DRIVER}}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"UID={DB_USER};"
    f"PWD={DB_PASS};"
    f"Encrypt=no;TrustServerCertificate=yes;"
)

@contextmanager
def get_db_cursor():
    conn = pyodbc.connect(CONN_STR)
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT @@VERSION, DB_NAME()")
            row = cur.fetchone()
            print(f">> [BAŞARILI] Bağlantı sağlandı!")
            print(f">> Veritabanı: {row[1]}")
            print(f">> SQL Server Versiyonu: {row[0][:50]}...")
    except Exception as e:
        print(f">> [HATA] Veritabanına bağlanılamadı: {e}")