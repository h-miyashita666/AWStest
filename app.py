import os
from flask import Flask, request, render_template_string, redirect, make_response
import psycopg2
import datetime
import uuid

app = Flask(__name__)
DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# 起動時にテーブルを作成
def init_db():
    if DATABASE_URL:
      try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
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
    <title>24/7 メッセージ掲示板</title>
    <style>
        body { font-family: sans-serif; max-width: 500px; margin: 20px auto; padding: 10px; background: #8cabd9; }
        h1 { color: white; text-align: center; font-size: 20px; }
        .chat-box { display: flex; flex-direction: column; gap: 10px; margin-bottom: 80px; }
        .msg { max-width: 70%; padding: 10px 14px; border-radius: 15px; font-size: 14px; line-height: 1.4; word-break: break-all; }

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
	        <div class="msg {% if msg.usr_id == my_id %}my-msg{% else %}other-msg{% endif %}">
			{{ msg.content }}
		</div>
	{% else %}
		<div class="msg other-msg">まだメッセージはありません。送信してみましょう!</div>
	{% endfor %}
    </div>

   <div class="input-area">
	<form action="/add" method="POST">
            <input type="text" name="message" placeholder="メッセージを入力..." required>
            <button type="submit">送信</button>
        </form>
    </div>
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

@app.route('/add', methods=['POST'])
def add_message():
    init_db()
    #投稿者のCookieからIDを取得する
    my_id = request.cookies.get('user_id') or str(uuid.uuid4())

    msg = request.form.get('message')
    if msg and DATABASE_URL:
        #今の時間を年月日時分のカタチで取得、加えて9時間足して日本時間のJSTに
        DIFF_JST_FROM_UTC = 9
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=DIFF_JST_FROM_UTC)
        #メッセージ内容と時間とを結合させる
        msg_with_time = f"{msg} ({now})"

        conn = get_db_connection()
        cur = conn.cursor()

        #user_idも一緒にinsertする
        cur.execute('INSERT INTO messages (content, user_id) VALUES (%s, %s);', (msg_with_time, my_id))
        conn.commit()
        cur.close()
        conn.close()


    resp = make_response(redirect('/'))
    resp.set_cookie('user_id', my_id, max_age=60*60*24*365)
    return resp

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
