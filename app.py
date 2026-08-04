import os
from flask import Flask, request, render_template_string, redirect, make_response
import psycopg2
import datetime
import uuid
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# 起動時にテーブルを作成
def init_db():
    if DATABASE_URL:
      try:
        conn = get_db_connection()
        cur = conn.cursor()

        # ↓★★ 内容を消すときはこの行を使う ★★
        cur.execute('TRUNCATE TABLE messages RESTART IDENTITY;')

        cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL
            );
        ''')
        #user_idカラムを強制的に追加する
        cur.execute('''
            ALTER TABLE messages ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'legacy';
        ''')

        conn.commit()
        cur.close()
        conn.close()
      except Exception as e:
        print(f"Init DB Error: {e}")

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>

    <title>24/7 メッセージ掲示板</title>
    <style>
        /* 1メッセージ全体のグループ */
        .msg-container { display: flex; flex-direction: column; max-width: 70%; }
        .my-container { align-self: flex-end; align-items: flex-end; }
        .other-container { align-self: flex-start; align-items: flex-start; }

        /* 吹き出し本体 */
        .msg { padding: 10px 14px; border-radius: 15px; font-size: 14px; line-height: 1.4; word-break: break-all; }
        .my-msg { background: #85e249; color: #000; border-bottom-right-radius: 2px; }
        .other-msg { background: #ffffff; color: #000; border-bottom-left-radius: 2px; }

        /* 吹き出しの外下の時間 */
        .time { font-size: 10px; color: #f0f0f0; margin-top: 2px; padding: 0 4px; }


        body { font-family: sans-serif; max-width: 500px; margin: 20px auto; padding: 10px; background: #8cabd9; }
        h1 { color: white; text-align: center; font-size: 20px; }
        .chat-box { display: flex; flex-direction: column; gap: 10px; margin-bottom: 80px; }

        /* 自分の投稿（右側・緑色） */
        .my-msg { align-self: flex-end; background: #85e249; color: #000; border-bottom-right-radius: 2px; }
        /* 他人の投稿（左側・白色） */
        .other-msg { align-self: flex-start; background: #ffffff; color: #000; border-bottom-left-radius: 2px; }

        .input-area { position: fixed; bottom: 0; left: 0; right: 0; background: white; padding: 10px; display: flex; justify-content: center; }
        .input-area form { width: 100%; max-width: 500px; display: flex; gap: 8px; }
        input[type="text"] { flex: 1; padding: 10px; border: 1px solid #ccc; border-radius: 20px; outline: none; }
        button { padding: 10px 18px; background: #007bff; color: white; border: none; border-radius: 20px; cursor: pointer; font-weight: bold; }
    </style>
</head>
<body>
    <h1>🚀 チャットルーム</h1>
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
// python(jinja2)から自分のuser_idをJSに受け取る
  const myId = "{{ my_id }}";

// サーバーとwebsocket接続を確立
  const socket = io();

// Jinja2(python)から自身のmy_idをjavascript変数として受け取る
  const input = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const chatBox = document.querySelector('.chat-box');

// メッセージ送信処理
  function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    
    // 日本時間の時分を作成
    const now = new Date();
    const hours = String(now.getHours()).padStart(2,'0');
    const minutes = String(now.getMinutes()).padStart(2,'0');
    const timeStr = `${hours}:${minutes}`;
    
    // 本文 ||| 時刻のフォーマットに作成
    const fullContent = `${text} ||| ${timeStr}`;
    
    // サーバーへwebsocketでメッセージ送信
    socket.emit('send_message',{
      content: fullContent,
      user_id: myId
      }
    );
    
    // 入力欄をクリア
    input.value = '';
}


// 送信ボタンクリックorEnterキーで送信
sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keypress', (e) => {
  if (e.key === 'Enter') sendMessage();
  }
);

// サーバーから新着メッセージが届いた時の処理
socket.on('receive_message', (data) => {
  const parts = data.content.split('|||');
  const text = parts[0];
  const time = parts[1] || '';

  // 自分が送ったか他人か判定
  const isMyMsg = (data.user_id === myId);

  // 新しい吹き出しHTMLの要素を作成
  const container = document.createElement('div');
  container.className = `msg-container ${isMyMsg ? 'my-container' : 'other-container'}`;
       let html = `<div class="msg ${isMyMsg ? 'my-msg' : 'other-msg'}">${text}</div>`;
        if (time) {
          html += `<span class="time">${time}</span>`;
        }
       container.innerHTML = html;

  // 画面のチャットエリアに追加
  chatBox.appendChild(container);

  // 一番下まで自動スクロール
  window.scrollTo(0, document.body.scrollHeight);
});

// 2000ミリ秒ごとにページの自動更新
//  setInterval(() => {
//      window.location.reload();
//    }, 2000);
</script>


</body>
</html>
'''

@app.route('/')
def index():
    # ページが開かれた時テーブルがなければ自動作成する
    init_db()
    # cookieからmy_idを取得。なければ新しく生成する
    my_id = request.cookies.get('user_id')
    if not my_id:
        my_id = str(uuid.uuid4())

    messages = []
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # contentとuser_idの両方を取得。古い順に並べる
            cur.execute('SELECT content, user_id FROM messages ORDER BY id ASC;')
            messages = [{'content': row[0], 'user_id': row[1]} for row in cur.fetchall()]
            cur.close()
            conn.close()
        except Exception as e:
            messages = [{'content': f"DBエラー: {e}", 'user_id': ''}]
    resp = make_response(render_template_string(HTML_TEMPLATE, messages=messages, my_id=my_id))
    resp.set_cookie('user_id',my_id,max_age=60*60*24*365)
    return resp


#@app.route('/add', methods=['POST'])
#def add_message():
#    init_db()
#    #投稿者のCookieからIDを取得する
#    my_id = request.cookies.get('user_id') or str(uuid.uuid4())
#
#    msg = request.form.get('message')
#    if msg and DATABASE_URL:
#        #今の時間を年月日時分のカタチで取得、加えて9時間足して日本時間のJSTに
#        DIFF_JST_FROM_UTC = 9
#        now = (datetime.datetime.utcnow() + datetime.timedelta(hours=DIFF_JST_FROM_UTC)).strftime('%H:%M')
#        #メッセージ内容と時間とを結合させる。あとでCSSで整える
#        msg_with_time = f"{msg} ||| {now}"
#
#        conn = get_db_connection()
#        cur = conn.cursor()
#
#        #user_idも一緒にinsertする
#        cur.execute('INSERT INTO messages (content, user_id) VALUES (%s, %s);', (msg_with_time, my_id))
#        conn.commit()
#        cur.close()
#        conn.close()
#
#
#    resp = make_response(redirect('/'))
#    resp.set_cookie('user_id', my_id, max_age=60*60*24*365)
#    return resp

# ----------------------------------------------------
# WebSocket: メッセージ受信・一斉送信処理
# ----------------------------------------------------
@socketio.on('send_message')
def handle_send_message(data):
    content = data.get('content')
    user_id = data.get('user_id')

    if not content or not user_id:
        return

    # 1. DBにメッセージを保存
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO messages (content, user_id) VALUES (%s, %s);', (content, user_id))
    conn.commit()
    cur.close()
    conn.close()

    # 2. 接続中の全員に「新着メッセージだよ！」と送る（broadcast=True）
    emit('receive_message', {
        'content': content,
        'user_id': user_id
    }, broadcast=True)


if __name__ == '__main__':
    init_db()
# LINEみたいにする→app.runではなく、socketio.runを使う
#    app.run(host='0.0.0.0', port=8080)
    socketio.run(app, host='0.0.0.0', port=8080)