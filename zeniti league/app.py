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

    # 🔄 ვკითხულობთ ახალი ციფრული სვეტებიდან (თუ ცარიელია, ვიყენებთ ძველ სვეტებს უსაფრთხოებისთვის)
    played_m = player.get('played_match_count') if player.get('played_match_count') is not None else player.get('played_match')
    played_sh = player.get('played_second_half_count') if player.get('played_second_half_count') is not None else player.get('played_second_half')
    team_w = player.get('team_won_count') if player.get('team_won_count') is not None else player.get('team_won')
    cs_count = player.get('clean_sheet_count') if player.get('clean_sheet_count') is not None else player.get('clean_sheet')

    # ბულიანების ციფრებში გადაყვანა (თუ ძველი ჩანაწერი დაგვხვდა)
    if isinstance(played_m, bool): played_m = 1 if played_m else 0
    if isinstance(played_sh, bool): played_sh = 1 if played_sh else 0
    if isinstance(team_w, bool): team_w = 3 if team_w else 0
    if isinstance(cs_count, bool): cs_count = 1 if cs_count else 0

    # ქულების დარიცხვა მატჩებზე
    points += played_m * 1
    points += played_sh * 1
    
    # თუ team_w უკვე ქულაა (ანუ ბულიანიდან გადავიდა), პირდაპირ ვუმატებთ, თუ ახალი ციფრია, ვამრავლებთ 3-ზე
    if player.get('team_won_count') is not None:
        points += team_w * 3
    else:
        points += team_w
    
    # გოლების დათვლა პოზიციების მიხედვით
    if 'მეკარე' in pos: points += goals * 8
    elif 'მცველი' in pos: points += goals * 7
    elif 'ნახევარმცველი' in pos: points += goals * 6
    elif 'თავდამსხმელი' in pos: points += goals * 5
    
    points += outside_goals * 1
    points += own_half_goals * 3
    points += assists * 4
    points += pen_saved * 6
    points += pen_won * 3
    points += (saves // 4)
    
    # 🔄 მშრალი მატჩების დაგროვებითი დათვლა
    if cs_count > 0:
        if 'მეკარე' in pos: points += cs_count * 8
        elif 'მცველი' in pos: points += cs_count * 6
        
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

# --- დამხმარე ფუნქცია გუნდის მოთამაშეების წამოსაღებად ბაზიდან ---
def get_team_players(team_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE real_team = %s", (team_name,))
    raw_players = cur.fetchall()
    cur.close()
    conn.close()
    
    players = []
    for p in raw_players:
        p_dict = dict(p)
        p_dict['total_points'] = calculate_fantasy_points(p_dict)
        players.append(p_dict)
    return players

# ==========================================
# 🏠 ძირითადი მარშრუტები (Routes)
# ==========================================

@app.route('/')
def home():
    return render_template('index.html', username=session.get('username'))

@app.route('/teams')
def teams():
    return render_template('teams.html')

@app.route('/playoffs')
def playoffs():
    return render_template('playoffs.html')

# 🔄 შეცვლილია: ძველი 'centri' როუტის ნაცვლად ახლა არის თეთროსანი
@app.route('/tetrosani')
def tetrosani():
    return render_template('tetrosani.html', players=get_team_players('თეთროსანი'))

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

@app.route('/support')
def support():
    return render_template('support.html')

# ==========================================
# 🔐 ავტორიზაციის სისტემა (Auth)
# ==========================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        team_name = request.form.get('team_name', '').strip() # ვიღებთ გუნდის სახელს HTML-დან
        
        if not username or not password:
            flash('გთხოვთ შეავსოთ ყველა ველი!', 'error')
            return redirect(url_for('register'))
            
        hashed_password = generate_password_hash(password)
        
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # users-ის ნაცვლად ვწერთ "Users"-ს და ვამატებთ team_name-ს
            cur.execute('INSERT INTO "Users" (username, password, team_name) VALUES (%s, %s, %s)', 
                        (username, hashed_password, team_name))
            conn.commit()
            flash('რეგისტრაცია წარმატებით დასრულდა! შეგიძლიათ შეხვიდეთ.', 'success')
            return redirect(url_for('login'))
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            flash('ეს მომხმარებლის სახელი უკვე დაკავებულია!', 'error')
        finally:
            cur.close()
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # users-ის ნაცვლად ვწერთ "Users"-ს
        cur.execute('SELECT * FROM "Users" WHERE username = %s', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash(f'მოგესალმებით, {username}!', 'success')
            return redirect(url_for('home'))
        else:
            flash('არასწორი მომხმარებლის სახელი ან პაროლი!', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('თქვენ გამოხვედით სისტემიდან.', 'info')
    return redirect(url_for('home'))

# ==========================================
# ⚽ ფენტეზი გუნდის აწყობის სისტემა
# ==========================================

@app.route('/pick-team', methods=['GET', 'POST'])
def pick_team():
    if 'user_id' not in session:
        flash('გუნდის ასაწყობად ჯერ უნდა შეხვიდეთ სისტემაში!', 'error')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    
    if request.method == 'POST':
        try:
            data = request.get_json() or {}
            player_ids = data.get('player_ids', [])
            captain_id = data.get('captain_id')
            
            if len(player_ids) != 5:
                return jsonify({'success': False, 'message': 'გუნდი უნდა შედგებოდეს ზუსტად 5 მოთამაშისგან!'})
            if captain_id not in player_ids:
                return jsonify({'success': False, 'message': 'კაპიტანი უნდა იყოს თქვენი გუნდის წევრი!'})
                
            cur.execute("SELECT name, real_team FROM players WHERE id = ANY(%s)", (player_ids,))
            selected_raw = cur.fetchall()
            
            team_counts = {}
            for p in selected_raw:
                t = p['real_team']
                team_counts[t] = team_counts.get(t, 0) + 1
                if team_counts[t] > 2:
                    return jsonify({'success': False, 'message': f'ერთი რეალური გუნდიდან ({t}) შეგიძლიათ მაქსიმუმ 2 მოთამაშის აყვანა!'})
            
            cur.execute("DELETE FROM user_teams WHERE user_id = %s", (user_id,))
            for p_id in player_ids:
                is_cap = (p_id == captain_id)
                cur.execute(
                    "INSERT INTO user_teams (user_id, player_id, is_captain) VALUES (%s, %s, %s)",
                    (user_id, p_id, is_cap)
                )
            conn.commit()
            return jsonify({'success': True, 'message': 'გუნდი წარმატებით შეინახა!'})
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': f'შეცდომა შენახვისას: {str(e)}'})
        finally:
            cur.close()
            conn.close()

    # GET მოთხოვნა: ვტვირთავთ ყველა მოთამაშეს საიტზე გამოსაჩენად
    cur.execute("SELECT * FROM players ORDER BY position, name")
    all_players_raw = cur.fetchall()
    
    all_players = []
    for p in all_players_raw:
        p_dict = dict(p)
        p_dict['total_points'] = calculate_fantasy_points(p_dict)
        all_players.append(p_dict)
        
    # ვამოწმებთ, ჰყავს თუ არა მომხმარებელს უკვე აწყობილი გუნდი
    cur.execute("SELECT player_id, is_captain FROM user_teams WHERE user_id = %s", (user_id,))
    my_team_rows = cur.fetchall()
    
    my_team_ids = [r['player_id'] for r in my_team_rows]
    captain_id = next((r['player_id'] for r in my_team_rows if r['is_captain']), None)
    
    cur.close()
    conn.close()
    
    return render_template(
        'pick_team.html',
        all_players=all_players,
        my_team_ids=my_team_ids,
        captain_id=captain_id
    )

# ==========================================
# 📊 ლიდერბორდი (მომხმარებელთა რეიტინგი)
# ==========================================

@app.route('/leaderboard')
def leaderboard():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # users-ის ნაცვლად ვწერთ "Users"-ს
    cur.execute('SELECT id, username FROM "Users"')
    all_users = cur.fetchall()
    
    cur.execute("SELECT * FROM players")
    all_players_raw = cur.fetchall()
    players_pool = {p['id']: dict(p) for p in all_players_raw}
    
    cur.execute("SELECT user_id, player_id, is_captain FROM user_teams")
    all_selections = cur.fetchall()
    
    cur.close()
    conn.close()
    
    user_teams_map = {}
    for sel in all_selections:
        uid = sel['user_id']
        if uid not in user_teams_map:
            user_teams_map[uid] = []
        user_teams_map[uid].append({
            'player_id': sel['player_id'],
            'is_captain': sel['is_captain']
        })
        
    leaderboard_data = []
    for u in all_users:
        uid = u['id']
        uname = u['username']
        
        u_team = user_teams_map.get(uid, [])
        total_score = 0
        
        for item in u_team:
            pid = item['player_id']
            is_cap = item['is_captain']
            
            if pid in players_pool:
                player_data = dict(players_pool[pid])
                player_data['is_captain'] = is_cap
                total_score += calculate_fantasy_points(player_data)
                
        leaderboard_data.append({
            'username': uname,
            'total_points': total_score,
            'team_size': len(u_team)
        })
        
    leaderboard_data.sort(key=lambda x: x['total_points'], reverse=True)
    
    return render_template('leaderboard.html', leaderboard=leaderboard_data)

if __name__ == '__main__':
    # Render-ზე პორტი დინამიურად უნდა წაიკითხოს
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
