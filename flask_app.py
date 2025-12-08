from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///guandan.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

db = SQLAlchemy(app)

class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_count = db.Column(db.Integer)
    time = db.Column(db.DateTime)
    location = db.Column(db.String(100))
    status = db.Column(db.String(20), default='ongoing')
    players = db.relationship('Player', backref='match', lazy=True, cascade="all, delete-orphan")
    scores = db.relationship('RoundScore', backref='match', lazy=True, cascade="all, delete-orphan")

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    player_number = db.Column(db.Integer)
    name = db.Column(db.String(50))
    team = db.Column(db.Integer)

class ScoreRule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    rank = db.Column(db.Integer)
    points = db.Column(db.Integer)

class RoundScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey('match.id'))
    round_number = db.Column(db.Integer)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    rank = db.Column(db.Integer)
    points = db.Column(db.Integer)
    player = db.relationship('Player', backref='scores')

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    matches = Match.query.all()

    # 按照时间先后排序
    matches = sorted(matches, key=lambda m: m.time, reverse=True)

    # 计算选手总分排行榜
    all_players = Player.query.all()
    player_scores = {}
    for player in all_players:
        name = player.name
        if name not in player_scores:
            player_scores[name] = 0
        scores = RoundScore.query.filter_by(player_id=player.id).all()
        player_scores[name] += sum(score.points for score in scores if score.points is not None)
    sorted_score_rankings = sorted(player_scores.items(), key=lambda x: x[1], reverse=True)
    score_rankings_with_index = [(i + 1, name, score) for i, (name, score) in enumerate(sorted_score_rankings)]

    # 计算选手胜率排行榜
    player_stats = {}  # {name: {'matches': 场次, 'wins': 胜场}}
    for match in matches:
        if match.status == 'finished':  # 只统计已结束的比赛
            players = Player.query.filter_by(match_id=match.id).all()
            total_scores = {}
            for player in players:
                player_scores = RoundScore.query.filter_by(match_id=match.id, player_id=player.id).all()
                total_scores[player.id] = sum(score.points for score in player_scores if score.points is not None)

            team_scores = {1: 0, 2: 0}
            for player in players:
                team_scores[player.team] += total_scores.get(player.id, 0)

            winning_team = 1 if team_scores[1] > team_scores[2] else 2 if team_scores[2] > team_scores[1] else None

            for player in players:
                name = player.name
                if name not in player_stats:
                    player_stats[name] = {'matches': 0, 'wins': 0}
                player_stats[name]['matches'] += 1
                if winning_team and player.team == winning_team:
                    player_stats[name]['wins'] += 1
                # 如果平局，算两边都胜利
                if not winning_team:
                    player_stats[name]['wins'] += 1

    # 计算胜率并排序
    win_rate_rankings = []
    for name, stats in player_stats.items():
        win_rate = stats['wins'] / stats['matches'] if stats['matches'] > 0 else 0
        win_rate_rankings.append((name, stats['matches'], stats['wins'], win_rate))
    sorted_win_rate_rankings = sorted(win_rate_rankings, key=lambda x: (x[3], x[1]), reverse=True)
    win_rate_rankings_with_index = [(i + 1, name, matches, wins, f"{win_rate:.2%}") for i, (name, matches, wins, win_rate) in enumerate(sorted_win_rate_rankings)]

    return render_template('index.html', matches=matches, score_rankings=score_rankings_with_index, win_rate_rankings=win_rate_rankings_with_index)

@app.route('/create_match', methods=['GET', 'POST'])
def create_match():
    if request.method == 'POST':
        player_count = int(request.form['player_count'])
        time = datetime.datetime.strptime(request.form['time'], '%Y-%m-%dT%H:%M')
        location = request.form['location']

        match = Match(player_count=player_count, time=time, location=location)
        db.session.add(match)
        db.session.commit()

        for i in range(1, player_count + 1):
            name = request.form[f'player_{i}']
            team = 1 if i % 2 == 1 else 2
            player = Player(match_id=match.id, player_number=i, name=name, team=team)
            db.session.add(player)

        for i in range(1, player_count + 1):
            points = int(request.form[f'points_{i}'])
            rule = ScoreRule(match_id=match.id, rank=i, points=points)
            db.session.add(rule)

        db.session.commit()
        flash('比赛创建成功！')
        return redirect(url_for('index'))

    return render_template('create_match.html')

