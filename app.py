"""
BattleBottle AI Backend
Flask server with Groq/Llama integration for tactical recommendations
Supports both standard missions and custom defense mode
Deployed on Render
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app, origins=['*'], supports_credentials=True)

# Database path - use /tmp for Render (ephemeral storage)
# For persistent storage, use a database service like PostgreSQL
DB_PATH = os.environ.get('DB_PATH', '/tmp/battlebottle.db')

# Groq API configuration
GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'

# Base simulation count (shown in UI as starting point)
BASE_SIMULATION_COUNT = 120

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Simulations table - stores all battle data including custom defense
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
            mode TEXT DEFAULT 'standard',
            custom_map_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Aggregated stats table for quick lookups
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
    
    # Custom defense stats table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_defense_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map TEXT,
            enemy TEXT,
            total_tests INTEGER DEFAULT 0,
            defenses_held INTEGER DEFAULT 0,
            avg_units_used REAL DEFAULT 0,
            best_unit_compositions TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(map, enemy)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

def get_budget_tier(budget):
    """Categorize budget into tiers for aggregation"""
    if budget < 1000000:
        return 'low'
    elif budget < 3000000:
        return 'medium'
    elif budget < 5000000:
        return 'high'
    else:
        return 'unlimited'

def call_groq_llama(prompt, max_tokens=500):
    """Call Groq API with Llama model for tactical analysis"""
    if not GROQ_API_KEY:
        return None
    
    import urllib.request
    import urllib.error
    
    headers = {
        'Authorization': f'Bearer {GROQ_API_KEY}',
        'Content-Type': 'application/json'
    }
    
    data = json.dumps({
        'model': 'llama-3.1-70b-versatile',
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
        req = urllib.request.Request(GROQ_API_URL, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except Exception as e:
        print(f'[Groq API Error] {e}')
        return None

def generate_ai_recommendations(map_name, enemy_type, budget, historical_data):
    """Generate AI-powered recommendations using Llama"""
    
    # Build context from historical data
    if historical_data:
        wins = [d for d in historical_data if d['result'] == 'victory']
        losses = [d for d in historical_data if d['result'] == 'defeat']
        win_rate = len(wins) / len(historical_data) * 100 if historical_data else 0
        
        # Analyze winning compositions
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
        
        # Sort by effectiveness
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
    
    llama_response = call_groq_llama(context, max_tokens=600)
    
    if llama_response:
        try:
            # Extract JSON from response
            json_start = llama_response.find('{')
            json_end = llama_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                ai_recs = json.loads(llama_response[json_start:json_end])
                return ai_recs
        except json.JSONDecodeError:
            print(f'[AI] Failed to parse Llama response as JSON')
    
    return None

def generate_post_battle_feedback(battle_data):
    """Generate AI feedback after a battle using Llama"""
    
    allies = battle_data.get('allies', [])
    result = battle_data.get('result', 'unknown')
    map_name = battle_data.get('map', 'unknown')
    enemy_type = battle_data.get('enemy', 'unknown')
    budget = battle_data.get('budget', 0)
    spent = battle_data.get('spent', 0)
    timer = battle_data.get('timer', 0)
    mode = battle_data.get('mode', 'standard')
    custom_map_name = battle_data.get('customMapName', '')
    
    # Calculate stats
    total_allies = len(allies)
    surviving_allies = sum(1 for a in allies if a.get('hp', 0) > 0)
    total_kills = sum(a.get('kills', 0) for a in allies)
    total_damage = sum(a.get('damageDealt', 0) for a in allies)
    
    # Categorize units
    recon_count = sum(1 for a in allies if a.get('cat') == 'recon')
    attack_count = sum(1 for a in allies if a.get('cat') == 'attack')
    defense_count = sum(1 for a in allies if a.get('cat') == 'defense')
    equip_count = sum(1 for a in allies if a.get('cat') == 'equip')
    
    # Customize prompt based on mode
    if mode == 'custom_defense':
        mode_context = f"""
MODE: CUSTOM DEFENSE TEST
Custom Map Name: {custom_map_name or 'Unnamed'}
This was a defense test where the player placed units to defend against attackers.
Focus feedback on defensive positioning and unit placement strategy.
"""
        result_text = "DEFENSE HELD" if result == 'victory' else "DEFENSE BREACHED"
    else:
        mode_context = "MODE: STANDARD MISSION"
        result_text = result.upper()
    
    prompt = f"""
