"""Creates or repairs the PAH operator account without touching other users."""
import bcrypt

from database import get_db_cursor


USERNAME = "pah"
PASSWORD = "1234"
FULL_NAME = "PAH Kırma İstasyonu"
FACTORY = "TR"
CATEGORY_CODE = "PAH"


def seed_pah_user():
    password_hash = bcrypt.hashpw(PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM dbo.StationCategories WHERE code = ?", (CATEGORY_CODE,))
        category = cur.fetchone()
        if not category:
            raise RuntimeError("Önce 20260911_add_pah_station.sql migration dosyasını UVT_DB'de çalıştırın.")
        category_id = category[0]

        cur.execute("SELECT id FROM dbo.Users WHERE username = ?", (USERNAME,))
        user = cur.fetchone()
        if user:
            user_id = user[0]
            cur.execute("""
                UPDATE dbo.Users
                SET password_hash = ?, full_name = ?, factory_location = ?, role = 'OPERATOR', is_active = 1
                WHERE id = ?
            """, (password_hash, FULL_NAME, FACTORY, user_id))
        else:
            cur.execute("""
                INSERT INTO dbo.Users (username, password_hash, full_name, factory_location, role, is_active)
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?, 'OPERATOR', 1)
            """, (USERNAME, password_hash, FULL_NAME, FACTORY))
            user_id = cur.fetchone()[0]

        # The live UVT schema stores only the two foreign keys here.
        cur.execute("SELECT 1 FROM dbo.UserCategories WHERE user_id = ? AND category_id = ?", (user_id, category_id))
        if cur.fetchone():
            pass
        else:
            cur.execute("""
                INSERT INTO dbo.UserCategories (user_id, category_id)
                VALUES (?, ?)
            """, (user_id, category_id))

    print("PAH istasyonu kullanıcısı hazır: kullanıcı adı 'pah', şifre '1234'.")


if __name__ == "__main__":
    seed_pah_user()
