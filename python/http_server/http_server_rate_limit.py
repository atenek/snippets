import os
import json
import mimetypes
import time
import asyncio
import uvicorn
from urllib.parse import parse_qs
from datetime import datetime
from pathlib import Path
import socket
import logging
import sys

DEFAULT_ENCODING = 'utf-8'


# ALIAS, BG_COLOR, H1_COLOR = "RS0", "#F0E68C", "#FF8C00"
ALIAS, BG_COLOR, H1_COLOR  = "RS0", "#C09090", "#C01010"
# ALIAS, BG_COLOR, H1_COLOR = "RS1", "#90C090", "#10C010"
# ALIAS, BG_COLOR, H1_COLOR = "RS2", "#9090C0", "#1010C0"
# ALIAS, BG_COLOR, H1_COLOR = "RS3", "#F0E68C", "#FF8C00"

PORT = 62000

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Вывод в консоль
    ]
)

logger = logging.getLogger("asgi-server")

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("3.4.5.6", 80))
IP = s.getsockname()[0]
s.close()


class BandwidthLimiter:
    def __init__(self):
        self.connections = {}
        self.rates = {               # в байтах в секунду
            '1000К': 1024 * 1024,    # 1000 MB/s
            '100К': 100 * 1024,      # 100 KB/s по умолчанию
            '50K': 50 * 1024         # 50 KB/s
        }
        self.default_rate = self.rates.get('100К', 100 * 1024)


    def get_rate_for_client(self, client_ip, file_size=None, file_type=None):
        if file_size and file_size > 10 * 1024 * 1024:  # больше 10 MB
            return self.rates['50K']

        return self.rates['100К']

    def register_connection(self, connection_id, client_ip, rate=None):
        if rate is None:
            rate = self.get_rate_for_client(client_ip)

        self.connections[connection_id] = {
            'ip': client_ip,
            'rate': rate,
            'start_time': time.time(),
            'bytes_sent': 0,
            'last_check_time': time.time()
        }
        return connection_id

    def unregister_connection(self, connection_id):
        if connection_id in self.connections:
            del self.connections[connection_id]

    async def throttle(self, connection_id, chunk_size):
        if connection_id not in self.connections:
            return chunk_size

        conn = self.connections[connection_id]
        current_time = time.time()
        time_passed = current_time - conn['last_check_time']

        allowed_bytes = conn['rate'] * time_passed


        conn['bytes_sent'] += chunk_size
        conn['last_check_time'] = current_time

        if conn['bytes_sent'] > allowed_bytes:
            excess_bytes = conn['bytes_sent'] - allowed_bytes
            wait_time = excess_bytes / conn['rate']

            wait_time = min(wait_time, 1.0)

            if wait_time > 0.01:  # Ждем только если нужно ждать больше 10ms
                await asyncio.sleep(wait_time)

                conn['bytes_sent'] = 0
                conn['last_check_time'] = time.time()

        return chunk_size

    def get_connection_stats(self, connection_id):
        if connection_id in self.connections:
            conn = self.connections[connection_id]
            elapsed = time.time() - conn['start_time']
            if elapsed > 0:
                avg_rate = conn['bytes_sent'] / elapsed
                return {
                    'bytes_sent': conn['bytes_sent'],
                    'elapsed': round(elapsed, 2),
                    'avg_rate': round(avg_rate / 1024, 2),  # в KB/s
                    'current_rate': round(conn['rate'] / 1024, 2)  # в KB/s
                }
        return None

bandwidth_limiter = BandwidthLimiter()

class FileServer:
    def __init__(self, path: Path = "static"):
        self.files_dir = path
        self.connection_counter = 0


    def get_file_info(self, filepath):
        stat = os.stat(filepath)
        size = stat.st_size
        return {
            "name": os.path.basename(filepath),
            "size": size,
            "size_formatted": self.format_size(size),
            "size_category": self.get_size_category(size),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "type": mimetypes.guess_type(filepath)[0] or "application/octet-stream"
        }

    def get_size_category(self, size):
        if size < 1024 * 1024:  # < 1 MB
            return "small"
        elif size < 10 * 1024 * 1024:  # < 10 MB
            return "medium"
        else:
            return "large"

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def get_next_connection_id(self):
        self.connection_counter += 1
        return f"conn_{self.connection_counter}_{int(time.time())}"

    def list_files(self):
        files = []
        for filename in os.listdir(self.files_dir):
            filepath = os.path.join(self.files_dir, filename)
            if os.path.isfile(filepath):
                files.append(self.get_file_info(filepath))
        return files