Analyze this completed battle and provide tactical feedback:

{mode_context}

BATTLE SUMMARY:
- Map: {map_name}
- Enemy: {enemy_type}
- Result: {result_text}
- Battle time: {timer} simulation seconds

DEPLOYMENT:
- Budget: ${budget:,} | Spent: ${spent:,}
- Units deployed: {total_allies} (Recon: {recon_count}, Attack: {attack_count}, Defense: {defense_count}, Equipment: {equip_count})
- Surviving: {surviving_allies}/{total_allies}
- Total kills: {total_kills}

UNIT PERFORMANCE:
{chr(10).join([f"- {a.get('name', 'Unknown')}: {a.get('kills', 0)} kills, {a.get('damageDealt', 0):.0f} damage, {'SURVIVED' if a.get('hp', 0) > 0 else 'DESTROYED'}" for a in allies[:10]])}

Provide tactical feedback in JSON:
{{
    "overall_assessment": "brief assessment",
    "strengths": ["what went well"],
    "weaknesses": ["what could improve"],
    "specific_advice": ["actionable tip 1", "actionable tip 2"],
    "recommended_changes": [
        {{"unit": "unit_name", "action": "add/remove/reposition", "reason": "why"}}
    ]
}}
"""
    
    llama_response = call_groq_llama(prompt, max_tokens=700)
    
    if llama_response:
        try:
            json_start = llama_response.find('{')
            json_end = llama_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(llama_response[json_start:json_end])
        except json.JSONDecodeError:
            print(f'[AI] Failed to parse post-battle feedback as JSON')
    
    return None


def generate_defense_feedback(battle_data):
    """Generate specific feedback for custom defense tests"""
    
    allies = battle_data.get('allies', [])
    result = battle_data.get('result', 'unknown')
    map_name = battle_data.get('map', 'unknown')
    enemy_type = battle_data.get('enemy', 'unknown')
    
    # Analyze unit positions
    positions_by_cat = {'recon': [], 'attack': [], 'defense': [], 'equip': []}
    for ally in allies:
        cat = ally.get('cat', 'attack')
        if cat in positions_by_cat:
            positions_by_cat[cat].append({
                'name': ally.get('name'),
                'x': ally.get('initialX', ally.get('x', 50)),
                'y': ally.get('initialY', ally.get('y', 50)),
                'survived': ally.get('hp', 0) > 0,
                'kills': ally.get('kills', 0)
            })
    
    prompt = f"""
Analyze this CUSTOM DEFENSE placement and provide specific positioning feedback:

MAP: {map_name}
ENEMY TYPE: {enemy_type}
RESULT: {"DEFENSE HELD" if result == 'victory' else "DEFENSE BREACHED"}

UNIT POSITIONS BY CATEGORY:
Recon Units: {json.dumps(positions_by_cat['recon'])}
Attack Units: {json.dumps(positions_by_cat['attack'])}
Defense Units: {json.dumps(positions_by_cat['defense'])}
Equipment: {json.dumps(positions_by_cat['equip'])}

