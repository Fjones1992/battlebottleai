"""
BattleBottle AI Backend
Flask server with Fireworks AI/Llama integration for tactical recommendations
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Database path
DB_PATH = os.environ.get('DB_PATH', 'battlebottle.db')

# Fireworks AI API configuration
FIREWORKS_API_KEY = os.environ.get('FIREWORKS_API_KEY', '')
FIREWORKS_API_URL = 'https://api.fireworks.ai/inference/v1/chat/completions'

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            map TEXT,
            enemy TEXT,
            budget INTEGER,
            spent INTEGER,
            result TEXT,
            timer INTEGER,
            allies TEXT,
            enemies TEXT,
            initial_positions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scenario_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map TEXT,
            enemy TEXT,
            budget_tier TEXT,
            total_battles INTEGER DEFAULT 0,
            victories INTEGER DEFAULT 0,
            avg_time REAL DEFAULT 0,
            best_compositions TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(map, enemy, budget_tier)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

def get_budget_tier(budget):
    if budget < 1000000:
        return 'low'
    elif budget < 3000000:
        return 'medium'
    elif budget < 5000000:
        return 'high'
    else:
        return 'unlimited'

def call_llama(prompt, max_tokens=500):
    """Call Fireworks AI API with Llama model"""
    if not FIREWORKS_API_KEY:
        print('[Fireworks AI] No API key configured')
        return None
    
    import urllib.request
    import urllib.error
    
    headers = {
        'Authorization': f'Bearer {FIREWORKS_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    data = json.dumps({
        'model': 'accounts/fireworks/models/llama-v3p3-70b-instruct',
        'messages': [
            {
                'role': 'system',
                'content': '''You are a tactical AI advisor for BattleBottle, a military drone warfare simulator. 
Analyze battle data and provide concise, actionable tactical recommendations.
Focus on: unit composition, deployment positioning, and strategic priorities.
Keep responses brief and structured. Use military terminology appropriately.
Format recommendations as JSON when requested.'''
            },
            {
                'role': 'user',
                'content': prompt
            }
        ],
        'max_tokens': max_tokens,
        'temperature': 0.7
    }).encode('utf-8')
    
    try:
        req = urllib.request.Request(FIREWORKS_API_URL, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            print('[Fireworks AI] Success')
            return result['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        print(f'[Fireworks AI Error] HTTP Error {e.code}: {e.reason}')
        return None
    except Exception as e:
        print(f'[Fireworks AI Error] {e}')
        return None

def generate_ai_recommendations(map_name, enemy_type, budget, historical_data):
    """Generate AI-powered recommendations using Llama"""
    
    if historical_data:
        wins = [d for d in historical_data if d['result'] == 'victory']
        win_rate = len(wins) / len(historical_data) * 100 if historical_data else 0
        
        winning_units = {}
        for win in wins:
            allies = json.loads(win['allies']) if isinstance(win['allies'], str) else win['allies']
            for ally in allies:
                name = ally.get('name', 'Unknown')
                if name not in winning_units:
                    winning_units[name] = {'count': 0, 'total_kills': 0, 'total_damage': 0}
                winning_units[name]['count'] += 1
                winning_units[name]['total_kills'] += ally.get('kills', 0)
                winning_units[name]['total_damage'] += ally.get('damageDealt', 0)
        
        unit_effectiveness = sorted(
            winning_units.items(),
            key=lambda x: x[1]['total_kills'] / max(1, x[1]['count']),
            reverse=True
        )
        
        context = f"""
Historical battle data for {map_name} vs {enemy_type}:
- Total battles: {len(historical_data)}
- Win rate: {win_rate:.1f}%
- Budget range: ${budget:,}

Most effective units in winning battles:
{chr(10).join([f"- {name}: {stats['count']} deployments, {stats['total_kills']} total kills" for name, stats in unit_effectiveness[:5]])}

Analyze this data and provide tactical recommendations in JSON format:
{{
    "specific_units": [
        {{"name": "unit_name", "count": number, "reason": "brief reason"}}
    ],
    "deployment_zones": {{
        "recon": {{"x": percent, "y": percent, "description": "positioning advice"}},
        "attack": {{"x": percent, "y": percent, "description": "positioning advice"}},
        "defense": {{"x": percent, "y": percent, "description": "positioning advice"}}
    }},
    "tactical_notes": ["key insight 1", "key insight 2"],
    "priority_targets": ["target type 1", "target type 2"]
}}
"""
    else:
        context = f"""
New scenario with no historical data:
- Map: {map_name}
- Enemy: {enemy_type}
- Budget: ${budget:,}

