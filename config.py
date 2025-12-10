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
    
    # FTP 相关配置
    FTP_ENABLED = True
    LIST_INI_PATH = 'list.ini'  # FTP 服务中的 ini 文件路径
    FTP_BASE_URL = 'ftp://your-ftp-server.com/'  # FTP 服务器地址
    
    @staticmethod
    def init_app(app):
        # 确保目录存在
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(app.config['ICON_FOLDER'], exist_ok=True)
        
        # 确保默认图标存在
        default_icon = os.path.join(app.config['ICON_FOLDER'], 'default.png')
        if not os.path.exists(default_icon):
            # 创建一个简单的默认图标（这里可以替换为实际的图标文件）
            try:
                from PIL import Image, ImageDraw
                img = Image.new('RGB', (64, 64), color='#007bff')
                draw = ImageDraw.Draw(img)
                draw.ellipse([10, 10, 54, 54], fill='#ffffff')
                img.save(default_icon, 'PNG')
            except:
                pass  # 如果无法创建默认图标，跳过
