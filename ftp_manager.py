import configparser
import os
from database import Database

class FTPManager:
    def __init__(self, ini_path='list.ini', db_path='plugins.db'):
        self.ini_path = ini_path
        self.db = Database(db_path)
    
    def generate_ini_content(self):
        """生成 list.ini 文件内容"""
        plugins = self.db.get_all_plugins_with_latest_version()
        
        config = configparser.ConfigParser(allow_no_value=True)
        
        for i, plugin in enumerate(plugins):
            if not plugin.get('version_id'):  # 没有版本的插件不显示
                continue
                
            section_name = f'PluginInfo'
            if i > 0:
                section_name = f'PluginInfo.{i}'
            
            config.add_section(section_name)
            
            # 基本属性
            config.set(section_name, 'name', plugin['name'])
            config.set(section_name, 'description', plugin.get('description', ''))
            config.set(section_name, 'version', plugin.get('latest_version', 'v1.0'))
            
            # 类型映射
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
            
            # GUI 类型
            gui_type = plugin.get('gui', 'button')
            config.set(section_name, 'gui', gui_type)
            
            # 图标路径 - 使用三级目录结构
            icon_path = plugin.get('icon_path', '')
            if icon_path:
                # 提取 plugin_uuid 和 version
                import re
                match = re.search(r'icons/([^/]+)/([^/]+)/', icon_path)
                if match:
                    plugin_uuid, version = match.groups()
                    ftp_icon_path = f'icons/{plugin_uuid}/{version}/{os.path.basename(icon_path)}'
                    config.set(section_name, 'icon', ftp_icon_path)
                else:
                    config.set(section_name, 'icon', 'icons/default.png')
            else:
                config.set(section_name, 'icon', 'icons/default.png')
            
            # 文件路径 - 使用三级目录结构
            if plugin.get('filename') and plugin.get('plugin_uuid') and plugin.get('latest_version'):
                ftp_file_path = f'uploads/{plugin["plugin_uuid"]}/{plugin["latest_version"]}/{plugin["filename"]}'
                config.set(section_name, 'path', ftp_file_path)
            
            # 新增属性：打分
            rating = plugin.get('rating', 5)  # 默认5星好评
            config.set(section_name, 'rating', str(rating))
            
            # 新增属性：分类
            category = plugin.get('category', '未分类')  # 默认分类为“未分类”
            config.set(section_name, 'category', category)
            
            # 可选：添加其他属性作为注释
            author = plugin.get('author', 'Unknown Author')
            config.set(section_name, 'author', author)
            
            platform = plugin.get('supported_platform', '')
            if platform:
                config.set(section_name, '# platform', platform)
        
        return config
    
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