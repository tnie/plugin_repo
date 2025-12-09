import os

class Config:
    # 基础配置
    SECRET_KEY = 'your-secret-key-here'  # 生产环境请更改
    UPLOAD_FOLDER = 'uploads'
    ICON_FOLDER = 'icons'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB最大文件大小
    DATABASE = 'plugins.db'
    
    # 允许的文件扩展名
    ALLOWED_EXTENSIONS = {
        'exe', 'dll', 'so', 'dylib', 'py', 
        'zip', 'tar', 'gz', 'whl'
    }
    
    # 管理员密码（简易实现）
    ADMIN_PASSWORD = 'admin123'  # 生产环境请使用更强密码
    
    @staticmethod
    def init_app(app):
        # 确保目录存在
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['ICON_FOLDER'], exist_ok=True)