Provide defense improvement feedback in JSON:
{{
    "defense_rating": "A/B/C/D/F",
    "position_analysis": "analysis of current positioning",
    "vulnerabilities": ["weak point 1", "weak point 2"],
    "repositioning_suggestions": [
        {{"unit_type": "type", "current_position": "description", "suggested_position": "description", "reason": "why"}}
    ],
    "additional_units_needed": [
        {{"unit_name": "name", "suggested_position": "description", "reason": "why"}}
    ],
    "key_improvements": ["improvement 1", "improvement 2"]
}}
"""
    
    llama_response = call_groq_llama(prompt, max_tokens=800)
    
    if llama_response:
        try:
            json_start = llama_response.find('{')
            json_end = llama_response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(llama_response[json_start:json_end])
        except json.JSONDecodeError:
            print(f'[AI] Failed to parse defense feedback as JSON')
    
    return None


@app.route('/', methods=['GET'])
def index():
    """Root endpoint"""
    return jsonify({
        'service': 'BattleBottle AI Backend',
        'version': '1.1.0',
        'status': 'running',
        'features': ['standard_missions', 'custom_defense', 'ai_feedback'],
        'endpoints': ['/api/submit', '/api/recommend', '/api/feedback', '/api/defense-feedback', '/api/stats', '/health']
    })


@app.route('/api/submit', methods=['POST'])
def submit_simulation():
    """Submit a completed simulation to the database"""
    try:
        data = request.json
        
        conn = get_db()
        cursor = conn.cursor()
        
        mode = data.get('mode', 'standard')
        custom_map_name = data.get('customMapName', '')
        
        # Store simulation
        cursor.execute('''
            INSERT INTO simulations 
            (session_id, map, enemy, budget, spent, result, timer, allies, enemies, initial_positions, mode, custom_map_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(data.get('initialPositions', {})),
            mode,
            custom_map_name
        ))
        
        sim_id = cursor.lastrowid
        
        # Update aggregated stats
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
        
        # Update custom defense stats if applicable
        if mode == 'custom_defense':
            num_units = len(data.get('allies', []))
            cursor.execute('''
                INSERT INTO custom_defense_stats (map, enemy, total_tests, defenses_held, avg_units_used)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(map, enemy) 
                DO UPDATE SET 
                    total_tests = total_tests + 1,
                    defenses_held = defenses_held + ?,
                    avg_units_used = (avg_units_used * total_tests + ?) / (total_tests + 1),
                    updated_at = CURRENT_TIMESTAMP
            ''', (
                map_name,
                enemy_type,
                1 if data.get('result') == 'victory' else 0,
                num_units,
                1 if data.get('result') == 'victory' else 0,
                num_units
            ))
        
        conn.commit()
        conn.close()
        
        # Generate post-battle AI feedback
        ai_feedback = generate_post_battle_feedback(data)
        
        # Generate additional defense-specific feedback for custom defense mode
        defense_feedback = None
        if mode == 'custom_defense':
            defense_feedback = generate_defense_feedback(data)
        
        return jsonify({
            'success': True,
            'simulation_id': sim_id,
            'message': 'Simulation recorded',
            'mode': mode,
            'ai_feedback': ai_feedback,
            'defense_feedback': defense_feedback
        })
        
    except Exception as e:
        print(f'[Submit Error] {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/recommend', methods=['POST'])
def get_recommendations():
    """Get AI-powered tactical recommendations"""
    try:
        data = request.json
        map_name = data.get('map', '')
        enemy_type = data.get('enemy', '')
        budget = data.get('budget', 2000000)
        budget_tier = get_budget_tier(budget)
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get historical data for this scenario (both standard and custom defense)
        cursor.execute('''
            SELECT * FROM simulations 
            WHERE map = ? AND enemy = ?
            ORDER BY created_at DESC
            LIMIT 50
        ''', (map_name, enemy_type))
        
        historical = [dict(row) for row in cursor.fetchall()]
        
        # Get aggregated stats
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
        
        # Generate AI recommendations using Llama
        ai_recs = generate_ai_recommendations(map_name, enemy_type, budget, historical)
        
        # Build response
        response = {
            'data_points': data_points,
            'overall_win_rate': overall_win_rate,
            'ai_enhanced': ai_recs is not None,
            'simulation_count': BASE_SIMULATION_COUNT + (data_points * 3)
        }
        
        if ai_recs:
            # Merge AI recommendations
            response['specific_units'] = ai_recs.get('specific_units', [])
            response['deployment_zones'] = ai_recs.get('deployment_zones', {})
            response['tactical_notes'] = ai_recs.get('tactical_notes', [])
            response['priority_targets'] = ai_recs.get('priority_targets', [])
        else:
            # Fallback to rule-based recommendations
            response['specific_units'] = get_fallback_units(enemy_type, budget)
            response['deployment_zones'] = get_fallback_positions(map_name)
            response['tactical_notes'] = get_fallback_notes(enemy_type)
        
        return jsonify(response)
        
    except Exception as e:
        print(f'[Recommend Error] {e}')
        return jsonify({'data_points': 0, 'error': str(e)}), 500


@app.route('/api/feedback', methods=['POST'])
def get_ai_feedback():
    """Get detailed AI feedback for a completed battle"""
    try:
        data = request.json
        feedback = generate_post_battle_feedback(data)
        
        if feedback:
            return jsonify({
                'success': True,
                'feedback': feedback
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not generate AI feedback'
            })
            
    except Exception as e:
        print(f'[Feedback Error] {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/defense-feedback', methods=['POST'])
def get_defense_feedback():
    """Get specific feedback for custom defense placements"""
    try:
        data = request.json
        feedback = generate_defense_feedback(data)
        
        if feedback:
            return jsonify({
                'success': True,
                'feedback': feedback
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not generate defense feedback'
            })
            
    except Exception as e:
        print(f'[Defense Feedback Error] {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_global_stats():
    """Get global statistics for the data flywheel"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as total FROM simulations')
        total_sims = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as wins FROM simulations WHERE result = "victory"')
        total_wins = cursor.fetchone()['wins']
        
        cursor.execute('SELECT COUNT(DISTINCT session_id) as players FROM simulations')
        unique_players = cursor.fetchone()['players']
        
        # Custom defense stats
        cursor.execute('SELECT COUNT(*) as total FROM simulations WHERE mode = "custom_defense"')
        custom_defense_tests = cursor.fetchone()['total']
        
        cursor.execute('SELECT COUNT(*) as held FROM simulations WHERE mode = "custom_defense" AND result = "victory"')
        defenses_held = cursor.fetchone()['held']
        
        conn.close()
        
        return jsonify({
            'total_simulations': total_sims,
            'total_victories': total_wins,
            'global_win_rate': round((total_wins / total_sims) * 100) if total_sims > 0 else 0,
            'unique_players': unique_players,
            'custom_defense_tests': custom_defense_tests,
            'defenses_held': defenses_held,
            'defense_success_rate': round((defenses_held / custom_defense_tests) * 100) if custom_defense_tests > 0 else 0,
            'ai_enabled': bool(GROQ_API_KEY),
            'base_simulation_count': BASE_SIMULATION_COUNT
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'ai_enabled': bool(GROQ_API_KEY),
        'version': '1.1.0',
        'features': ['standard', 'custom_defense'],
        'timestamp': datetime.now().isoformat()
    })