Provide baseline tactical recommendations for a drone warfare engagement.
Consider typical enemy compositions and terrain factors.
Return JSON format:
{{
    "specific_units": [
        {{"name": "unit_name", "count": number, "reason": "brief reason"}}
    ],
    "deployment_zones": {{
        "recon": {{"x": percent, "y": percent, "description": "positioning advice"}},
        "attack": {{"x": percent, "y": percent, "description": "positioning advice"}}
    }},
    "tactical_notes": ["key insight 1"],
    "priority_targets": ["target type 1"]
}}
"""
    
    llama_response = call_llama(context, max_tokens=600)
    
    if llama_response:
        try:
            json_start = llama_response.find('{')
            json_end = llama_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                ai_recs = json.loads(llama_response[json_start:json_end])
                return ai_recs
        except json.JSONDecodeError:
            print('[AI] Failed to parse Llama response as JSON')
    
    return None

def generate_post_battle_feedback(battle_data):
    """Generate AI feedback after a battle"""
    
    allies = battle_data.get('allies', [])
    result = battle_data.get('result', 'unknown')
    map_name = battle_data.get('map', 'unknown')
    enemy_type = battle_data.get('enemy', 'unknown')
    budget = battle_data.get('budget', 0)
    spent = battle_data.get('spent', 0)
    timer = battle_data.get('timer', 0)
    
    total_allies = len(allies)
    surviving_allies = sum(1 for a in allies if a.get('hp', 0) > 0)
    total_kills = sum(a.get('kills', 0) for a in allies)
    
    unit_summary = {}
    for ally in allies:
        cat = ally.get('cat', 'unknown')
        if cat not in unit_summary:
            unit_summary[cat] = {'count': 0, 'survived': 0, 'kills': 0}
        unit_summary[cat]['count'] += 1
        if ally.get('hp', 0) > 0:
            unit_summary[cat]['survived'] += 1
        unit_summary[cat]['kills'] += ally.get('kills', 0)
    
    prompt = f"""
Battle completed on {map_name} vs {enemy_type}:
- Result: {result.upper()}
- Budget: ${budget:,} / Spent: ${spent:,}
- Battle duration: {timer} seconds
- Allies deployed: {total_allies}, Survived: {surviving_allies}
- Total kills: {total_kills}

Unit breakdown:
{chr(10).join([f"- {cat}: {stats['count']} deployed, {stats['survived']} survived, {stats['kills']} kills" for cat, stats in unit_summary.items()])}

