import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import json

app = Flask(__name__)
app.secret_key = 'zeniti_secret_key_2026'

# --- მონაცემთა ბაზასთან კავშირი (PostgreSQL) ---
def get_db_connection():
    # პირველ რიგში ამოწმებს Render-ის გარემოს ცვლადს, თუ არადა იყენებს შენს External URL-ს
    db_url = os.environ.get('DATABASE_URL') or 'postgresql://zeniti_fantasy_db_user:jzZEzwqtNLOkev8AFuY4Q70gv0ogPho4@dpg-d8qj28e8bjmc738pm37g-a.oregon-postgres.render.com/zeniti_fantasy_db_s49c'
    
    # Render-ის ბაზას სჭირდება sslmode='require' გარე კავშირებისთვის
    if "render.com" in db_url and "sslmode" not in db_url:
        if "?" in db_url:
            db_url += "&sslmode=require"
        else:
            db_url += "?sslmode=require"
            
    conn = psycopg2.connect(db_url, cursor_factory=DictCursor)
    return conn

# --- ბაზის ცხრილების ავტომატური შექმნა ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 1. Users ცხრილი
    cur.execute('''
        CREATE TABLE IF NOT EXISTS "Users" (
            id SERIAL PRIMARY KEY,
            username VARCHAR(80) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            budget NUMERIC(5,1) DEFAULT 100.0,
            team_name VARCHAR(100)
        );
    ''')
    
    # 2. Players ცხრილი
    cur.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            position VARCHAR(50) NOT NULL,
            price NUMERIC(4,1) NOT NULL,
            real_team VARCHAR(100) NOT NULL,
            shirt_number INT,
            goal INT DEFAULT 0,
            assist INT DEFAULT 0,
            saves INT DEFAULT 0,
            goals_against INT DEFAULT 0,
            yellow_card INT DEFAULT 0,
            red_card INT DEFAULT 0,
            own_goal INT DEFAULT 0,
            penalty_caused INT DEFAULT 0,
            penalty_saved INT DEFAULT 0,
            penalty_won INT DEFAULT 0,
            outside_box_goals INT DEFAULT 0,
            own_half_goals INT DEFAULT 0,
            played_match BOOLEAN DEFAULT FALSE,
            played_second_half BOOLEAN DEFAULT FALSE,
            team_won BOOLEAN DEFAULT FALSE,
            clean_sheet BOOLEAN DEFAULT FALSE,
            is_captain BOOLEAN DEFAULT FALSE
        );
    ''')
    
    # 3. User Teams ცხრილი (კავშირი მომხმარებელსა და მოთამაშეებს შორის)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_teams (
            id SERIAL PRIMARY KEY,
            user_id INT REFERENCES "Users"(id) ON DELETE CASCADE,
            player_id INT REFERENCES players(id) ON DELETE CASCADE
        );
    ''')
    
    conn.commit()
    cur.close()
    conn.close()

# გაეშვას ცხრილების შექმნა პროექტის სტარტზე
init_db()