def get_fallback_units(enemy_type, budget):
    """Rule-based unit recommendations when AI is unavailable"""
    units = []
    
    if budget >= 500000:
        units.append({'name': 'RQ-11 Raven', 'count': 2, 'reason': 'Reliable recon platform'})
    
    if enemy_type == 'guerrilla':
        units.append({'name': 'Custom FPV Drone', 'count': 15, 'reason': 'Effective against infantry swarms'})
        units.append({'name': 'Switchblade 300', 'count': 8, 'reason': 'Precision anti-infantry'})
    elif enemy_type == 'mercenary':
        units.append({'name': 'Raytheon Coyote', 'count': 5, 'reason': 'Counter fast targets'})
        units.append({'name': 'Switchblade 300', 'count': 10, 'reason': 'Rapid elimination'})
        units.append({'name': 'Custom FPV Drone', 'count': 8, 'reason': 'Backup firepower'})
    else:
        units.append({'name': 'Anduril Anvil', 'count': 4, 'reason': 'Counter-drone capability'})
        units.append({'name': 'Switchblade 600', 'count': 5, 'reason': 'Heavy strike power'})
        units.append({'name': 'Switchblade 300', 'count': 6, 'reason': 'Anti-infantry support'})
        units.append({'name': 'Custom FPV Drone', 'count': 12, 'reason': 'Swarm assault'})
    
    return units


def get_fallback_positions(map_name):
    """Rule-based positioning recommendations"""
    return {
        'recon': {'x': 50, 'y': 85, 'description': 'Center rear for maximum coverage'},
        'attack': {'x': 30, 'y': 90, 'description': 'Left flank approach'},
        'defense': {'x': 70, 'y': 90, 'description': 'Right side protection'}
    }


def get_fallback_notes(enemy_type):
    """Rule-based tactical notes"""
    notes = {
        'army': ['Focus on counter-drone operations first', 'Expect organized resistance with drone support'],
        'guerrilla': ['Spread FPV swarm wide to catch scattered infantry', 'Infantry will use cover effectively'],
        'mercenary': ['Defense line MUST intercept fast movers early', 'Expect aggressive flanking maneuvers']
    }
    return notes.get(enemy_type, ['Assess threat before committing forces'])


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
