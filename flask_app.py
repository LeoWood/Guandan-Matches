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

    # 按照时间先后排序（处理 NULL 值）
    matches = sorted(matches, key=lambda m: m.time if m.time else datetime.datetime.min, reverse=True)

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

@app.route('/annual_report')
def annual_report():
    import numpy as np
    from collections import defaultdict, Counter
    
    # 获取年度参数（默认当前年）
    year = request.args.get('year', datetime.datetime.now().year, type=int)
    
    # 获取该年度所有比赛
    matches = Match.query.filter(
        db.extract('year', Match.time) == year
    ).all()
    
    if not matches:
        return render_template('annual_report.html', year=year, no_data=True)
    
    # === 基础统计 ===
    total_matches = len(matches)
    finished_matches = [m for m in matches if m.status == 'finished']
    total_rounds = sum(len(RoundScore.query.filter_by(match_id=m.id).all()) // m.player_count for m in matches)
    
    # 参与人次
    all_players = []
    for match in matches:
        players = Player.query.filter_by(match_id=match.id).all()
        all_players.extend(players)
    total_participations = len(all_players)
    unique_players = len(set(p.name for p in all_players))
    
    # 时间分布（按月）
    monthly_distribution = defaultdict(int)
    for match in matches:
        month = match.time.month
        monthly_distribution[month] += 1
    monthly_data = [{'month': f'{m}月', 'count': monthly_distribution.get(m, 0)} for m in range(1, 13)]
    
    # 地点热度 TOP3
    location_counter = Counter(m.location for m in matches)
    top_locations = location_counter.most_common(3)
    
    # 最早/最晚开始时间
    earliest_match = min(matches, key=lambda m: m.time.time()) if matches else None
    latest_match = max(matches, key=lambda m: m.time.time()) if matches else None
    
    # 获取这两场比赛的玩家列表
    earliest_players = Player.query.filter_by(match_id=earliest_match.id).all() if earliest_match else []
    latest_players = Player.query.filter_by(match_id=latest_match.id).all() if latest_match else []
    
    # === 荣誉榜单 ===
    # 计算每个选手的统计数据
    player_stats = defaultdict(lambda: {
        'total_score': 0,
        'matches': 0,
        'wins': 0,
        'first_place': 0,
        'ranks': [],
        'comebacks': 0,
        'profit': 0,  # 收益/亏损
        'max_single_round_score': 0,  # 单轮最高分
        'match_rank_ranges': [],  # 每场比赛的名次范围（用于计算过山车）
        'teammates': defaultdict(lambda: {'matches': 0, 'wins': 0}),
        'opponents': defaultdict(lambda: {'matches': 0, 'wins': 0})
    })
    
    for match in finished_matches:
        players = Player.query.filter_by(match_id=match.id).all()
        round_scores = RoundScore.query.filter_by(match_id=match.id).all()
        
        # 计算个人总分
        player_total_scores = defaultdict(int)
        player_match_ranks = defaultdict(list)  # 记录每个选手在本场比赛中的名次
        for score in round_scores:
            player = Player.query.get(score.player_id)
            player_total_scores[player.id] = player_total_scores.get(player.id, 0) + score.points
            player_stats[player.name]['total_score'] += score.points
            player_stats[player.name]['ranks'].append(score.rank)
            player_match_ranks[player.name].append(score.rank)  # 记录本场名次
            
            # 更新单轮最高分
            if score.points > player_stats[player.name]['max_single_round_score']:
                player_stats[player.name]['max_single_round_score'] = score.points
            
            if score.rank == 1:
                player_stats[player.name]['first_place'] += 1
        
        # 计算每个选手在本场比赛的名次波动（过山车）
        for player_name, ranks in player_match_ranks.items():
            if len(ranks) > 1:
                rank_range = max(ranks) - min(ranks)  # 最大名次 - 最小名次
                player_stats[player_name]['match_rank_ranges'].append(rank_range)
        
        # 计算队伍总分
        team_scores = {1: 0, 2: 0}
        for player in players:
            team_scores[player.team] += player_total_scores.get(player.id, 0)
        
        winning_team = 1 if team_scores[1] > team_scores[2] else 2 if team_scores[2] > team_scores[1] else None
        
        # 计算收益/亏损（积分差，88封顶）
        score_diff = abs(team_scores[1] - team_scores[2])
        score_diff = min(score_diff, 88)  # 积分差88封顶
        
        # 统计胜负和参赛次数
        for player in players:
            name = player.name
            player_stats[name]['matches'] += 1
            
            if winning_team and player.team == winning_team:
                player_stats[name]['wins'] += 1
                player_stats[name]['profit'] += score_diff  # 赢家获得积分差（最多88）
            elif winning_team:
                player_stats[name]['profit'] -= score_diff  # 输家失去积分差（最多88）
            elif not winning_team:  # 平局算半场胜利
                player_stats[name]['wins'] += 1
            
            # 记录队友和对手
            for other_player in players:
                if other_player.id != player.id:
                    if other_player.team == player.team:
                        player_stats[name]['teammates'][other_player.name]['matches'] += 1
                        if winning_team == player.team:
                            player_stats[name]['teammates'][other_player.name]['wins'] += 1
                    else:
                        player_stats[name]['opponents'][other_player.name]['matches'] += 1
                        if winning_team == player.team:
                            player_stats[name]['opponents'][other_player.name]['wins'] += 1
        
        # 计算翻盘次数（最后一轮从落后到领先）
        rounds = defaultdict(list)
        for score in round_scores:
            rounds[score.round_number].append(score)
        
        if len(rounds) >= 2:
            last_round = max(rounds.keys())
            second_last_round = last_round - 1
            
            if second_last_round in rounds:
                # 倒数第二轮的队伍分数
                team_scores_before = {1: 0, 2: 0}
                for score in rounds[second_last_round]:
                    player = Player.query.get(score.player_id)
                    team_scores_before[player.team] += score.points
                
                # 最后一轮的队伍分数
                team_scores_after = {1: 0, 2: 0}
                for score in rounds[last_round]:
                    player = Player.query.get(score.player_id)
                    team_scores_after[player.team] += score.points
                
                # 判断是否翻盘
                if (team_scores_before[1] < team_scores_before[2] and 
                    team_scores_after[1] > team_scores_after[2]):
                    for player in players:
                        if player.team == 1:
                            player_stats[player.name]['comebacks'] += 1
                elif (team_scores_before[2] < team_scores_before[1] and 
                      team_scores_after[2] > team_scores_after[1]):
                    for player in players:
                        if player.team == 2:
                            player_stats[player.name]['comebacks'] += 1
    
    # 年度积分王
    top_scorer = max(player_stats.items(), key=lambda x: x[1]['total_score']) if player_stats else None
    
    # 年度胜率王（最少10场）
    win_rate_candidates = [(name, stats) for name, stats in player_stats.items() if stats['matches'] >= 10]
    top_win_rate = max(win_rate_candidates, 
                      key=lambda x: x[1]['wins'] / x[1]['matches']) if win_rate_candidates else None
    
    # 铁人奖（参赛最多）
    iron_man = max(player_stats.items(), key=lambda x: x[1]['matches']) if player_stats else None
    
    # 最佳搭档（同队胜率最高，最少10场）
    best_partners = []
    for name, stats in player_stats.items():
        for teammate, team_stats in stats['teammates'].items():
            if team_stats['matches'] >= 10:
                win_rate = team_stats['wins'] / team_stats['matches']
                best_partners.append((name, teammate, team_stats['matches'], team_stats['wins'], win_rate))
    best_partners = sorted(best_partners, key=lambda x: x[4], reverse=True)[:3]
    
    # === 趣味数据 ===
    # 头名收割机
    first_place_king = max(player_stats.items(), 
                          key=lambda x: x[1]['first_place']) if player_stats else None
    
    # 稳定达人（名次方差最小，最少10场）
    stable_candidates = [(name, stats) for name, stats in player_stats.items() 
                        if stats['matches'] >= 10 and len(stats['ranks']) > 0]
    stable_player = None
    if stable_candidates:
        stable_player = min(stable_candidates, 
                          key=lambda x: np.var(x[1]['ranks']))
    
    # 大心脏选手（翻盘次数最多）
    comeback_king = max(player_stats.items(), 
                       key=lambda x: x[1]['comebacks']) if player_stats else None
    
    # 陪跑达人（参赛多但胜率最低，最少10场）
    runner_up_candidates = [(name, stats) for name, stats in player_stats.items() 
                           if stats['matches'] >= 10]
    runner_up = None
    if runner_up_candidates:
        runner_up = min(runner_up_candidates, 
                       key=lambda x: x[1]['wins'] / x[1]['matches'])
    
    # === 新增趣味统计 ===
    # 🎲 人形锦鲤（队友buff最强 - 和TA搭档，队友胜率提升最多）
    lucky_charm = None
    lucky_charm_boost = 0
    for name, stats in player_stats.items():
        if stats['matches'] >= 10:
            # 计算所有队友的平均胜率提升
            teammate_boosts = []
            for teammate, team_stats in stats['teammates'].items():
                if team_stats['matches'] >= 5:  # 至少合作5场
                    # 和该选手搭档的胜率
                    together_win_rate = team_stats['wins'] / team_stats['matches']
                    # 该队友的总体胜率
                    teammate_overall_win_rate = player_stats[teammate]['wins'] / player_stats[teammate]['matches'] if player_stats[teammate]['matches'] > 0 else 0
                    boost = together_win_rate - teammate_overall_win_rate
                    teammate_boosts.append(boost)
            
            if teammate_boosts:
                avg_boost = sum(teammate_boosts) / len(teammate_boosts)
                if avg_boost > lucky_charm_boost:
                    lucky_charm_boost = avg_boost
                    lucky_charm = (name, avg_boost, stats['matches'])
    
    # ☠️ 队友克星（和TA搭档，队友胜率降低最多）
    bad_luck_charm = None
    bad_luck_debuff = 0
    for name, stats in player_stats.items():
        if stats['matches'] >= 10:
            teammate_debuffs = []
            for teammate, team_stats in stats['teammates'].items():
                if team_stats['matches'] >= 5:
                    together_win_rate = team_stats['wins'] / team_stats['matches']
                    teammate_overall_win_rate = player_stats[teammate]['wins'] / player_stats[teammate]['matches'] if player_stats[teammate]['matches'] > 0 else 0
                    debuff = together_win_rate - teammate_overall_win_rate
                    teammate_debuffs.append(debuff)
            
            if teammate_debuffs:
                avg_debuff = sum(teammate_debuffs) / len(teammate_debuffs)
                if avg_debuff < bad_luck_debuff:
                    bad_luck_debuff = avg_debuff
                    bad_luck_charm = (name, avg_debuff, stats['matches'])
    
    # 🌪️ 过山车玩家（单场比赛名次波动最大）
    rollercoaster_player = None
    max_rank_swing = 0
    for name, stats in player_stats.items():
        if stats['matches'] >= 10 and stats['match_rank_ranges']:
            # 计算平均单场名次波动
            avg_swing = sum(stats['match_rank_ranges']) / len(stats['match_rank_ranges'])
            max_swing_in_match = max(stats['match_rank_ranges'])
            if max_swing_in_match > max_rank_swing:
                max_rank_swing = max_swing_in_match
                rollercoaster_player = (name, max_swing_in_match, avg_swing, stats['matches'])
    
    # === 对战记录 ===
    # 最强宿敌（对战次数最多，最少10场）
    rivalries = []
    processed_pairs = set()
    for name, stats in player_stats.items():
        for opponent, opp_stats in stats['opponents'].items():
            pair = tuple(sorted([name, opponent]))
            if pair not in processed_pairs and opp_stats['matches'] >= 10:
                rivalries.append((name, opponent, opp_stats['matches']))
                processed_pairs.add(pair)
    strongest_rivalry = max(rivalries, key=lambda x: x[2]) if rivalries else None
    
    # 最佳拍档（搭档次数最多，不考虑胜率）
    most_frequent_partners = []
    processed_teammate_pairs = set()
    for name, stats in player_stats.items():
        for teammate, team_stats in stats['teammates'].items():
            pair = tuple(sorted([name, teammate]))
            if pair not in processed_teammate_pairs:
                most_frequent_partners.append((name, teammate, team_stats['matches'], team_stats['wins']))
                processed_teammate_pairs.add(pair)
    most_frequent_partners = sorted(most_frequent_partners, key=lambda x: x[2], reverse=True)
    most_frequent_partner = most_frequent_partners[0] if most_frequent_partners else None
    
    # 黄金搭档 vs 冤家对头
    golden_partner = best_partners[0] if best_partners else None
    
    worst_partners = []
    for name, stats in player_stats.items():
        for teammate, team_stats in stats['teammates'].items():
            if team_stats['matches'] >= 10:
                win_rate = team_stats['wins'] / team_stats['matches']
                worst_partners.append((name, teammate, team_stats['matches'], team_stats['wins'], win_rate))
    worst_partners = sorted(worst_partners, key=lambda x: x[4])[:3]
    worst_partner = worst_partners[0] if worst_partners else None
    
    # === 年度之最 ===
    # 单场最高分
    max_single_score = 0
    max_score_player = None
    max_score_match = None
    for match in finished_matches:
        players = Player.query.filter_by(match_id=match.id).all()
        for player in players:
            scores = RoundScore.query.filter_by(match_id=match.id, player_id=player.id).all()
            total = sum(s.points for s in scores)
            if total > max_single_score:
                max_single_score = total
                max_score_player = player.name
                max_score_match = match
    
    # 单轮最大翻盘
    max_comeback = 0
    max_comeback_match = None
    for match in finished_matches:
        rounds = defaultdict(list)
        round_scores = RoundScore.query.filter_by(match_id=match.id).all()
        for score in round_scores:
            rounds[score.round_number].append(score)
        
        if len(rounds) >= 2:
            for round_num in range(2, max(rounds.keys()) + 1):
                prev_round = round_num - 1
                if prev_round in rounds and round_num in rounds:
                    # 计算前一轮队伍分差
                    team_scores_prev = {1: 0, 2: 0}
                    for score in rounds[prev_round]:
                        player = Player.query.get(score.player_id)
                        team_scores_prev[player.team] += score.points
                    
                    # 计算当前轮队伍分差
                    team_scores_curr = {1: 0, 2: 0}
                    for score in rounds[round_num]:
                        player = Player.query.get(score.player_id)
                        team_scores_curr[player.team] += score.points
                    
                    diff_prev = abs(team_scores_prev[1] - team_scores_prev[2])
                    diff_curr = abs(team_scores_curr[1] - team_scores_curr[2])
                    comeback = abs(diff_curr - diff_prev)
                    
                    if comeback > max_comeback:
                        max_comeback = comeback
                        max_comeback_match = match
    
    # 最激烈比赛（分差最小）
    min_diff = float('inf')
    closest_match = None
    for match in finished_matches:
        players = Player.query.filter_by(match_id=match.id).all()
        team_scores = {1: 0, 2: 0}
        for player in players:
            scores = RoundScore.query.filter_by(match_id=match.id, player_id=player.id).all()
            team_scores[player.team] += sum(s.points for s in scores)
        
        diff = abs(team_scores[1] - team_scores[2])
        if diff < min_diff:
            min_diff = diff
            closest_match = match
    
    # 最悬殊比赛（分差最大）
    max_diff = 0
    most_lopsided_match = None
    for match in finished_matches:
        players = Player.query.filter_by(match_id=match.id).all()
        team_scores = {1: 0, 2: 0}
        for player in players:
            scores = RoundScore.query.filter_by(match_id=match.id, player_id=player.id).all()
            team_scores[player.team] += sum(s.points for s in scores)
        
        diff = abs(team_scores[1] - team_scores[2])
        if diff > max_diff:
            max_diff = diff
            most_lopsided_match = match
    
    # 收益/亏损统计
    profit_rankings = sorted([(name, stats['profit']) for name, stats in player_stats.items()],
                            key=lambda x: x[1], reverse=True)
    
    top_profit_maker = profit_rankings[0] if profit_rankings else None
    biggest_loser = profit_rankings[-1] if profit_rankings else None
    
    return render_template('annual_report.html',
                         year=year,
                         no_data=False,
                         # 基础统计
                         total_matches=total_matches,
                         finished_matches_count=len(finished_matches),
                         total_rounds=total_rounds,
                         total_participations=total_participations,
                         unique_players=unique_players,
                         monthly_data=monthly_data,
                         top_locations=top_locations,
                         earliest_match=earliest_match,
                         latest_match=latest_match,
                         earliest_players=earliest_players,
                         latest_players=latest_players,
                         # 荣誉榜单
                         top_scorer=top_scorer,
                         top_win_rate=top_win_rate,
                         iron_man=iron_man,
                         best_partners=best_partners[:3],
                         # 趣味数据
                         first_place_king=first_place_king,
                         stable_player=stable_player,
                         comeback_king=comeback_king,
                         runner_up=runner_up,
                         lucky_charm=lucky_charm,
                         bad_luck_charm=bad_luck_charm,
                         rollercoaster_player=rollercoaster_player,
                         # 对战记录
                         strongest_rivalry=strongest_rivalry,
                         most_frequent_partner=most_frequent_partner,
                         golden_partner=golden_partner,
                         worst_partner=worst_partner,
                         # 年度之最
                         max_score_player=max_score_player,
                         max_single_score=max_single_score,
                         max_score_match=max_score_match,
                         max_comeback=max_comeback,
                         max_comeback_match=max_comeback_match,
                         closest_match=closest_match,
                         min_diff=min_diff,
                         most_lopsided_match=most_lopsided_match,
                         max_diff=max_diff,
                         # 收益亏损
                         top_profit_maker=top_profit_maker,
                         biggest_loser=biggest_loser,
                         profit_rankings=profit_rankings)


# # 运行应用
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8899, debug=True)