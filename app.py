from flask import Flask, render_template, request, redirect, url_for, send_file, session, jsonify, send_from_directory
import os
import hashlib
import mimetypes
from werkzeug.utils import secure_filename
from config import Config
from database import Database
from ftp_manager import FTPManager

app = Flask(__name__)
app.config.from_object(Config)
Config.init_app(app)

# 初始化数据库
db = Database(app.config['DATABASE'])

# 初始化 FTP 管理器
ftp_manager = FTPManager(
    ini_path=app.config['LIST_INI_PATH'],
    db_path=app.config['DATABASE']
)

def allowed_file(filename):
    """检查文件扩展名是否允许"""
    if '.' not in filename:
        return True
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

def calculate_checksum(filepath):
    """计算文件的SHA256校验和"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_plugin_storage_path(plugin_uuid, version, filename):
    """获取插件存储路径（三级目录结构）"""
    # 创建目录结构：uploads/plugin_uuid/version/
    version_dir = os.path.join(app.config['UPLOAD_FOLDER'], plugin_uuid, version)
    os.makedirs(version_dir, exist_ok=True)
    
    # 文件路径
    file_path = os.path.join(version_dir, filename)
    return file_path

@app.template_filter('filesizeformat')
def filesizeformat_filter(value):
    """格式化文件大小为可读格式"""
    if value is None:
        return '0 Bytes'
    
    for unit in ['Bytes', 'KB', 'MB', 'GB', 'TB']:
        if value < 1024.0:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{value:.2f} PB"

@app.route('/')
def index():
    """插件列表页面"""
    plugins = db.get_all_plugins_with_latest_version()
    return render_template('list.html', plugins=plugins)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """管理员登录"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if db.verify_admin(username, password):
            session['admin_logged_in'] = True
            return redirect(url_for('upload'))
        else:
            return render_template('admin.html', error='用户名或密码错误')
    
    return render_template('admin.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """插件上传页面"""
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        # 获取表单数据
        name = request.form.get('name')
        plugin_type = request.form.get('type')
        description = request.form.get('description')
        version = request.form.get('version')
        author = request.form.get('author')
        supported_platform = request.form.get('supported_platform')
        category = request.form.get('category')  # 新增字段
        rating = request.form.get('rating', '5')  # 新增字段，默认5星
        gui_type = request.form.get('gui', 'button')
        
        # 检查插件是否已存在
        existing_plugins = db.get_all_plugins_with_latest_version()
        existing_plugin = None
        for plugin in existing_plugins:
            if plugin['name'] == name:
                existing_plugin = plugin
                break
        
        if existing_plugin:
            # 检查版本是否已存在
            versions = db.get_plugin_versions(existing_plugin['plugin_uuid'])
            for v in versions:
                if v['version'] == version:
                    return render_template('upload.html', 
                                         error=f'插件 "{name}" 的版本 {version} 已存在',
                                         allowed_extensions=', '.join(Config.ALLOWED_EXTENSIONS))
        
        # 处理文件上传
        if 'plugin_file' not in request.files:
            return render_template('upload.html', error='请选择插件文件')
        
        file = request.files['plugin_file']
        if file.filename == '':
            return render_template('upload.html', error='请选择插件文件')
        
        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            
            # 如果是新插件，创建插件记录
            if not existing_plugin:
                plugin_uuid = db.create_plugin({
                    'name': name,
                    'description': description,
                    'author': author,
                    'version': version
                })
            else:
                plugin_uuid = existing_plugin['plugin_uuid']
            
            # 生成唯一的文件名
            file_hash = hashlib.md5(f'{name}_{version}_{original_filename}'.encode()).hexdigest()
            filename = f"{file_hash}_{original_filename}"
            
            # 保存文件到三级目录结构
            file_path = get_plugin_storage_path(plugin_uuid, version, filename)
            file.save(file_path)
            
            # 计算文件大小和校验和
            file_size = os.path.getsize(file_path)
            checksum = calculate_checksum(file_path)
            
            # 处理图标上传
            icon_path = ''
            if 'icon_file' in request.files and request.files['icon_file'].filename:
                icon_file = request.files['icon_file']
                icon_filename = f"icon_{secure_filename(icon_file.filename)}"
                icon_dir = os.path.join(app.config['ICON_FOLDER'], plugin_uuid, version)
                os.makedirs(icon_dir, exist_ok=True)
                icon_path = os.path.join(icon_dir, icon_filename)
                icon_file.save(icon_path)
            
            # 保存版本信息到数据库
            version_data = {
                'version': version,
                'type': plugin_type,
                'gui': gui_type,
                'icon_path': icon_path,
                'checksum': checksum,
                'filename': filename,
                'original_filename': original_filename,
                'file_path': file_path,  # 存储完整的文件路径
                'file_size': file_size,
                'supported_platform': supported_platform,
                'category': category,  # 新增字段
                'rating': rating  # 新增字段
            }
            
            version_id = db.add_plugin_version(plugin_uuid, version_data)
            
            # 更新 list.ini 文件
            if app.config['FTP_ENABLED']:
                ftp_manager.update_ini_file()
            
            return redirect(url_for('index'))
    
    return render_template('upload.html', allowed_extensions=', '.join(Config.ALLOWED_EXTENSIONS))

@app.route('/delete/<plugin_uuid>', methods=['POST'])
def delete_plugin(plugin_uuid):
    """删除插件（所有版本）"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': '未授权'}), 401
    
    # 获取所有版本信息
    versions = db.delete_plugin(plugin_uuid)
    
    try:
        # 删除所有版本的文件和目录
        for version in versions:
            version_id, filename, file_path, icon_path = version
            
            # 删除插件文件
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            
            # 删除图标文件
            if icon_path and os.path.exists(icon_path):
                os.remove(icon_path)
            
            # 尝试删除空目录
            version_dir = os.path.dirname(file_path)
            if os.path.exists(version_dir) and not os.listdir(version_dir):
                os.rmdir(version_dir)
            
            icon_dir = os.path.dirname(icon_path) if icon_path else None
            if icon_dir and os.path.exists(icon_dir) and not os.listdir(icon_dir):
                os.rmdir(icon_dir)
        
        # 删除插件主目录（如果为空）
        plugin_dir = os.path.join(app.config['UPLOAD_FOLDER'], plugin_uuid)
        if os.path.exists(plugin_dir) and not os.listdir(plugin_dir):
            os.rmdir(plugin_dir)
        
        # 更新 list.ini 文件
        if app.config['FTP_ENABLED']:
            ftp_manager.update_ini_file()
        
        return jsonify({'success': True, 'message': '插件删除成功'})
    
    except Exception as e:
        return jsonify({'error': f'删除文件时出错: {str(e)}'}), 500

@app.route('/delete_version/<int:version_id>', methods=['POST'])
def delete_version(version_id):
    """删除特定版本"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': '未授权'}), 401
    
    # 获取版本信息
    version = db.get_version_by_id(version_id)  # 确保先查询版本信息
    if not version:
        return jsonify({'error': '版本不存在'}), 404
    
    try:
        # 删除版本记录
        db.delete_version(version_id)
        
        # 删除文件
        file_path = version['file_path']
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        
        icon_path = version['icon_path']
        if icon_path and os.path.exists(icon_path):
            os.remove(icon_path)
        
        # 尝试删除空目录
        version_dir = os.path.dirname(file_path)
        if os.path.exists(version_dir) and not os.listdir(version_dir):
            os.rmdir(version_dir)
            # 再尝试删除插件目录（如果为空）
            plugin_dir = os.path.dirname(version_dir)
            if os.path.exists(plugin_dir) and not os.listdir(plugin_dir):
                os.rmdir(plugin_dir)
        
        # 检查插件是否还有其他版本
        plugin_uuid = version['plugin_uuid']
        remaining_versions = db.get_plugin_versions(plugin_uuid)
        if not remaining_versions:
            # 删除插件记录
            db.delete_plugin(plugin_uuid)
        
        # 更新 list.ini 文件
        if app.config['FTP_ENABLED']:
            ftp_manager.update_ini_file()
        
        return jsonify({'success': True, 'message': '版本删除成功'})
    
    except Exception as e:
        return jsonify({'error': f'删除文件时出错: {str(e)}'}), 500

@app.route('/download/<int:version_id>')
def download_plugin(version_id):
    """下载插件文件"""
    print(f"下载请求: version_id={version_id}")  # 添加调试信息
    
    version = db.get_version_by_id(version_id)
    if not version:
        print(f"版本不存在: {version_id}")  # 添加调试信息
        return "插件版本不存在", 404
    
    print(f"找到版本: {version}")  # 添加调试信息
    
    # 增加下载计数
    try:
        db.increment_download_count(version_id)
        print("下载计数增加成功")  # 添加调试信息
    except Exception as e:
        print(f"下载计数增加失败: {e}")  # 添加调试信息
    
    # 设置下载文件名
    plugin = db.get_plugin_by_uuid(version['plugin_uuid'])
    if plugin:
        download_name = f"{plugin['name']}_v{version['version']}.{version['original_filename'].split('.')[-1]}"
    else:
        download_name = version['original_filename']
    
    print(f"文件路径: {version['file_path']}")  # 添加调试信息
    print(f"下载名称: {download_name}")  # 添加调试信息
    
    # 检查文件是否存在
    if not os.path.exists(version['file_path']):
        print(f"文件不存在: {version['file_path']}")  # 添加调试信息
        return "文件不存在", 404
    
    return send_file(
        version['file_path'],
        as_attachment=True,
        download_name=download_name,
        mimetype=mimetypes.guess_type(version['file_path'])[0] or 'application/octet-stream'
    )

@app.route('/api/plugins')
def api_plugins():
    """API：获取插件列表（JSON格式）"""
    plugins = db.get_all_plugins_with_latest_version()
    
    # 转换为API响应格式
    result = []
    for plugin in plugins:
        if plugin.get('version_id'):  # 确保有版本信息
            # 添加 FTP 下载地址
            ftp_download_url = None
            if app.config['FTP_ENABLED'] and plugin.get('filename'):
                ftp_download_url = f"{app.config['FTP_BASE_URL']}uploads/{plugin['plugin_uuid']}/{plugin['latest_version']}/{plugin['filename']}"
            
            result.append({
                'id': plugin['plugin_uuid'],
                'version_id': plugin['version_id'],
                'name': plugin['name'],
                'type': plugin['type'],
                'description': plugin['description'],
                'version': plugin['latest_version'],
                'author': plugin['author'],
                'checksum': plugin['checksum'],
                'download_url': url_for('download_plugin', version_id=plugin['version_id'], _external=True),
                'ftp_download_url': ftp_download_url,
                'file_size': plugin['file_size'],
                'upload_time': plugin['upload_time'],
                'download_count': plugin['download_count'],
                'total_downloads': plugin['total_downloads'],
                'icon_path': plugin.get('icon_path', ''),
                'supported_platform': plugin.get('supported_platform', ''),
                'category': plugin.get('category', ''),  # 新增字段
                'rating': plugin.get('rating', '5'),  # 新增字段
                'gui': plugin.get('gui', 'button')
            })
    
    return jsonify(result)

@app.route('/api/plugin/<plugin_uuid>')
def api_plugin_detail(plugin_uuid):
    """API：获取插件详情（包括所有版本）"""
    plugin = db.get_plugin_by_uuid(plugin_uuid)
    if not plugin:
        return jsonify({'error': 'Plugin not found'}), 404
    
    versions = db.get_plugin_versions(plugin_uuid)
    
    plugin_detail = {
        'plugin_uuid': plugin['plugin_uuid'],
        'name': plugin['name'],
        'description': plugin['description'],
        'author': plugin['author'],
        'created_time': plugin['created_time'],
        'updated_time': plugin['updated_time'],
        'latest_version': plugin['latest_version'],
        'total_downloads': plugin['total_downloads'],
        'versions': []
    }
    
    for version in versions:
        version_info = {
            'version_id': version['id'],
            'version': version['version'],
            'type': version['type'],
            'gui': version['gui'],
            'download_url': url_for('download_plugin', version_id=version['id'], _external=True),
            'file_size': version['file_size'],
            'upload_time': version['upload_time'],
            'download_count': version['download_count'],
            'supported_platform': version['supported_platform'],
            'category': version.get('category', ''),  # 新增字段
            'rating': version.get('rating', '5'),  # 新增字段
            'checksum': version['checksum']
        }
        
        # 添加 FTP 下载地址
        if app.config['FTP_ENABLED'] and version.get('filename'):
            version_info['ftp_download_url'] = f"{app.config['FTP_BASE_URL']}uploads/{plugin_uuid}/{version['version']}/{version['filename']}"
        
        plugin_detail['versions'].append(version_info)
    
    return jsonify(plugin_detail)

@app.route('/detail/<plugin_uuid>', methods=['GET', 'POST'])
def plugin_detail(plugin_uuid):
    """插件详情页面"""
    plugin = db.get_plugin_by_uuid(plugin_uuid)
    if not plugin:
        return "插件不存在", 404
    
    versions = db.get_plugin_versions(plugin_uuid)
    latest_version = db.get_latest_version(plugin_uuid)
    
    if request.method == 'POST':
        if not session.get('admin_logged_in'):
            return jsonify({'error': '未授权'}), 401
        
        # 获取表单数据
        name = request.form.get('name')
        description = request.form.get('description')
        author = request.form.get('author')
        
        # 更新插件基本信息
        db.update_plugin_info(plugin_uuid, {
            'name': name,
            'description': description,
            'author': author
        })
        
        # 处理新版本上传
        if 'plugin_file' in request.files and request.files['plugin_file'].filename:
            file = request.files['plugin_file']
            if file.filename and allowed_file(file.filename):
                # 获取新版本号
                new_version = request.form.get('version')
                if not new_version:
                    # 如果没有提供版本号，自动递增
                    if latest_version:
                        # 尝试解析版本号
                        import re
                        version_parts = re.findall(r'\d+', latest_version['version'])
                        if version_parts:
                            # 递增最后一位
                            last_part = int(version_parts[-1]) + 1
                            new_version = re.sub(r'\d+$', str(last_part), latest_version['version'])
                        else:
                            new_version = f"{latest_version['version']}.1"
                    else:
                        new_version = '1.0.0'
                
                plugin_type = request.form.get('type', 'executable')
                gui_type = request.form.get('gui', 'button')
                supported_platform = request.form.get('supported_platform', '')
                category = request.form.get('category', '')  # 新增字段
                rating = request.form.get('rating', '5')  # 新增字段
                
                original_filename = secure_filename(file.filename)
                file_hash = hashlib.md5(f'{name}_{new_version}_{original_filename}'.encode()).hexdigest()
                filename = f"{file_hash}_{original_filename}"
                
                # 保存文件到三级目录结构
                file_path = get_plugin_storage_path(plugin_uuid, new_version, filename)
                file.save(file_path)
                
                # 计算文件大小和校验和
                file_size = os.path.getsize(file_path)
                checksum = calculate_checksum(file_path)
                
                # 处理图标上传
                icon_path = ''
                if 'icon_file' in request.files and request.files['icon_file'].filename:
                    icon_file = request.files['icon_file']
                    icon_filename = f"icon_{secure_filename(icon_file.filename)}"
                    icon_dir = os.path.join(app.config['ICON_FOLDER'], plugin_uuid, new_version)
                    os.makedirs(icon_dir, exist_ok=True)
                    icon_path = os.path.join(icon_dir, icon_filename)
                    icon_file.save(icon_path)
                elif latest_version and latest_version.get('icon_path'):
                    # 复制上一个版本的图标
                    old_icon_path = latest_version['icon_path']
                    if os.path.exists(old_icon_path):
                        icon_dir = os.path.join(app.config['ICON_FOLDER'], plugin_uuid, new_version)
                        os.makedirs(icon_dir, exist_ok=True)
                        icon_filename = os.path.basename(old_icon_path)
                        icon_path = os.path.join(icon_dir, icon_filename)
                        import shutil
                        shutil.copy2(old_icon_path, icon_path)
                
                # 保存新版本信息
                version_data = {
                    'version': new_version,
                    'type': plugin_type,
                    'gui': gui_type,
                    'icon_path': icon_path,
                    'checksum': checksum,
                    'filename': filename,
                    'original_filename': original_filename,
                    'file_path': file_path,
                    'file_size': file_size,
                    'supported_platform': supported_platform,
                    'category': category,  # 新增字段
                    'rating': rating  # 新增字段
                }
                
                db.add_plugin_version(plugin_uuid, version_data)
        
        # 更新 list.ini 文件
        if app.config['FTP_ENABLED']:
            ftp_manager.update_ini_file()
        
        # 重新获取数据
        plugin = db.get_plugin_by_uuid(plugin_uuid)
        versions = db.get_plugin_versions(plugin_uuid)
        latest_version = db.get_latest_version(plugin_uuid)
        
        return render_template('detail.html', 
                             plugin=plugin, 
                             versions=versions,
                             latest_version=latest_version,
                             success='插件信息已更新')
    
    return render_template('detail.html', 
                         plugin=plugin, 
                         versions=versions,
                         latest_version=latest_version)

@app.route('/icon/<plugin_uuid>/<version>')
def get_plugin_icon(plugin_uuid, version):
    """获取插件图标"""
    versions = db.get_plugin_versions(plugin_uuid)
    icon_path = None
    
    # 查找指定版本的图标
    for v in versions:
        if v['version'] == version and v.get('icon_path'):
            icon_path = v['icon_path']
            break
    
    if icon_path and os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/png')
    
    # 返回默认图标
    default_icon = os.path.join(app.config['ICON_FOLDER'], 'default.png')
    if os.path.exists(default_icon):
        return send_file(default_icon, mimetype='image/png')
    
    return '', 404

@app.route('/api/ftp/list')
def get_ftp_list():
    """获取 list.ini 文件内容"""
    if not app.config['FTP_ENABLED']:
        return jsonify({'error': 'FTP功能未启用'}), 400
    
    ini_content = ftp_manager.get_ini_content()
    return ini_content, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/ftp/list.ini')
def serve_list_ini():
    """提供 list.ini 文件下载"""
    if not app.config['FTP_ENABLED']:
        return "FTP功能未启用", 404
    
    return send_from_directory(
        os.path.dirname(app.config['LIST_INI_PATH']),
        os.path.basename(app.config['LIST_INI_PATH']),
        as_attachment=False,
        mimetype='text/plain'
    )

@app.route('/logout')
def logout():
    """退出登录"""
    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.secret_key = app.config['SECRET_KEY']
    app.run(debug=True, host='0.0.0.0', port=5201)