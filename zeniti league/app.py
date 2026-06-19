import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os

app = Flask(__name__)
app.secret_key = 'zeniti_secret_key_2026'

# --- მონაცემთა ბაზასთან კავშირი (PostgreSQL) ---
def get_db_connection():
    db_url = os.environ.get('DATABASE_URL') or 'postgresql://zeniti_fantasy_db_user:L7axr98Dc4MNSs3Jr8iB5Y3W7YdeBJHE@dpg-d78577dm5p6s73eii93g-a.oregon-postgres.render.com/zeniti_fantasy_db'
    conn = psycopg2.connect(db_url)
    return conn

# --- 1. ფენტეზი ქულების დათვლის ლოგიკა ---
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

    # 1. მატჩში მონაწილეობა
    if player.get('played_match'): points += 1
    if player.get('played_second_half'): points += 1
    
    # 2. გოლები პოზიციების მიხედვით
    if 'მეკარე' in pos: points += goals * 8
    elif 'მცველი' in pos: points += goals * 7
    elif 'ნახევარმცველი' in pos: points += goals * 6
    elif 'თავდამსხმელი' in pos: points += goals * 5
    
    # 3. ბონუს გოლები
    points += outside_goals * 1
    points += own_half_goals * 3
    
    # 4. ასისტი, მოგება, პენალტები
    points += assists * 4
    if player.get('team_won'): points += 3
    points += pen_saved * 6
    points += pen_won * 3
    
    # 5. სეივები (ყოველ 4-ზე +1)
    points += (saves // 4)
    
    # 6. მშრალი კარი (Clean Sheet)
    if player.get('clean_sheet'):
        if 'მეკარე' in pos: points += 8
        elif 'მცველი' in pos: points += 6
        
    # 7. ჯარიმები (მინუსები)
    points -= yellow * 2
    points -= red * 4
    points -= own_goal * 4
    points -= pen_caused * 3
    
    # 8. გაშვებული გოლები (მეკარე და მცველი)
    if 'მეკარე' in pos and ga >= 4:
        points -= ((ga - 2) // 2) * 2
    
    if 'მცველი' in pos and ga >= 3:
        points -= (ga // 3)

    # 9. კაპიტანი (ორმაგი ქულა)
    if player.get('is_captain'):
        points *= 2
        
    return points

# 2. დამხმარე ფუნქცია კონკრეტული გუნდის მოთამაშეების წამოსაღებად
def get_team_players(team_name_in_db):
    conn = get_db_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM players WHERE real_team = %s", (team_name_in_db,))
        players_raw = cur.fetchall()
        
        players_list = []
        for p in players_raw:
            p_dict = dict(p)
            for field in ['goal', 'assist', 'saves', 'goals_against', 'yellow_card', 'red_card', 'own_goal', 'penalty_caused', 'penalty_saved', 'penalty_won', 'outside_box_goals', 'own_half_goals']:
                p_dict[field] = p_dict.get(field) or 0
            p_dict['total_points'] = calculate_fantasy_points(p_dict)
            players_list.append(p_dict)
        return players_list
    finally:
        cur.close()
        conn.close()

# --- 2. ავტორიზაცია ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        conn = get_db_connection()
        try:
            cur = conn.cursor()
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
        cur = conn.cursor(cursor_factory=RealDictCursor)
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

# --- 3. ფენტეზი გუნდის არჩევა (Pick Team) ---
@app.route('/pick-team', methods=['GET', 'POST'])
def pick_team():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    user_id = session['user_id']
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT budget, team_name FROM "Users" WHERE id = %s', (user_id,))
    user_data = cur.fetchone()
    
    if not user_data:
        cur.close()
        conn.close()
        return "მომხმარებელი ვერ მოიძებნა!"

    if request.method == 'POST':
        selected_ids = request.form.getlist('players')
        
        if len(selected_ids) != 11:
            cur.close()
            conn.close()
            flash("აირჩიეთ ზუსტად 11 მოთამაშე!")
            return redirect(url_for('pick_team'))

        placeholders = ', '.join(['%s'] * len(selected_ids))
        cur.execute(f'SELECT SUM(price) as total_cost FROM players WHERE id IN ({placeholders})', selected_ids)
        cost_row = cur.fetchone()
        total_cost = cost_row['total_cost'] or 0

        if total_cost > user_data['budget']:
            cur.close()
            conn.close()
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

    # --- GET რეჟიმი ---
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
        for field in ['goal', 'assist', 'saves', 'yellow_card', 'red_card']:
            p_dict[field] = p_dict.get(field) or 0
        p_dict['total_points'] = calculate_fantasy_points(p_dict)
        total_team_points += p_dict['total_points']
        my_team_list.append(p_dict)
        saved_player_ids.append(p_dict['id'])

    cur.execute('SELECT * FROM players ORDER BY price DESC')
    players_raw = cur.fetchall()
    players_market = []
    for p in players_raw:
        p_dict = dict(p)
        for field in ['goal', 'assist', 'saves', 'yellow_card', 'red_card']:
            p_dict[field] = p_dict.get(field) or 0
        
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

# --- 4. დინამიური გვერდები ---
@app.route('/')
def home():
    return render_template('index.html', username=session.get('username'))

@app.route('/teams')
def teams():
    return render_template('teams.html')

@app.route('/playoffs')
def playoffs():
    return render_template('playoffs.html')

# --- 8 გუნდის ინდივიდუალური გვერდები ---
@app.route('/centri')
def centri():
    players = get_team_players('ცენტრი')
    return render_template('centri.html', players=players)

@app.route('/phoenix')
def phoenix():
    players = get_team_players('ფენიქსი')
    return render_template('phoenix.html', players=players)

@app.route('/ghele')
def ghele():
    players = get_team_players('ღელე')
    return render_template('ghele.html', players=players)

@app.route('/leghva')
def leghva():
    players = get_team_players('ლეღვა')
    return render_template('leghva.html', players=players)

@app.route('/la-legends')
def la_legends():
    players = get_team_players('La legends')
    return render_template('la_legends.html', players=players)

@app.route('/tsqavroka')
def tsqavroka():
    players = get_team_players('წყავროკა')
    return render_template('tsqavroka.html', players=players)

@app.route('/jikhanjuri')
def jikhanjuri():
    players = get_team_players('ჯიხანჯური')
    return render_template('jikhanjuri.html', players=players)

@app.route('/atchqvistavi')
def atchqvistavi():
    players = get_team_players('აჭყვისთავი')
    return render_template('atchqvistavi.html', players=players)

@app.route('/leaderboard')
def leaderboard():
    return render_template('index.html')

@app.route('/support')
def support():
    return render_template('support.html')

if __name__ == '__main__':
    app.run(debug=True)