file_server = FileServer(Path("static"))

async def app(scope, receive, send):
    assert scope['type'] == 'http'

    path = scope['path']
    method = scope['method']
    query_string = scope.get('query_string', b'').decode(DEFAULT_ENCODING)
    query_params = parse_qs(query_string)

    headers = dict(scope.get('headers', []))
    client_ip = headers.get(b'x-forwarded-for', b'').decode(DEFAULT_ENCODING) or scope.get('client', ['127.0.0.1'])[0]
    logger.info(f"Request from {client_ip}; headers: {headers}; query_params: {query_params}" )

    if path == '/':
        await handle_home(send, client_ip)

    elif path.startswith('/download/'):
        filename = path.replace('/download/', '')
        if 'rate' in query_params:
            try:
                custom_rate = int(query_params['rate'][0]) * 1024  # конвертируем KB/s в B/s
            except:
                custom_rate = None
        else:
            custom_rate = None
        await handle_download_with_limiter(send, receive, filename, client_ip, custom_rate)


    elif path == '/download' and 'file' in query_params:
        filename = query_params['file'][0]
        if 'rate' in query_params:
            try:
                custom_rate = int(query_params['rate'][0]) * 1024  # конвертируем KB/s в B/s
            except:
                custom_rate = None
        else:
            custom_rate = None
        await handle_download_with_limiter(send, receive, filename, client_ip, custom_rate)

    elif path == '/api/files':
        await send_json(send, {
            "files": file_server.list_files(),
            "rate_limits": {
                "100К": f"{bandwidth_limiter.rates['100К']/1024} KB/s",
                "50K": f"{bandwidth_limiter.rates['50K']/1024} KB/s",
                "1000К": f"{bandwidth_limiter.rates['1000К']/1024} KB/s"
            }
        })

    elif path == '/api/stats':
        stats = {}
        for conn_id in list(bandwidth_limiter.connections.keys())[:10]:  # показываем только последние 10
            conn_stats = bandwidth_limiter.get_connection_stats(conn_id)
            if conn_stats:
                stats[conn_id] = conn_stats
        await send_json(send, {
            "active_connections": len(bandwidth_limiter.connections),
            "connections": stats
        })

    elif path == '/api':
        await send_json(send, {
            "name": "File Server with Bandwidth Limiter",
            "version": "3.0",
            "encoding": DEFAULT_ENCODING,
            "rate_limits": {
                "100К": f"{bandwidth_limiter.rates['100К']/1024} KB/s",
                "50K": f"{bandwidth_limiter.rates['50K']/1024} KB/s",
                "1000К": f"{bandwidth_limiter.rates['1000К']/1024} KB/s"
            },
            "endpoints": [
                "/ - главная страница",
                "/download/ - скачивание файлов с ограничением скорости",
                "/download?file=filename&rate=100 - скачивание с указанием скорости (KB/s)",
                "/api/files - список файлов в JSON",
                "/api/stats - статистика соединений"
            ]
        })

    elif path == '/hc':
        await send_response(send, 200, 'text/plain; charset=utf-8', b'Ok')

    else:
        await send_response(send, 404, 'text/plain; charset=utf-8', b'Not Found')

