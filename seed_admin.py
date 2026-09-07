import os
import bcrypt
from database import get_db_cursor
from dotenv import load_dotenv

# .env dosyasındaki değişkenleri yükle
load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
ADMIN_FULLNAME = "Sistem Yöneticisi"
ADMIN_LOCATION = "TR"
ADMIN_ROLE = "ADMIN"


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def seed_admin_user():
    hashed_pwd = hash_password(ADMIN_PASSWORD)

    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM dbo.Users WHERE username = ?", (ADMIN_USERNAME,))
        existing = cur.fetchone()

        if existing:
            print(f">> [BİLGİ] '{ADMIN_USERNAME}' kullanıcısı zaten mevcut.")
            return

        insert_sql = """
            INSERT INTO dbo.Users (username, password_hash, full_name, factory_location, role, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """
        cur.execute(insert_sql, (ADMIN_USERNAME, hashed_pwd, ADMIN_FULLNAME, ADMIN_LOCATION, ADMIN_ROLE))
        print(f">> [BAŞARILI] '{ADMIN_USERNAME}' kullanıcısı ADMIN rolü ile oluşturuldu.")
        print(f">> Başlangıç Şifresi: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    seed_admin_user()