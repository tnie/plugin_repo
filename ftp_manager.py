import configparser
import os
from database import Database

class FTPManager:
    def __init__(self, ini_path='list.ini', db_path='plugins.db'):
        self.ini_path = ini_path
        self.db = Database(db_path)
    
    def generate_ini_content(self):
        """生成 list.ini 文件内容"""
        plugins = self.db.get_all_plugins()
        
        config = configparser.ConfigParser(allow_no_value=True)
        
        for i, plugin in enumerate(plugins):
            section_name = f'PluginInfo'
            if i > 0:
                section_name = f'PluginInfo.{i}'
            
            config.add_section(section_name)
            
            # 基本属性
            config.set(section_name, 'name', plugin['name'])
            config.set(section_name, 'description', plugin.get('description', ''))
            config.set(section_name, 'version', plugin.get('version', 'v1.0'))
            
            # 类型映射：database 类型 -> ini 类型
            type_mapping = {
                'executable': 'app',
                'library': 'lib',
                'script': 'app',
                'package': 'app',
                'other': 'app'
            }
            db_type = plugin.get('type', 'executable')
            ini_type = type_mapping.get(db_type, 'app')
            config.set(section_name, 'type', ini_type)
            
            # GUI 类型（从数据库获取）
            gui_type = plugin.get('gui', 'button')
            config.set(section_name, 'gui', gui_type)
            
            # 图标路径 - 使用 FTP 路径
            icon_path = plugin.get('icon_path', '')
            if icon_path:
                # 转换为 FTP 路径格式
                ftp_icon_path = self._convert_to_ftp_path(icon_path)
                config.set(section_name, 'icon', ftp_icon_path)
            else:
                config.set(section_name, 'icon', 'icons/default.png')
            
            # 文件路径 - 使用 FTP 路径
            filename = plugin.get('filename', '')
            if filename:
                ftp_file_path = self._convert_to_ftp_path(filename, is_plugin=True)
                config.set(section_name, 'path', ftp_file_path)
            
            # 可选：添加其他属性作为注释
            author = plugin.get('author', '')
            if author:
                config.set(section_name, '# author', author)
            
            platform = plugin.get('supported_platform', '')
            if platform:
                config.set(section_name, '# platform', platform)
        
        return config
    
    def _convert_to_ftp_path(self, local_path, is_plugin=False):
        """将本地路径转换为 FTP 路径格式"""
        if not local_path:
            return ''
        
        # 获取文件名
        filename = os.path.basename(local_path)
        
        # 根据文件类型确定目录
        if is_plugin:
            # 插件文件放在 uploads 目录 - 去掉 ../ 前缀
            return f'uploads/{filename}'
        else:
            # 图标文件放在 icons 目录 - 去掉 ../ 前缀
            return f'icons/{filename}'
    
    def update_ini_file(self):
        """更新 list.ini 文件"""
        config = self.generate_ini_content()
        
        with open(self.ini_path, 'w', encoding='utf-8') as f:
            config.write(f)
        
        print(f"已更新 {self.ini_path} 文件")
        return True
    
    def get_ini_content(self):
        """获取当前的 ini 文件内容"""
        if os.path.exists(self.ini_path):
            with open(self.ini_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""