Provide brief tactical feedback in JSON format:
{{
    "overall_assessment": "one sentence summary",
    "what_worked": ["point 1", "point 2"],
    "what_to_improve": ["point 1", "point 2"],
    "suggested_changes": ["specific suggestion 1", "specific suggestion 2"]
}}
"""
    
    llama_response = call_llama(prompt, max_tokens=400)
    
    if llama_response:
        try:
            json_start = llama_response.find('{')
            json_end = llama_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(llama_response[json_start:json_end])
        except json.JSONDecodeError:
            print('[AI] Failed to parse feedback as JSON')
    
    return None

@app.route('/')
def index():
    return jsonify({
        'service': 'BattleBottle AI Backend',
        'version': '1.2.0',
        'status': 'running',
        'ai_provider': 'Fireworks AI',
        'endpoints': ['/api/submit', '/api/recommend', '/api/feedback', '/api/defense-feedback', '/api/stats', '/health']
    })

@app.route('/api/submit', methods=['POST'])
def submit_simulation():
    try:
        data = request.json
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO simulations 
            (session_id, map, enemy, budget, spent, result, timer, allies, enemies, initial_positions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('session_id', ''),
            data.get('map', ''),
            data.get('enemy', ''),
            data.get('budget', 0),
            data.get('spent', 0),
            data.get('result', ''),
            data.get('timer', 0),
            json.dumps(data.get('allies', [])),
            json.dumps(data.get('enemies', [])),
            json.dumps(data.get('initialPositions', {}))
        ))
        
        sim_id = cursor.lastrowid
        
        budget_tier = get_budget_tier(data.get('budget', 0))
        map_name = data.get('map', '')
        enemy_type = data.get('enemy', '')
        
        cursor.execute('''
            INSERT INTO scenario_stats (map, enemy, budget_tier, total_battles, victories)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(map, enemy, budget_tier) 
            DO UPDATE SET 
                total_battles = total_battles + 1,
                victories = victories + ?,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            map_name,
            enemy_type,
            budget_tier,
            1 if data.get('result') == 'victory' else 0,
            1 if data.get('result') == 'victory' else 0
        ))
        
        conn.commit()
        conn.close()
        
        ai_feedback = generate_post_battle_feedback(data)
        
        return jsonify({
            'success': True,
            'simulation_id': sim_id,
            'message': 'Simulation recorded',
            'ai_feedback': ai_feedback
        })
        
    except Exception as e:
        print(f'[Submit Error] {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/recommend', methods=['POST'])
def get_recommendations():
    try:
        data = request.json
        map_name = data.get('map', '')
        enemy_type = data.get('enemy', '')
        budget = data.get('budget', 2000000)
        budget_tier = get_budget_tier(budget)
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM simulations 
            WHERE map = ? AND enemy = ?
            ORDER BY created_at DESC
            LIMIT 50
        ''', (map_name, enemy_type))
        
        historical = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('''
            SELECT * FROM scenario_stats
            WHERE map = ? AND enemy = ? AND budget_tier = ?
        ''', (map_name, enemy_type, budget_tier))
        
        stats = cursor.fetchone()
        conn.close()
        
        data_points = len(historical)
        overall_win_rate = 0
        
        if stats:
            total = stats['total_battles']
            wins = stats['victories']
            overall_win_rate = round((wins / total) * 100) if total > 0 else 0
        
        ai_recs = generate_ai_recommendations(map_name, enemy_type, budget, historical)
        
        response = {
            'data_points': data_points,
            'overall_win_rate': overall_win_rate,
            'ai_enhanced': ai_recs is not None
        }
        
        if ai_recs:
            response['specific_units'] = ai_recs.get('specific_units', [])
            response['deployment_zones'] = ai_recs.get('deployment_zones', {})
            response['tactical_notes'] = ai_recs.get('tactical_notes', [])
            response['priority_targets'] = ai_recs.get('priority_targets', [])
        else:
            response['specific_units'] = get_fallback_units(enemy_type, budget)
            response['deployment_zones'] = get_fallback_positions(map_name)
            response['tactical_notes'] = get_fallback_notes(enemy_type)
        
        return jsonify(response)
        
    except Exception as e:
        print(f'[Recommend Error] {e}')
        return jsonify({'data_points': 0, 'error': str(e)}), 500

@app.route('/api/feedback', methods=['POST'])
def get_ai_feedback():
    try:
        data = request.json
        feedback = generate_post_battle_feedback(data)
        
        if feedback:
            return jsonify({'success': True, 'feedback': feedback})
        else:
            return jsonify({'success': False, 'error': 'Could not generate AI feedback'})
            
    except Exception as e:
        print(f'[Feedback Error] {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/defense-feedback', methods=['POST'])
def get_defense_feedback():
    try:
        data = request.json
        data['mode'] = 'custom_defense'
        feedback = generate_post_battle_feedback(data)
        
        if feedback:
            return jsonify({'success': True, 'feedback': feedback, 'mode': 'defense'})
        else:
            return jsonify({'success': False, 'error': 'Could not generate defense feedback'})
            
    except Exception as e:
        print(f'[Defense Feedback Error] {e}')
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_global_stats():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as total FROM simulations')
        total_sims = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as wins FROM simulations WHERE result = "victory"')
        total_wins = cursor.fetchone()['wins']
        
        cursor.execute('SELECT COUNT(DISTINCT session_id) as players FROM simulations')
        unique_players = cursor.fetchone()['players']
        
        conn.close()
        
        return jsonify({
            'total_simulations': total_sims,
            'total_victories': total_wins,
            'global_win_rate': round((total_wins / total_sims) * 100) if total_sims > 0 else 0,
            'unique_players': unique_players,
            'ai_enabled': bool(FIREWORKS_API_KEY)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'ai_enabled': bool(FIREWORKS_API_KEY),
        'ai_provider': 'Fireworks AI',
        'model': 'accounts/fireworks/models/llama-v3p3-70b-instruct',
        'timestamp': datetime.now().isoformat()
    })

def get_fallback_units(enemy_type, budget):
    units = []
    if enemy_type == 'guerrilla':
        units.append({'name': 'RQ-11 Raven', 'count': 2, 'reason': 'Recon for scattered infantry'})
        units.append({'name': 'Switchblade 300', 'count': 4, 'reason': 'Effective against infantry'})
        units.append({'name': 'Custom FPV Drone', 'count': 3, 'reason': 'Cheap area denial'})
    elif enemy_type == 'mercenary':
        units.append({'name': 'PD-100 Black Hornet', 'count': 2, 'reason': 'Stealthy recon vs elite forces'})
        units.append({'name': 'Switchblade 600', 'count': 2, 'reason': 'Anti-armor capability'})
        units.append({'name': 'Coyote Block 3', 'count': 2, 'reason': 'Counter-drone defense'})
    else:
        units.append({'name': 'Boeing ScanEagle', 'count': 1, 'reason': 'Long-range ISR'})
        units.append({'name': 'MQ-9 Reaper', 'count': 1, 'reason': 'Precision strike capability'})
        units.append({'name': 'Switchblade 600', 'count': 3, 'reason': 'Anti-armor loitering munition'})
        units.append({'name': 'Anduril Anvil', 'count': 2, 'reason': 'Counter-UAS protection'})
    return units

def get_fallback_positions(map_name):
    return {
        'recon': {'x': 50, 'y': 85, 'description': 'Center rear for maximum coverage'},
        'attack': {'x': 30, 'y': 90, 'description': 'Left flank approach'},
        'defense': {'x': 70, 'y': 90, 'description': 'Right side protection'}
    }

def get_fallback_notes(enemy_type):
    notes = {
        'army': ['Focus on counter-drone operations', 'Expect organized resistance', 'Use terrain for cover'],
        'guerrilla': ['Watch for ambush positions', 'Infantry will use buildings', 'Spread recon wide'],
        'mercenary': ['Fast and aggressive enemies', 'Prioritize eliminating scouts', 'Defend flanks']
    }
    return notes.get(enemy_type, ['Assess threat before committing forces'])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
