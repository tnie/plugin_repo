import sqlite3
import hashlib
from datetime import datetime

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 创建插件表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                icon_path TEXT,
                version TEXT NOT NULL,
                author TEXT,
                checksum TEXT,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                download_count INTEGER DEFAULT 0,
                file_size INTEGER,
                supported_platform TEXT,
                dependencies TEXT,
                license TEXT,
                gui TEXT DEFAULT 'button'  -- 新增: 交互入口类型
            )
        ''')
        
        # 创建用户表（简易版）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        ''')
        
        # 插入默认管理员（如果不存在）
        admin_hash = hashlib.sha256('admin123'.encode()).hexdigest()
        cursor.execute('''
            INSERT OR IGNORE INTO users (username, password_hash) 
            VALUES (?, ?)
        ''', ('admin', admin_hash))
        
        conn.commit()
        conn.close()
    
    def add_plugin(self, plugin_data):
        """添加插件到数据库"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO plugins (
                name, type, description, icon_path, version, 
                author, checksum, filename, original_filename,
                file_size, supported_platform, dependencies, license, gui
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            plugin_data['name'],
            plugin_data['type'],
            plugin_data.get('description', ''),
            plugin_data.get('icon_path', ''),
            plugin_data['version'],
            plugin_data.get('author', ''),
            plugin_data.get('checksum', ''),
            plugin_data['filename'],
            plugin_data['original_filename'],
            plugin_data.get('file_size', 0),
            plugin_data.get('supported_platform', ''),
            plugin_data.get('dependencies', ''),
            plugin_data.get('license', ''),
            plugin_data.get('gui', 'button')  # 新增: 默认值为 button
        ))
        
        plugin_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return plugin_id
    
    def delete_plugin(self, plugin_id):
        """删除插件"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 先获取插件信息，用于删除相关文件
        cursor.execute('SELECT filename, icon_path FROM plugins WHERE id = ?', (plugin_id,))
        plugin = cursor.fetchone()
        
        if plugin:
            # 删除数据库记录
            cursor.execute('DELETE FROM plugins WHERE id = ?', (plugin_id,))
            conn.commit()
            
        conn.close()
        
        # 返回插件信息，用于删除文件
        if plugin:
            return {
                'filename': plugin[0],
                'icon_path': plugin[1]
            }
        return None
    
    def get_all_plugins(self):
        """获取所有插件"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM plugins ORDER BY upload_time DESC
        ''')
        
        plugins = cursor.fetchall()
        conn.close()
        return [dict(plugin) for plugin in plugins]
    
    def get_plugin_by_id(self, plugin_id):
        """根据ID获取插件"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM plugins WHERE id = ?', (plugin_id,))
        plugin = cursor.fetchone()
        
        # 增加下载计数
        if plugin:
            cursor.execute('''
                UPDATE plugins SET download_count = download_count + 1 
                WHERE id = ?
            ''', (plugin_id,))
            conn.commit()
        
        conn.close()
        return dict(plugin) if plugin else None
    
    def verify_admin(self, username, password):
        """验证管理员登录"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute('''
            SELECT id FROM users 
            WHERE username = ? AND password_hash = ?
        ''', (username, password_hash))
        
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def update_plugin(self, plugin_id, update_data):
        """更新插件信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 构建更新SQL
        update_fields = []
        values = []
        
        for field, value in update_data.items():
            update_fields.append(f"{field} = ?")
            values.append(value)
        
        values.append(plugin_id)
        
        update_sql = f'''
            UPDATE plugins SET
            {', '.join(update_fields)}
            WHERE id = ?
        '''
        
        cursor.execute(update_sql, values)
        conn.commit()
        conn.close()
        
        return True