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
    plugins = db.get_all_plugins()
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
        dependencies = request.form.get('dependencies')
        license_type = request.form.get('license')
        gui_type = request.form.get('gui', 'button')  # 新增: 获取 GUI 类型
        
        # 处理文件上传
        if 'plugin_file' not in request.files:
            return render_template('upload.html', error='请选择插件文件')
        
        file = request.files['plugin_file']
        if file.filename == '':
            return render_template('upload.html', error='请选择插件文件')
        
        if file and allowed_file(file.filename):
            # 保存插件文件
            original_filename = secure_filename(file.filename)
            filename = f"{hashlib.md5(f'{name}_{version}'.encode()).hexdigest()}_{original_filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # 计算文件大小和校验和
            file_size = os.path.getsize(filepath)
            checksum = calculate_checksum(filepath)
            
            # 处理图标上传
            icon_path = ''
            if 'icon_file' in request.files and request.files['icon_file'].filename:
                icon_file = request.files['icon_file']
                icon_filename = f"{filename.split('.')[0]}_{secure_filename(icon_file.filename)}"
                icon_path = os.path.join(app.config['ICON_FOLDER'], icon_filename)
                icon_file.save(icon_path)
            
            # 保存到数据库
            plugin_data = {
                'name': name,
                'type': plugin_type,
                'description': description,
                'icon_path': icon_path,
                'version': version,
                'author': author,
                'checksum': checksum,
                'filename': filename,
                'original_filename': original_filename,
                'file_size': file_size,
                'supported_platform': supported_platform,
                'dependencies': dependencies,
                'license': license_type,
                'gui': gui_type  # 新增: GUI 类型
            }
            
            plugin_id = db.add_plugin(plugin_data)
            
            # 更新 list.ini 文件
            if app.config['FTP_ENABLED']:
                ftp_manager.update_ini_file()
            
            return redirect(url_for('index'))
    
    return render_template('upload.html', allowed_extensions=', '.join(Config.ALLOWED_EXTENSIONS))

@app.route('/delete/<int:plugin_id>', methods=['POST'])
def delete_plugin(plugin_id):
    """删除插件"""
    if not session.get('admin_logged_in'):
        return jsonify({'error': '未授权'}), 401
    
    # 获取插件信息
    plugin = db.delete_plugin(plugin_id)
    if not plugin:
        return jsonify({'error': '插件不存在'}), 404
    
    try:
        # 删除插件文件
        if plugin['filename']:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], plugin['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
        
        # 删除图标文件（如果存在）
        if plugin['icon_path']:
            icon_path = os.path.join(app.config['ICON_FOLDER'], os.path.basename(plugin['icon_path']))
            if os.path.exists(icon_path):
                os.remove(icon_path)
        
        # 更新 list.ini 文件
        if app.config['FTP_ENABLED']:
            ftp_manager.update_ini_file()
        
        return jsonify({'success': True, 'message': '插件删除成功'})
    
    except Exception as e:
        return jsonify({'error': f'删除文件时出错: {str(e)}'}), 500

@app.route('/download/<int:plugin_id>')
def download_plugin(plugin_id):
    """下载插件文件"""
    plugin = db.get_plugin_by_id(plugin_id, increment_download=True)
    if not plugin:
        return "插件不存在", 404
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], plugin['filename'])
    
    # 设置下载文件名
    download_name = f"{plugin['name']}_v{plugin['version']}.{plugin['filename'].split('.')[-1]}"
    
    return send_file(
        filepath,
        as_attachment=True,
        download_name=download_name,
        mimetype=mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
    )

@app.route('/api/plugins')
def api_plugins():
    """API：获取插件列表（JSON格式）"""
    plugins = db.get_all_plugins()
    
    # 转换为API响应格式
    result = []
    for plugin in plugins:
        # 添加 FTP 下载地址（新增）
        ftp_download_url = None
        if app.config['FTP_ENABLED'] and plugin.get('filename'):
            ftp_download_url = f"{app.config['FTP_BASE_URL']}uploads/{plugin['filename']}"
        
        result.append({
            'id': plugin['id'],
            'name': plugin['name'],
            'type': plugin['type'],
            'description': plugin['description'],
            'version': plugin['version'],
            'author': plugin['author'],
            'checksum': plugin['checksum'],
            'download_url': url_for('download_plugin', plugin_id=plugin['id'], _external=True),
            'ftp_download_url': ftp_download_url,  # 新增
            'file_size': plugin['file_size'],
            'upload_time': plugin['upload_time'],
            'download_count': plugin['download_count'],
            'icon_path': plugin.get('icon_path', ''),
            'supported_platform': plugin.get('supported_platform', ''),
            'dependencies': plugin.get('dependencies', ''),
            'license': plugin.get('license', '')
        })
    
    return jsonify(result)

