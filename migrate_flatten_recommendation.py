"""
Migration: Flatten haircut_recommendation + haircut_recommendation_assoc
into a single haircut_recommendation table with direct haircut_id column.

Before:
  haircut_recommendation (id, face_shape_id, hair_type_id)
  haircut_recommendation_assoc (recommendation_id, haircut_id)

After:
  haircut_recommendation (id, face_shape_id, hair_type_id, haircut_id)
"""
import sqlalchemy
from sqlalchemy import text
from config import SQLALCHEMY_DATABASE_URI

engine = sqlalchemy.create_engine(SQLALCHEMY_DATABASE_URI)

def run():
    with engine.connect() as conn:
        # 1. Read current data
        old_recs = conn.execute(text("SELECT * FROM haircut_recommendation")).mappings().all()
        old_assoc = conn.execute(text("SELECT * FROM haircut_recommendation_assoc")).mappings().all()
        old_history = conn.execute(text("SELECT * FROM user_recommendation_history")).mappings().all()

        print(f"Old haircut_recommendation: {len(old_recs)} rows")
        print(f"Old haircut_recommendation_assoc: {len(old_assoc)} rows")
        print(f"Old user_recommendation_history: {len(old_history)} rows")

        # 2. Build flattened recommendation data
        #    old_rec_id -> {face_shape_id, hair_type_id}
        rec_lookup = {r['id']: dict(r) for r in old_recs}

        # New recommendations: one row per (face_shape_id, hair_type_id, haircut_id)
        new_recs = []
        # Mapping: old_rec_id -> list of new_rec_ids (one per haircut)
        old_to_new_map = {}
        new_id = 1
        for assoc in old_assoc:
            old_rec = rec_lookup[assoc['recommendation_id']]
            new_recs.append({
                'id': new_id,
                'face_shape_id': old_rec['face_shape_id'],
                'hair_type_id': old_rec['hair_type_id'],
                'haircut_id': assoc['haircut_id'],
            })
            if assoc['recommendation_id'] not in old_to_new_map:
                old_to_new_map[assoc['recommendation_id']] = []
            old_to_new_map[assoc['recommendation_id']].append(new_id)
            new_id += 1

        print(f"\nNew haircut_recommendation (flattened): {len(new_recs)} rows")

        # 3. Build new user_recommendation_history
        #    Each old history row that referenced 1 old_rec_id now expands to N rows
        new_history = []
        new_hist_id = 1
        for h in old_history:
            old_rec_id = h['haircut_recommendation_id']
            new_rec_ids = old_to_new_map.get(old_rec_id, [])
            for new_rec_id in new_rec_ids:
                new_history.append({
                    'id': new_hist_id,
                    'user_id': h['user_id'],
                    'haircut_recommendation_id': new_rec_id,
                    'scan_result_id': h['scan_result_id'],
                    'created_at': h.get('created_at'),
                })
                new_hist_id += 1

        print(f"New user_recommendation_history: {len(new_history)} rows")

        # 4. Drop old tables and recreate
        print("\nDropping old tables...")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))

        conn.execute(text("DROP TABLE IF EXISTS user_recommendation_history"))
        conn.execute(text("DROP TABLE IF EXISTS haircut_recommendation_assoc"))
        conn.execute(text("DROP TABLE IF EXISTS haircut_recommendation"))

        print("Creating new haircut_recommendation table...")
        conn.execute(text("""
            CREATE TABLE haircut_recommendation (
                id INTEGER NOT NULL AUTO_INCREMENT,
                face_shape_id INTEGER NOT NULL,
                hair_type_id INTEGER NOT NULL,
                haircut_id INTEGER NOT NULL,
                PRIMARY KEY (id),
                UNIQUE KEY uq_fs_ht_hc (face_shape_id, hair_type_id, haircut_id),
                FOREIGN KEY (face_shape_id) REFERENCES face_shape(id),
                FOREIGN KEY (hair_type_id) REFERENCES hair_type(id),
                FOREIGN KEY (haircut_id) REFERENCES haircut(id)
            )
        """))

        print("Creating new user_recommendation_history table...")
        conn.execute(text("""
            CREATE TABLE user_recommendation_history (
                id INTEGER NOT NULL AUTO_INCREMENT,
                user_id INTEGER NOT NULL,
                haircut_recommendation_id INTEGER NOT NULL,
                scan_result_id INTEGER NOT NULL,
                created_at DATETIME NULL,
                PRIMARY KEY (id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (haircut_recommendation_id) REFERENCES haircut_recommendation(id),
                FOREIGN KEY (scan_result_id) REFERENCES scan_result(id)
            )
        """))

        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

        # 5. Insert data
        if new_recs:
            conn.execute(
                text("INSERT INTO haircut_recommendation (id, face_shape_id, hair_type_id, haircut_id) VALUES (:id, :face_shape_id, :hair_type_id, :haircut_id)"),
                new_recs
            )
        print(f"Inserted {len(new_recs)} rows into haircut_recommendation")

        if new_history:
            conn.execute(
                text("INSERT INTO user_recommendation_history (id, user_id, haircut_recommendation_id, scan_result_id, created_at) VALUES (:id, :user_id, :haircut_recommendation_id, :scan_result_id, :created_at)"),
                new_history
            )
        print(f"Inserted {len(new_history)} rows into user_recommendation_history")

        conn.commit()
        print("\n✅ Migration completed successfully!")

if __name__ == '__main__':
    run()