@app.route('/match/<int:match_id>', methods=['GET', 'POST'])
def match_detail(match_id):
    match = Match.query.get_or_404(match_id)
    players = Player.query.filter_by(match_id=match_id).all()

    if request.method == 'POST':
        if 'submit_scores' in request.form:
            round_number = RoundScore.query.filter_by(match_id=match_id).count() // match.player_count + 1
            rules = {rule.rank: rule.points for rule in ScoreRule.query.filter_by(match_id=match_id).all()}

            selected_players = set()
            for i in range(1, match.player_count + 1):
                player_id = int(request.form[f'player_{i}'])
                if player_id in selected_players:
                    flash('错误：同一选手不能重复出现在成绩中！')
                    return redirect(url_for('match_detail', match_id=match_id))
                selected_players.add(player_id)

            for i in range(1, match.player_count + 1):
                player_id = int(request.form[f'player_{i}'])
                rank = i
                points = rules[rank]
                score = RoundScore(
                    match_id=match_id,
                    round_number=round_number,
                    player_id=player_id,
                    rank=rank,
                    points=points
                )
                db.session.add(score)

            db.session.commit()
            flash('本轮成绩录入成功！')

        elif 'end_match' in request.form:
            match.status = 'finished'
            db.session.commit()
            flash('比赛已结束！')

        return redirect(url_for('match_detail', match_id=match_id))

    scores = RoundScore.query.filter_by(match_id=match_id).all()
    rounds = {}
    for score in scores:
        if score.round_number not in rounds:
            rounds[score.round_number] = []
        rounds[score.round_number].append(score)

    total_scores = {}
    for player in players:
        player_scores = RoundScore.query.filter_by(match_id=match_id, player_id=player.id).all()
        total_scores[player.id] = sum(score.points for score in player_scores)

    sorted_players = sorted(players, key=lambda p: total_scores.get(p.id, 0), reverse=True)

    team_scores = {1: 0, 2: 0}
    for player in players:
        team_scores[player.team] += total_scores.get(player.id, 0)

    score_difference = abs(team_scores[1] - team_scores[2])
    leading_team = 1 if team_scores[1] > team_scores[2] else 2 if team_scores[2] > team_scores[1] else None

    # 计算级牌
    level_cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    team_levels = {1: 0, 2: 0}  # 初始级牌为 '2'，索引 0

    for round_num in sorted(rounds.keys()):
        round_scores = rounds[round_num]
        # 按名次排序
        sorted_round_scores = sorted(round_scores, key=lambda x: x.rank)

        # 计算每队本轮的名次
        team_ranks = {1: [], 2: []}
        for score in sorted_round_scores:
            player = Player.query.get(score.player_id)
            team_ranks[player.team].append(score.rank)

        # 确定第一名的队伍
        first_team = Player.query.get(sorted_round_scores[0].player_id).team

        # 计算完全领先人数
        if team_ranks[1] and team_ranks[2]:  # 确保两队都有数据
            if first_team == 1:
                opponent_best_rank = min(team_ranks[2])  # 偶数队最好名次
                leading_count = sum(1 for rank in team_ranks[1] if rank < opponent_best_rank)
                team_levels[1] = min(team_levels[1] + leading_count, len(level_cards) - 1)
            elif first_team == 2:
                opponent_best_rank = min(team_ranks[1])  # 奇数队最好名次
                leading_count = sum(1 for rank in team_ranks[2] if rank < opponent_best_rank)
                team_levels[2] = min(team_levels[2] + leading_count, len(level_cards) - 1)

    team_level_display = {1: level_cards[team_levels[1]], 2: level_cards[team_levels[2]]}

    return render_template('match_detail.html',
                         match=match,
                         players=players,
                         sorted_players=sorted_players,
                         rounds=rounds,
                         total_scores=total_scores,
                         team_scores=team_scores,
                         score_difference=score_difference,
                         leading_team=leading_team,
                         team_levels=team_level_display)

@app.route('/delete_match/<int:match_id>', methods=['POST'])
def delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    if match.status == 'finished':
        flash('错误：已结束的比赛不能删除！')
        return redirect(url_for('index'))

    ScoreRule.query.filter_by(match_id=match_id).delete()
    RoundScore.query.filter_by(match_id=match_id).delete()
    db.session.delete(match)
    db.session.commit()
    flash('比赛已删除！')
    return redirect(url_for('index'))


# # 运行应用
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8899, debug=True)