async def handle_home(send, client_ip):
    files = file_server.list_files()

    files_html = ""
    for f in files:
        files_html += f'''
            <li>
                <div class="file-card">
                    <div class="file-header">
                        <span class="file-icon">📄</span>
                        <span class="file-name">{f['name']}</span>
                        <span class="file-size">({f['size_formatted']})</span>
                    </div>
                    <div class="file-controls">
                        <div class="download-buttons">
                            <a href="/download/{f['name']}?rate=50" class="btn btn-free">50 KB/s</a>
                            <a href="/download/{f['name']}?rate=100" class="btn btn-default">100 KB/s</a>
                            <a href="/download/{f['name']}?rate=1024" class="btn btn-1000К">1000 KB/s</a>
                        </div>
                        <div class="file-info">
                            <span>Тип: {f['type']}</span>
                            <span>Категория: {f['size_category']}</span>
                        </div>
                    </div>
                </div>
            </li>
        '''

    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <title>{ALIAS} {IP}</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; 
               background: linear-gradient(180deg, {BG_COLOR} 0%, #EEEEEE 60%); color: white; }}
        h1 {{ color: {H1_COLOR}; text-align: center; }}
        .container {{ background: rgba(255,255,255,0.95); border-radius: 10px; padding: 20px; 
                    box-shadow: 0 10px 30px rgba(0,0,0,0.2); color: #333; }}
        ul {{ list-style: none; padding: 0; }}
        li {{ margin: 20px 0; }}
        .file-card {{ background: #f8f9fa; border-radius: 8px; padding: 20px; 
                     border-left: 4px solid #667eea; }}
        .file-header {{ display: flex; align-items: center; margin-bottom: 15px; }}
        .file-icon {{ font-size: 24px; margin-right: 10px; }}
        .file-name {{ font-weight: bold; font-size: 18px; margin-right: 10px; }}
        .file-size {{ color: #666; }}
        .file-controls {{ display: flex; justify-content: space-between; align-items: center; 
                        flex-wrap: wrap; gap: 15px; }}
        .download-buttons {{ display: flex; gap: 10px; flex-wrap: wrap; }}
        .btn {{ padding: 10px 15px; border-radius: 5px; text-decoration: none; color: white;
               font-size: 14px; transition: transform 0.2s; }}
        .btn:hover {{ transform: translateY(-2px); }}
        .btn-free {{ background: #48c774; }}
        .btn-default {{ background: #3273dc; }}
        .btn-1000К {{ background: #ff3860; }}
        .file-info {{ color: #666; font-size: 14px; display: flex; gap: 15px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; 
                     background: #e9ecef; padding: 15px; border-radius: 8px; margin: 20px 0; }}
        .stat-item {{ text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #667eea; }}
        .stat-label {{ color: #666; font-size: 14px; }}
        .info-box {{ background: #e3f2fd; border-left: 4px solid #2196f3; padding: 15px; 
                    border-radius: 4px; margin: 20px 0; }}
        .info-box h3 {{ margin: 0 0 10px 0; color: #1976d2; }}
        .info-box code {{ background: #fff; padding: 2px 5px; border-radius: 3px; }}
        .info-box a {{ color: #1976d2; }}
    </style>
</head>
<body>
    <h1>{ALIAS} server {IP} with Bandwidth Limiter</h1>
    <div class="container">
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-value">{len(files)}</div>
                <div class="stat-label">Доступно файлов</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{len(bandwidth_limiter.connections)}</div>
                <div class="stat-label">Активных скачиваний</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{bandwidth_limiter.rates['100К']/1024} KB/s</div>
                <div class="stat-label">Скорость по умолчанию</div>
            </div>
        </div>
        
        <div class="info-box">
            <h3>Информация о rate-limiter</h3>
            <p>Скорость скачивания ограничена для каждого соединения:</p>
            <ul>
                <li><strong>50K:</strong> {bandwidth_limiter.rates['50K']/1024} KB/s</li>
                <li><strong>100К:</strong> {bandwidth_limiter.rates['100К']/1024} KB/s</li>
                <li><strong>1000К:</strong> {bandwidth_limiter.rates['1000К']/1024} KB/s</li>
            </ul>
            <p>Можно указать скорость в параметре: <code>/download/file.bin?rate=200</code> (200 KB/s)</p>
        </div>
        
        <h2>Доступные файлы</h2>
        <ul>
            {files_html}
        </ul>
        
        <div class="info-box">
            <h3>API endpoints</h3>
            <p><code><a href="/api/files" style="color: #1976d2;">/api/files</a></code> - список файлов в JSON</p>
            <p><code><a href="/api/stats" style="color: #1976d2;">/api/stats</a></code> - статистика активных соединений</p>
            <p><code>/download/file.bin?rate=XXX</code> - скачивание с указанной скоростью (KB/s)</p>
        </div>
    </div>
</body>
</html>'''

    await send_response(send, 200, 'text/html; charset=utf-8', html.encode(DEFAULT_ENCODING))

async def handle_download_with_limiter(send, receive, filename, client_ip, custom_rate=None):
    filepath = os.path.join(file_server.files_dir, filename)

    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        error_msg = f"File not found: {filename}".encode(DEFAULT_ENCODING)
        await send_response(send, 404, 'text/plain; charset=utf-8', error_msg)
        return


    file_size = os.path.getsize(filepath)
    content_type, _ = mimetypes.guess_type(filepath)
    if content_type is None:
        content_type = 'application/octet-stream'


    if content_type.startswith('text/'):
        content_type = f'{content_type}; charset={DEFAULT_ENCODING}'

    connection_id = file_server.get_next_connection_id()

    if custom_rate:
        rate = custom_rate
    else:
        rate = bandwidth_limiter.get_rate_for_client(client_ip, file_size, content_type)


    bandwidth_limiter.register_connection(connection_id, client_ip, rate)

    try:
        headers = [
            [b'content-type', content_type.encode(DEFAULT_ENCODING)],
            [b'content-disposition', f'attachment; filename="{filename}"'.encode(DEFAULT_ENCODING)],
            [b'content-length', str(file_size).encode(DEFAULT_ENCODING)],
            [b'x-rate-limit', f'{rate//1024} KB/s'.encode(DEFAULT_ENCODING)],
            [b'cache-control', b'no-cache'],
        ]

        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': headers,
        })

        chunk_size = 8192  # 8 KB chunks

        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break

                await bandwidth_limiter.throttle(connection_id, len(chunk))

                await send({
                    'type': 'http.response.body',
                    'body': chunk,
                    'more_body': True
                })

        await send({
            'type': 'http.response.body',
            'body': b'',
            'more_body': False
        })

    except Exception as e:
        error_msg = f"Error sending file: {str(e)}".encode(DEFAULT_ENCODING)
        print(error_msg.decode(DEFAULT_ENCODING))
    finally:
        bandwidth_limiter.unregister_connection(connection_id)

async def send_json(send, data):
    body = json.dumps(data, ensure_ascii=False, indent=2).encode(DEFAULT_ENCODING)
    await send_response(send, 200, 'application/json; charset=utf-8', body)

async def send_response(send, status, content_type, body):
    headers = [[b'content-type', content_type.encode(DEFAULT_ENCODING)]]
    await send({
        'type': 'http.response.start',
        'status': status,
        'headers': headers,
    })
    await send({
        'type': 'http.response.body',
        'body': body,
    })

if __name__ == "__main__":
    print("File Server with Bandwidth Limiter")
    print("=" * 60)
    print(f"Сервер: http://{IP}:{PORT}")
    print(f"Директория с файлами: ./{file_server.files_dir}/ ")
    print("\n Опции rate-limiter:")
    print(f"  - 50K: {bandwidth_limiter.rates['50K']/1024} KB/s")
    print(f"  - 100К: {bandwidth_limiter.rates['100К']/1024} KB/s")
    print(f"  - 1000К: {bandwidth_limiter.rates['1000К']/1024} KB/s")
    print("\n Примеры использования:")
    print(f"  - http://{IP}:{PORT}/ - главная страница")
    print(f"  - http://{IP}:{PORT}/download/medium_file.bin?rate=500 - скачать с 500 KB/s")
    print(f"  - http://{IP}:{PORT}/api/stats - статистика активных соединений")
    print("=" * 60)

    uvicorn.run(
        "http_server_rate_limit:app",
        host=IP,
        port=PORT,
        log_level="info" )

# DOWNLOAD_FILE='Maven.pdf'; curl -H "Host: CI223443434.ru" -o $DOWNLOAD_FILE http://10.77.152.112:62000/download/$DOWNLOAD_FILE?rate=50
# DOWNLOAD_FILE='git.pdf'; curl -H "Host: CI223443434.ru" -o $DOWNLOAD_FILE http://10.77.152.112:62000/download/$DOWNLOAD_FILE?rate=50