# --- ფენტეზი ქულების დათვლის ლოგიკა ---
def calculate_fantasy_points(player):
    points = 0
    pos = str(player.get('position') or '')
    goals = player.get('goal') or 0
    assists = player.get('assist') or 0
    saves = player.get('saves') or 0
    ga = player.get('goals_against') or 0
    yellow = player.get('yellow_card') or 0
    red = player.get('red_card') or 0
    own_goal = player.get('own_goal') or 0
    pen_caused = player.get('penalty_caused') or 0
    pen_saved = player.get('penalty_saved') or 0
    pen_won = player.get('penalty_won') or 0
    outside_goals = player.get('outside_box_goals') or 0
    own_half_goals = player.get('own_half_goals') or 0

    if player.get('played_match'): points += 1
    if player.get('played_second_half'): points += 1
    
    if 'მეკარე' in pos: points += goals * 8
    elif 'მცველი' in pos: points += goals * 7
    elif 'ნახევარმცველი' in pos: points += goals * 6
    elif 'თავდამსხმელი' in pos: points += goals * 5
    
    points += outside_goals * 1
    points += own_half_goals * 3
    points += assists * 4
    if player.get('team_won'): points += 3
    points += pen_saved * 6
    points += pen_won * 3
    points += (saves // 4)
    
    if player.get('clean_sheet'):
        if 'მეკარე' in pos: points += 8
        elif 'მცველი' in pos: points += 6
        
    points -= yellow * 2
    points -= red * 4
    points -= own_goal * 4
    points -= pen_caused * 3
    
    if 'მეკარე' in pos and ga >= 4:
        points -= ((ga - 2) // 2) * 2
    if 'მცველი' in pos and ga >= 3:
        points -= (ga // 3)

    if player.get('is_captain'):
        points *= 2
        
    return points

def get_team_players(team_name_in_db):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # PostgreSQL-ისთვის გვჭირდება %s და არა ?
        cur.execute("SELECT * FROM players WHERE real_team = %s", (team_name_in_db,))
        players_raw = cur.fetchall()
        players_list = []
        for p in players_raw:
            p_dict = dict(p)
            p_dict['total_points'] = calculate_fantasy_points(p_dict)
            players_list.append(p_dict)
        return players_list
    finally:
        cur.close()
        conn.close()

# --- ავტორიზაცია ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute('INSERT INTO "Users" (username, password, budget) VALUES (%s, %s, %s)',
                         (username, hashed_pw, 100.0))
            conn.commit()
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.rollback()
            return "ეს სახელი უკვე დაკავებულია!"
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM "Users" WHERE username = %s', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect(url_for('home'))
        return "არასწორი მონაცემები!"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- ფენტეზი გუნდის არჩევა ---
@app.route('/pick-team', methods=['GET', 'POST'])
def pick_team():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    cur = conn.cursor()
    user_id = session['user_id']
    
    cur.execute('SELECT budget, team_name FROM "Users" WHERE id = %s', (user_id,))
    user_data = cur.fetchone()
    
    if not user_data:
        cur.close()
        conn.close()
        return "მომხმარებელი ვერ მოიძებნა!"

    if request.method == 'POST':
        selected_ids = request.form.getlist('players')
        
        if len(selected_ids) != 11:
            flash("აირჩიეთ ზუსტად 11 მოთამაშე!")
            return redirect(url_for('pick_team'))

        selected_ids = [int(i) for i in selected_ids]
        cur.execute('SELECT SUM(price) as total_cost FROM players WHERE id = ANY(%s)', (selected_ids,))
        cost_row = cur.fetchone()
        total_cost = cost_row['total_cost'] or 0

        if total_cost > user_data['budget']:
            flash(f"არ გაქვთ საკმარისი ბიუჯეტი! საჭიროა: {total_cost}M, გაქვთ: {user_data['budget']}M")
            return redirect(url_for('pick_team'))

        cur.execute('DELETE FROM user_teams WHERE user_id = %s', (user_id,))
        for p_id in selected_ids:
            cur.execute('INSERT INTO user_teams (user_id, player_id) VALUES (%s, %s)', (user_id, p_id))
        
        conn.commit()
        cur.close()
        conn.close()
        flash("გუნდი წარმატებით დაკომპლექტდა!")
        return redirect(url_for('home'))

    cur.execute('''
        SELECT p.* FROM players p
        JOIN user_teams ut ON p.id = ut.player_id
        WHERE ut.user_id = %s
    ''', (user_id,))
    user_team_raw = cur.fetchall()

    my_team_list = []
    total_team_points = 0
    saved_player_ids = []

    for p in user_team_raw:
        p_dict = dict(p)
        p_dict['total_points'] = calculate_fantasy_points(p_dict)
        total_team_points += p_dict['total_points']
        my_team_list.append(p_dict)
        saved_player_ids.append(p_dict['id'])

    cur.execute('SELECT * FROM players ORDER BY price DESC')
    players_raw = cur.fetchall()
    players_market = []
    for p in players_raw:
        p_dict = dict(p)
        players_market.append({
            'id': p_dict['id'],
            'name': p_dict['name'],
            'position': p_dict['position'],
            'price': float(p_dict['price'] or 0), 
            'real_team': p_dict['real_team'],
            'goal': p_dict['goal'],
            'assist': p_dict['assist'],
            'total_points': calculate_fantasy_points(p_dict)
        })
    
    cur.close()
    conn.close()
    
    return render_template('pick_team.html', 
                           my_team=my_team_list, 
                           total_points=total_team_points,
                           team_name=user_data['team_name'] if user_data['team_name'] else "ჩემი გუნდი",
                           players_json=json.dumps(players_market), 
                           saved_players=saved_player_ids, 
                           budget=user_data['budget'])

# --- როუტები ---
@app.route('/')
def home():
    return render_template('index.html', username=session.get('username'))

@app.route('/teams')
def teams():
    return render_template('teams.html')

@app.route('/playoffs')
def playoffs():
    return render_template('playoffs.html')

@app.route('/centri')
def centri():
    return render_template('centri.html', players=get_team_players('ცენტრი'))

@app.route('/phoenix')
def phoenix():
    return render_template('phoenix.html', players=get_team_players('ფენიქსი'))

@app.route('/ghele')
def ghele():
    return render_template('ghele.html', players=get_team_players('ღელე'))

@app.route('/leghva')
def leghva():
    return render_template('leghva.html', players=get_team_players('ლეღვა'))

@app.route('/tsqavroka')
def tsqavroka():
    return render_template('tsqavroka.html', players=get_team_players('წყავროკა'))

@app.route('/la_legends')
def la_legends():
    return render_template('la_legends.html', players=get_team_players('La legends'))

@app.route('/jikhanjuri')
def jikhanjuri():
    return render_template('jikhanjuri.html', players=get_team_players('ჯიხანჯური'))

@app.route('/atchqvistavi')
def atchqvistavi():
    return render_template('atchqvistavi.html', players=get_team_players('აჭყვისთავი'))

@app.route('/leaderboard')
def leaderboard():
    return render_template('index.html')

@app.route('/support')
def support():
    return render_template('support.html')

if __name__ == '__main__':
    app.run(debug=True)
