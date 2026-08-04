import os
import datetime
from flask import Flask, request, render_template_string, redirect, url_for, flash
import psycopg2
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

app = Flask(__name__)
# Flask-Loginのセッション暗号化用キー
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-12345')

# Flask-Loginのセットアップ
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # 未ログイン時にリダイレクトされるルート名

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# --- Userモデルとセッション管理 ---
class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

@login_manager.user_loader
def load_user(user_id):
    if not DATABASE_URL:
        return None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash FROM users WHERE id = %s;", (int(user_id),))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            return User(id=str(row[0]), username=row[1], password_hash=row[2])
    except Exception as e:
        print(f"Load User Error: {e}")
    return None

# --- データベース初期化 ---
def init_db():
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # 1. users テーブルの作成
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(256) NOT NULL
                );
            """)

            # 2. messages テーブルの作成
            cur.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    content TEXT NOT NULL,
                    user_id TEXT NOT NULL DEFAULT 'legacy'
                );
            ''')

            conn.commit()
            cur.close()
            conn.close()
            print("DB Initialized Successfully!")
        except Exception as e:
            print(f"Init DB Error: {e}")

# --- HTML テンプレート (ログイン・会員登録用) ---
LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8"><title>ログイン</title>
    <style>
        body { font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; }
        input { width: 100%; padding: 10px; margin: 8px 0; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #28a745; color: white; border: none; cursor: pointer; }
        .link { margin-top: 15px; text-align: center; }
    </style>
</head>
<body>
    <h2>🔐 ログイン</h2>
    <form method="POST">
        <input type="text" name="username" placeholder="ユーザー名" required>
        <input type="password" name="password" placeholder="パスワード" required>
        <button type="submit">ログイン</button>
    </form>
    <div class="link"><a href="/register">アカウント新規作成はこちら</a></div>
</body>
</html>
'''

REGISTER_HTML = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8"><title>会員登録</title>
    <style>
        body { font-family: sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; }
        input { width: 100%; padding: 10px; margin: 8px 0; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #007bff; color: white; border: none; cursor: pointer; }
        .link { margin-top: 15px; text-align: center; }
    </style>
</head>
<body>
    <h2>📝 会員登録</h2>
    <form method="POST">
        <input type="text" name="username" placeholder="ユーザー名" required>
        <input type="password" name="password" placeholder="パスワード" required>
        <button type="submit">登録する</button>
    </form>
    <div class="link"><a href="/login">ログイン画面へ戻る</a></div>
</body>
</html>
'''

CHAT_HTML = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
    <title>24/7 メッセージ掲示板</title>
    <style>
        .msg-container { display: flex; flex-direction: column; max-width: 70%; }
        .my-container { align-self: flex-end; align-items: flex-end; }
        .other-container { align-self: flex-start; align-items: flex-start; }
        .msg { padding: 10px 14px; border-radius: 15px; font-size: 14px; line-height: 1.4; word-break: break-all; }
        .my-msg { background: #85e249; color: #000; border-bottom-right-radius: 2px; }
        .other-msg { background: #ffffff; color: #000; border-bottom-left-radius: 2px; }
        .time { font-size: 10px; color: #f0f0f0; margin-top: 2px; padding: 0 4px; }
        body { font-family: sans-serif; max-width: 500px; margin: 20px auto; padding: 10px; background: #8cabd9; }
        .header { display: flex; justify-content: space-between; align-items: center; color: white; }
        .header a { color: #ffdddd; text-decoration: none; font-size: 14px; }
        .chat-box { display: flex; flex-direction: column; gap: 10px; margin-bottom: 80px; }
        .input-area { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 10px; display: flex; justify-content: center; }
        .input-area form { width: 100%; max-width: 500px; display: flex; gap: 8px; }
        input[type="text"] { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 20px; outline: none; }
        button { padding: 10px 18px; background: #007bff; color: white; border: none; border-radius: 20px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 チャットルーム</h1>
        <div>
            <span>👤 {{ current_user.username }}</span> | 
            <a href="/logout">ログアウト</a>
        </div>
    </div>

    <div class="chat-box">
	{% for msg in messages %}
            {% set parts = msg.content.split('|||') %}
            <div class="msg-container {% if msg.user_id == my_id %}my-container{% else %}other-container{% endif %}">
                <div class="msg {% if msg.user_id == my_id %}my-msg{% else %}other-msg{% endif %}">
                    {{ parts[0] }}
                </div>
                {% if parts|length > 1 %}
                    <span class="time">{{ parts[1] }}</span>
                {% endif %}
            </div>
	{% else %}
            <div class="msg other-msg">まだメッセージはありません。送信してみましょう!</div>
	{% endfor %}
    </div>

    <div class="input-area">
      <div style="width: 100%; max-width: 500px; display: flex; gap: 8px;">
        <input type="text" id="message-input" placeholder="メッセージを入力...">
        <button type="button" id="send-btn">送信</button>
      </div>
    </div>

<script>
  const myId = "{{ my_id }}";
  const socket = io();

  const input = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const chatBox = document.querySelector('.chat-box');

  function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    
    const now = new Date();
    const hours = String(now.getHours()).padStart(2,'0');
    const minutes = String(now.getMinutes()).padStart(2,'0');
    const timeStr = `${hours}:${minutes}`;
    
    const fullContent = `${text} ||| ${timeStr}`;
    
    socket.emit('send_message', {
      content: fullContent,
      user_id: myId
    });
    
    input.value = '';
  }

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendMessage();
  });

  socket.on('receive_message', (data) => {
    const parts = data.content.split('|||');
    const text = parts[0];
    const time = parts[1] || '';

    const isMyMsg = (data.user_id === myId);

    const container = document.createElement('div');
    container.className = `msg-container ${isMyMsg ? 'my-container' : 'other-container'}`;

    const msgDiv = document.createElement('div');
    msgDiv.className = `msg ${isMyMsg ? 'my-msg' : 'other-msg'}`;
    msgDiv.textContent = text; 

    container.appendChild(msgDiv);

    if (time) {
      const timeSpan = document.createElement('span');
      timeSpan.className = 'time';
      timeSpan.textContent = time;
      container.appendChild(timeSpan);
    }

    chatBox.appendChild(container);
    window.scrollTo(0, document.body.scrollHeight);
  });
</script>
</body>
</html>
'''

# --- 画面のルーティング ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        hashed_pw = generate_password_hash(password)

        if DATABASE_URL:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s);", (username, hashed_pw))
                conn.commit()
                cur.close()
                conn.close()
                return redirect(url_for('login'))
            except Exception as e:
                return f"登録エラー: 既に存在するユーザー名です ({e})"
    return render_template_string(REGISTER_HTML)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if DATABASE_URL:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id, username, password_hash FROM users WHERE username = %s;", (username,))
            row = cur.fetchone()
            cur.close()
            conn.close()

            if row and check_password_hash(row[2], password):
                user = User(id=str(row[0]), username=row[1], password_hash=row[2])
                login_user(user)
                return redirect(url_for('index'))
            else:
                return "ユーザー名またはパスワードが間違っています。"
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required  # 未ログインなら自動で /login へ飛ぶ
def index():
    init_db()
    # ユーザー固有IDとしてログイン中の user.id を利用
    my_id = str(current_user.id)

    messages = []
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT content, user_id FROM messages ORDER BY id ASC;')
            messages = [{'content': row[0], 'user_id': row[1]} for row in cur.fetchall()]
            cur.close()
            conn.close()
        except Exception as e:
            messages = [{'content': f"DBエラー: {e}", 'user_id': ''}]
            
    return render_template_string(CHAT_HTML, messages=messages, my_id=my_id, current_user=current_user)

# --- WebSocket リアルタイム通信 ---

@socketio.on('connect')
def handle_connect():
    if not current_user.is_authenticated:
        return False  # 未ログインユーザーのリアルタイム接続を拒否

@socketio.on('send_message')
def handle_send_message(data):
    if not current_user.is_authenticated:
        return

    content = data.get('content')
    # ユーザー識別用IDはクライアントからではなくサーバーの current_user.id を使用（なりすまし防止）
    user_id = str(current_user.id)

    if not content:
        return

    # 1. DBにメッセージを保存
    if DATABASE_URL:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO messages (content, user_id) VALUES (%s, %s);', (content, user_id))
        conn.commit()
        cur.close()
        conn.close()

    # 2. 全員に配信
    emit('receive_message', {
        'content': content,
        'user_id': user_id
    }, broadcast=True)

if __name__ == '__main__':
    init_db()
    socketio.run(app, host='0.0.0.0', port=8080)