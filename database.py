import sqlite3
import hashlib
from datetime import datetime
import uuid

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 创建插件表（主表）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plugins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_uuid TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                author TEXT,
                created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                latest_version TEXT,
                total_downloads INTEGER DEFAULT 0
            )
        ''')
        
        # 创建插件版本表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS plugin_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_uuid TEXT NOT NULL,
                version TEXT NOT NULL,
                type TEXT NOT NULL,
                gui TEXT DEFAULT 'button',
                icon_path TEXT,
                checksum TEXT,
                filename TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                download_count INTEGER DEFAULT 0,
                file_size INTEGER,
                supported_platform TEXT,
                dependencies TEXT,
                license TEXT,
                FOREIGN KEY (plugin_uuid) REFERENCES plugins (plugin_uuid),
                UNIQUE(plugin_uuid, version)
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
    
    def create_plugin(self, plugin_data):
        """创建新插件（主记录）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        plugin_uuid = str(uuid.uuid4())
        
        cursor.execute('''
            INSERT INTO plugins (plugin_uuid, name, description, author, latest_version)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            plugin_uuid,
            plugin_data['name'],
            plugin_data.get('description', ''),
            plugin_data.get('author', ''),
            plugin_data.get('version', '1.0.0')
        ))
        
        conn.commit()
        conn.close()
        return plugin_uuid
    
    def add_plugin_version(self, plugin_uuid, version_data):
        """添加插件版本"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO plugin_versions (
                plugin_uuid, version, type, gui, icon_path,
                checksum, filename, original_filename, file_path,
                file_size, supported_platform, dependencies, license
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            plugin_uuid,
            version_data['version'],
            version_data['type'],
            version_data.get('gui', 'button'),
            version_data.get('icon_path', ''),
            version_data.get('checksum', ''),
            version_data['filename'],
            version_data['original_filename'],
            version_data['file_path'],
            version_data.get('file_size', 0),
            version_data.get('supported_platform', ''),
            version_data.get('dependencies', ''),
            version_data.get('license', '')
        ))
        
        version_id = cursor.lastrowid
        
        # 更新插件的最新版本
        cursor.execute('''
            UPDATE plugins 
            SET latest_version = ?, updated_time = CURRENT_TIMESTAMP
            WHERE plugin_uuid = ?
        ''', (version_data['version'], plugin_uuid))
        
        conn.commit()
        conn.close()
        return version_id
    
    def get_all_plugins_with_latest_version(self):
        """获取所有插件及其最新版本信息"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                p.plugin_uuid,
                p.name,
                p.description,
                p.author,
                p.created_time,
                p.updated_time,
                p.latest_version,
                p.total_downloads,
                v.id as version_id,
                v.type,
                v.gui,
                v.icon_path,
                v.checksum,
                v.filename,
                v.original_filename,
                v.file_path,
                v.upload_time,
                v.download_count,
                v.file_size,
                v.supported_platform,
                v.dependencies,
                v.license
            FROM plugins p
            LEFT JOIN plugin_versions v ON 
                p.plugin_uuid = v.plugin_uuid AND 
                p.latest_version = v.version
            ORDER BY p.updated_time DESC
        ''')
        
        plugins = cursor.fetchall()
        conn.close()
        return [dict(plugin) for plugin in plugins]
    
    def get_plugin_by_uuid(self, plugin_uuid):
        """根据UUID获取插件信息"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM plugins WHERE plugin_uuid = ?', (plugin_uuid,))
        plugin = cursor.fetchone()
        
        conn.close()
        return dict(plugin) if plugin else None
    
    def get_plugin_versions(self, plugin_uuid):
        """获取插件的所有版本"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM plugin_versions 
            WHERE plugin_uuid = ? 
            ORDER BY upload_time DESC
        ''', (plugin_uuid,))
        
        versions = cursor.fetchall()
        conn.close()
        return [dict(version) for version in versions]
    
    def get_version_by_id(self, version_id):
        """根据版本ID获取版本信息"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM plugin_versions WHERE id = ?', (version_id,))
        version = cursor.fetchone()
        
        conn.close()
        return dict(version) if version else None
    
    def get_latest_version(self, plugin_uuid):
        """获取插件的最新版本"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT v.* FROM plugin_versions v
            JOIN plugins p ON p.plugin_uuid = v.plugin_uuid
            WHERE p.plugin_uuid = ? AND p.latest_version = v.version
        ''', (plugin_uuid,))
        
        version = cursor.fetchone()
        conn.close()
        return dict(version) if version else None
    
    def delete_plugin(self, plugin_uuid):
        """删除插件（包括所有版本）"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 先获取所有版本的文件信息
        cursor.execute('SELECT id, filename, file_path, icon_path FROM plugin_versions WHERE plugin_uuid = ?', (plugin_uuid,))
        versions = cursor.fetchall()
        
        # 删除数据库记录
        cursor.execute('DELETE FROM plugin_versions WHERE plugin_uuid = ?', (plugin_uuid,))
        cursor.execute('DELETE FROM plugins WHERE plugin_uuid = ?', (plugin_uuid,))
        
        conn.commit()
        conn.close()
        
        # 返回版本信息，用于删除文件
        return versions
    
    def delete_version(self, version_id):
        """删除指定版本"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 获取版本信息
        cursor.execute('SELECT * FROM plugin_versions WHERE id = ?', (version_id,))
        version = cursor.fetchone()
        
        if version:
            plugin_uuid = version[1]
            version_number = version[2]
            
            # 删除版本
            cursor.execute('DELETE FROM plugin_versions WHERE id = ?', (version_id,))
            
            # 如果删除的是最新版本，需要更新插件的最新版本
            cursor.execute('SELECT latest_version FROM plugins WHERE plugin_uuid = ?', (plugin_uuid,))
            latest_version_result = cursor.fetchone()
            
            if latest_version_result and latest_version_result[0] == version_number:
                # 获取最新的版本号
                cursor.execute('SELECT MAX(version) FROM plugin_versions WHERE plugin_uuid = ?', (plugin_uuid,))
                new_latest = cursor.fetchone()
                
                if new_latest and new_latest[0]:
                    cursor.execute('UPDATE plugins SET latest_version = ? WHERE plugin_uuid = ?', (new_latest[0], plugin_uuid))
                else:
                    cursor.execute('UPDATE plugins SET latest_version = NULL WHERE plugin_uuid = ?', (plugin_uuid,))
        
        conn.commit()
        conn.close()
        
        return dict(version) if version else None
    
    def increment_download_count(self, version_id):
        """增加版本下载计数"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 增加版本下载计数
        cursor.execute('''
            UPDATE plugin_versions SET download_count = download_count + 1 
            WHERE id = ?
        ''', (version_id,))
        
        # 增加插件总下载计数
        cursor.execute('''
            UPDATE plugins 
            SET total_downloads = total_downloads + 1
            WHERE plugin_uuid = (
                SELECT plugin_uuid FROM plugin_versions WHERE id = ?
            )
        ''', (version_id,))
        
        conn.commit()
        conn.close()
    
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
    
    def update_plugin_info(self, plugin_uuid, update_data):
        """更新插件基本信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        update_fields = []
        values = []
        
        for field, value in update_data.items():
            if field in ['name', 'description', 'author']:
                update_fields.append(f"{field} = ?")
                values.append(value)
        
        if update_fields:
            values.append(plugin_uuid)
            update_sql = f'''
                UPDATE plugins SET
                {', '.join(update_fields)},
                updated_time = CURRENT_TIMESTAMP
                WHERE plugin_uuid = ?
            '''
            
            cursor.execute(update_sql, values)
        
        conn.commit()
        conn.close()
        
        return True