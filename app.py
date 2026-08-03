import os
from flask import Flask, request, render_template_string, redirect
import psycopg2

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
                content TEXT NOT NULL
            );
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
        body { font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; background: #f4f6f8; }
        h1 { color: #333; text-align: center; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; }
        input[type="text"] { width: 75%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; }
        button { width: 20%; padding: 10px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer; }
        ul { list-style: none; padding: 0; }
        li { background: white; padding: 12px; margin-bottom: 8px; border-radius: 4px; border-left: 4px solid #007bff; }
    </style>
</head>
<body>
    <h1>🚀 24時間メッセージ掲示板</h1>
    <div class="card">
        <form action="/add" method="POST">
            <input type="text" name="message" placeholder="メッセージを入力..." required>
            <button type="submit">送信</button>
        </form>
    </div>
    <h2>投稿一覧</h2>
    <ul>
        {% for msg in messages %}
            <li>{{ msg }}</li>
        {% else %}
            <li>まだ投稿はありません。最初のメッセージを書いてみましょう！</li>
        {% endfor %}
    </ul>
</body>
</html>
'''

@app.route('/')
def index():
    # ページが開かれた時テーブルがなければ自動作成する
    init_db()
    messages = []
    if DATABASE_URL:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT content FROM messages ORDER BY id DESC;')
            messages = [row[0] for row in cur.fetchall()]
            cur.close()
            conn.close()
        except Exception as e:
            messages = [f"DBエラー: {e}"]
    return render_template_string(HTML_TEMPLATE, messages=messages)

@app.route('/add', methods=['POST'])
def add_message():
    init_db()
    msg = request.form.get('message')
    if msg and DATABASE_URL:
        #今の時間を年月日時分のカタチで取得、加えて9時間足して日本時間のJSTに
        jst_time = datetime.datetime,now(datetime.timezone.utc) + datetime.timedelta(hours=9)
        now_str = jst_time.strftime('%y-%m-%d %H:%M')

        #メッセージ内容と時間とを結合させる
        msg_with_time = f"{msg} ({now_str})"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO messages (content) VALUES (%s);', (msg_with_time,))
        conn.commit()
        cur.close()
        conn.close()
    return redirect('/')

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080)