@app.route('/api/plugin/<int:plugin_id>')
def api_plugin_detail(plugin_id):
    """API：获取插件详情"""
    plugin = db.get_plugin_by_id(plugin_id, increment_download=False)
    if not plugin:
        return jsonify({'error': 'Plugin not found'}), 404
    
    # 添加 FTP 下载地址（新增）
    ftp_download_url = None
    if app.config['FTP_ENABLED'] and plugin.get('filename'):
        ftp_download_url = f"{app.config['FTP_BASE_URL']}uploads/{plugin['filename']}"
    
    return jsonify({
        'id': plugin['id'],
        'name': plugin['name'],
        'type': plugin['type'],
        'description': plugin['description'],
        'version': plugin['version'],
        'author': plugin['author'],
        'checksum': plugin['checksum'],
        'download_url': url_for('download_plugin', plugin_id=plugin['id'], _external=True),
        'ftp_download_url': ftp_download_url,  # 新增
        'file_size': plugin['file_size'],
        'upload_time': plugin['upload_time'],
        'download_count': plugin['download_count'],
        'supported_platform': plugin['supported_platform'],
        'dependencies': plugin['dependencies'],
        'license': plugin['license'],
        'icon_path': plugin.get('icon_path', '')
    })

@app.route('/detail/<int:plugin_id>', methods=['GET', 'POST'])
def plugin_detail(plugin_id):
    """插件详情页面"""
    plugin = db.get_plugin_by_id(plugin_id, increment_download=False)
    if not plugin:
        return "插件不存在", 404
    
    if request.method == 'POST':
        if not session.get('admin_logged_in'):
            return jsonify({'error': '未授权'}), 401
        
        # 获取表单数据
        name = request.form.get('name')
        plugin_type = request.form.get('type')
        description = request.form.get('description')
        version = request.form.get('version')
        author = request.form.get('author')
        supported_platform = request.form.get('supported_platform')
        dependencies = request.form.get('dependencies')
        license_type = request.form.get('license')
        gui_type = request.form.get('gui', 'button')
        
        # 更新数据库
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE plugins SET
                name = ?, type = ?, description = ?, version = ?,
                author = ?, supported_platform = ?, dependencies = ?,
                license = ?, gui = ?
            WHERE id = ?
        ''', (
            name, plugin_type, description, version,
            author, supported_platform, dependencies,
            license_type, gui_type, plugin_id
        ))
        
        # 处理图标上传
        if 'icon_file' in request.files and request.files['icon_file'].filename:
            icon_file = request.files['icon_file']
            if icon_file.filename:
                icon_filename = f"{plugin['filename'].split('.')[0]}_{secure_filename(icon_file.filename)}"
                icon_path = os.path.join(app.config['ICON_FOLDER'], icon_filename)
                icon_file.save(icon_path)
                
                # 更新数据库中的图标路径
                cursor.execute('UPDATE plugins SET icon_path = ? WHERE id = ?', (icon_path, plugin_id))
        
        # 处理插件文件更新
        if 'plugin_file' in request.files and request.files['plugin_file'].filename:
            file = request.files['plugin_file']
            if file.filename and allowed_file(file.filename):
                # 删除旧文件
                old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], plugin['filename'])
                if os.path.exists(old_filepath):
                    os.remove(old_filepath)
                
                # 保存新文件
                original_filename = secure_filename(file.filename)
                filename = f"{hashlib.md5(f'{name}_{version}'.encode()).hexdigest()}_{original_filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # 计算新文件的大小和校验和
                file_size = os.path.getsize(filepath)
                checksum = calculate_checksum(filepath)
                
                # 更新数据库
                cursor.execute('''
                    UPDATE plugins SET 
                        filename = ?, original_filename = ?,
                        file_size = ?, checksum = ?
                    WHERE id = ?
                ''', (filename, original_filename, file_size, checksum, plugin_id))
        
        conn.commit()
        conn.close()
        
        # 更新 list.ini 文件
        if app.config['FTP_ENABLED']:
            ftp_manager.update_ini_file()
        
        # 重新获取插件信息
        plugin = db.get_plugin_by_id(plugin_id)
        return render_template('detail.html', plugin=plugin, success='插件信息已更新')
    
    return render_template('detail.html', plugin=plugin)

@app.route('/icon/<int:plugin_id>')
def get_plugin_icon(plugin_id):
    """获取插件图标"""
    plugin = db.get_plugin_by_id(plugin_id)
    if not plugin or not plugin.get('icon_path'):
        # 返回默认图标
        default_icon = os.path.join(app.config['ICON_FOLDER'], 'default.png')
        if os.path.exists(default_icon):
            return send_file(default_icon, mimetype='image/png')
        return '', 404
    
    icon_path = os.path.join(app.config['ICON_FOLDER'], os.path.basename(plugin['icon_path']))
    if os.path.exists(icon_path):
        return send_file(icon_path, mimetype='image/png')
    
    default_icon = os.path.join(app.config['ICON_FOLDER'], 'default.png')
    if os.path.exists(default_icon):
        return send_file(default_icon, mimetype='image/png')
    
    return '', 404

@app.route('/api/ftp/list')
def get_ftp_list():
    """获取 list.ini 文件内容（新增）"""
    if not app.config['FTP_ENABLED']:
        return jsonify({'error': 'FTP功能未启用'}), 400
    
    ini_content = ftp_manager.get_ini_content()
    return ini_content, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/ftp/list.ini')
def serve_list_ini():
    """提供 list.ini 文件下载（新增）"""
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