import sqlite3
import hashlib
from datetime import datetime
import uuid
import re

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
                version_sort TEXT,  -- 新增：用于排序的版本字段
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
                category TEXT,  -- 新增字段
                rating INTEGER DEFAULT 5,  -- 新增字段，默认5星
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
    
    def _normalize_version(self, version_str):
        """规范化版本号，用于排序比较"""
        # 移除非数字和点的字符
        version_clean = re.sub(r'[^0-9.]', '', version_str)
        
        # 分割为数字部分
        parts = version_clean.split('.')
        
        # 确保至少有3部分（主版本.次版本.修订号）
        while len(parts) < 3:
            parts.append('0')
        
        # 将每部分转换为整数，然后格式化为固定长度的字符串
        normalized_parts = []
        for part in parts:
            try:
                num = int(part)
                # 格式化为5位数字，保证排序正确
                normalized_parts.append(f"{num:05d}")
            except ValueError:
                normalized_parts.append("00000")
        
        # 返回可用于排序的字符串
        return '.'.join(normalized_parts)
    
    def _compare_versions(self, version1, version2):
        """比较两个版本号，返回1表示version1更大，-1表示version2更大，0表示相等"""
        norm1 = self._normalize_version(version1)
        norm2 = self._normalize_version(version2)
        
        if norm1 > norm2:
            return 1
        elif norm1 < norm2:
            return -1
        else:
            return 0
    
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
        
        version = version_data['version']
        version_sort = self._normalize_version(version)
        
        cursor.execute('''
            INSERT INTO plugin_versions (
                plugin_uuid, version, version_sort, type, gui, icon_path,
                checksum, filename, original_filename, file_path,
                file_size, supported_platform, category, rating
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            plugin_uuid,
            version,
            version_sort,
            version_data['type'],
            version_data.get('gui', 'button'),
            version_data.get('icon_path', ''),
            version_data.get('checksum', ''),
            version_data['filename'],
            version_data['original_filename'],
            version_data['file_path'],
            version_data.get('file_size', 0),
            version_data.get('supported_platform', ''),
            version_data.get('category', ''),  # 新增字段
            version_data.get('rating', 5)  # 新增字段
        ))
        
        version_id = cursor.lastrowid
        
        # 获取当前最新版本
        cursor.execute('SELECT latest_version FROM plugins WHERE plugin_uuid = ?', (plugin_uuid,))
        result = cursor.fetchone()
        current_latest = result[0] if result else None
        
        # 比较版本号，选择最大的作为最新版本
        if current_latest is None:
            new_latest = version
        else:
            # 比较版本号，选择更大的
            if self._compare_versions(version, current_latest) > 0:
                new_latest = version
            else:
                new_latest = current_latest
        
        # 更新插件的最新版本
        cursor.execute('''
            UPDATE plugins 
            SET latest_version = ?, updated_time = CURRENT_TIMESTAMP
            WHERE plugin_uuid = ?
        ''', (new_latest, plugin_uuid))
        
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
                v.category,  -- 新增字段
                v.rating  -- 新增字段
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
        """获取插件的所有版本（按版本号降序排列）"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM plugin_versions 
            WHERE plugin_uuid = ? 
            ORDER BY version_sort DESC, upload_time DESC
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
        """获取插件的最新版本（版本号最大的）"""
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
        version = self.get_version_by_id(version_id)  # 确保先查询版本信息
        if not version:
            return None
        
        # 删除版本记录
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM plugin_versions WHERE id = ?', (version_id,))
        
        plugin_uuid = version['plugin_uuid']
        version_number = version['version']
        
        # 如果删除的是最新版本，需要重新计算最新版本
        cursor.execute('SELECT latest_version FROM plugins WHERE plugin_uuid = ?', (plugin_uuid,))
        latest_version_result = cursor.fetchone()
        
        if latest_version_result and latest_version_result[0] == version_number:
            # 获取版本号最大的版本
            cursor.execute('''
                SELECT version FROM plugin_versions 
                WHERE plugin_uuid = ? 
                ORDER BY version_sort DESC 
                LIMIT 1
            ''', (plugin_uuid,))
            new_latest = cursor.fetchone()
            
            if new_latest:
                cursor.execute('UPDATE plugins SET latest_version = ? WHERE plugin_uuid = ?', (new_latest[0], plugin_uuid))
            else:
                cursor.execute('UPDATE plugins SET latest_version = NULL WHERE plugin_uuid = ?', (plugin_uuid,))
        
        conn.commit()
        conn.close()
        
        return version
    
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
    
    def update_version_info(self, version_id, update_data):
        """更新版本信息"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        update_fields = []
        values = []
        
        for field, value in update_data.items():
            if field in ['version', 'type', 'gui', 'supported_platform', 'category', 'rating']:
                update_fields.append(f"{field} = ?")
                values.append(value)
        
        if update_fields:
            values.append(version_id)
            update_sql = f'''
                UPDATE plugin_versions SET
                {', '.join(update_fields)}
                WHERE id = ?
            '''
            
            cursor.execute(update_sql, values)
        
        conn.commit()
        conn.close()
        
        return True