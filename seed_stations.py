import bcrypt
from database import get_db_cursor

# Şifre: 1234 (bcrypt ile doğrudan hashleme)
salt = bcrypt.gensalt()
DEFAULT_PASSWORD_HASH = bcrypt.hashpw(b"1234", salt).decode("utf-8")

USERS_TO_SEED = [
    # İstasyonlar (Operatörler)
    ("lzr", "Lazer Kesim İstasyonu", "OPERATOR", "Lazer"),
    ("abk", "Abkant Büküm İstasyonu", "OPERATOR", "Abkant"),
    ("kyn1", "Kaynak İstasyonu 1", "OPERATOR", "Kaynak"),
    ("kyn2", "Kaynak İstasyonu 2", "OPERATOR", "Kaynak"),
    ("kyn3", "Kaynak İstasyonu 3", "OPERATOR", "Kaynak"),
    ("kyn4", "Kaynak İstasyonu 4", "OPERATOR", "Kaynak"),
    ("kyn5", "Kaynak İstasyonu 5", "OPERATOR", "Kaynak"),
    ("kyn6", "Kaynak İstasyonu 6", "OPERATOR", "Kaynak"),
    ("kyn7", "Kaynak İstasyonu 7", "OPERATOR", "Kaynak"),
    ("kyn8", "Kaynak İstasyonu 8", "OPERATOR", "Kaynak"),
    ("tmz1", "Temizlik / Çapak İstasyonu 1", "OPERATOR", "Temizlik"),
    ("tmz2", "Temizlik / Çapak İstasyonu 2", "OPERATOR", "Temizlik"),
    # Planlama ve Yönetim
    ("Planlama", "Üretim Planlama Sorumlusu", "PLANNER", None),
    ("Yonetim", "Fabrika Üst Yönetimi", "ADMIN", None)
]

def seed():
    with get_db_cursor() as cur:
        for username, full_name, role, cat_name in USERS_TO_SEED:
            # 1. Kullanıcıyı ekle veya varsa güncelle
            cur.execute("""
                IF NOT EXISTS (SELECT 1 FROM dbo.Users WHERE username = ?)
                BEGIN
                    INSERT INTO dbo.Users (username, password_hash, full_name, factory_location, role, is_active)
                    VALUES (?, ?, ?, 'TR', ?, 1)
                END
                ELSE
                BEGIN
                    UPDATE dbo.Users 
                    SET password_hash = ?, full_name = ?, role = ?, is_active = 1
                    WHERE username = ?
                END
            """, (username, username, DEFAULT_PASSWORD_HASH, full_name, role, DEFAULT_PASSWORD_HASH, full_name, role, username))

            # Kullanıcı ID'sini al
            cur.execute("SELECT id FROM dbo.Users WHERE username = ?", (username,))
            user_id = cur.fetchone()[0]

            # 2. İstasyon ise UserCategories tablosuna bağla
            if cat_name:
                cur.execute("""
                    IF NOT EXISTS (SELECT 1 FROM dbo.UserCategories WHERE user_id = ? AND category_name = ?)
                    BEGIN
                        INSERT INTO dbo.UserCategories (user_id, category_name)
                        VALUES (?, ?)
                    END
                """, (user_id, cat_name, user_id, cat_name))

        print(f"Toplam {len(USERS_TO_SEED)} kullanıcı ve istasyon kaydı başarıyla oluşturuldu/güncellendi!")

if __name__ == "__main__":
    seed()