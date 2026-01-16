"""
数据库迁移脚本：为Match表添加manual_reward字段
"""
from flask_app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        try:
            # 检查字段是否已存在
            result = db.session.execute(text("PRAGMA table_info(match)"))
            columns = [row[1] for row in result]
            
            if 'manual_reward' not in columns:
                print("添加 manual_reward 字段到 Match 表...")
                db.session.execute(text("ALTER TABLE match ADD COLUMN manual_reward FLOAT"))
                db.session.commit()
                print("✓ 字段添加成功！")
            else:
                print("✓ manual_reward 字段已存在，无需迁移")
        except Exception as e:
            print(f"✗ 迁移失败: {e}")
            db.session.rollback()

if __name__ == '__main__':
    migrate()
