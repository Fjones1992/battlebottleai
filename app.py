"""
BattleBottle AI Data Flywheel Backend
=====================================
Collects simulation data from players and generates tactical recommendations
using Llama via Groq API (free tier).

Deploy for free on: Render.com, Railway.app, or Vercel
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime
from collections import defaultdict
import statistics

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from your game

# Database setup
DB_PATH = os.environ.get('DB_PATH', 'battlebottle.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with required tables."""
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            map_id TEXT NOT NULL,
            enemy_type TEXT NOT NULL,
            budget INTEGER,
            spent INTEGER,
            result TEXT,
            survival_rate REAL,
            kill_efficiency REAL,
            battle_duration INTEGER,
            cost_per_kill REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS deployments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            simulation_id INTEGER,
            unit_id TEXT,
            unit_name TEXT,
            unit_category TEXT,
            unit_cost INTEGER,
            start_x REAL,
            start_y REAL,
            survived INTEGER,
            kills INTEGER,
            damage_dealt REAL,
            FOREIGN KEY (simulation_id) REFERENCES simulations(id)
        );
        
        CREATE TABLE IF NOT EXISTS strategy_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            map_id TEXT,
            enemy_type TEXT,
            pattern_hash TEXT UNIQUE,
            unit_composition TEXT,
            avg_win_rate REAL,
            sample_count INTEGER,
            avg_cost_efficiency REAL,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_sim_map_enemy ON simulations(map_id, enemy_type, result);
        CREATE INDEX IF NOT EXISTS idx_patterns ON strategy_patterns(map_id, enemy_type, avg_win_rate DESC);
    ''')
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'BattleBottle AI Flywheel'})


@app.route('/api/submit', methods=['POST'])
def submit_simulation():
    """
    Receive simulation data after a battle completes.
    
    Expected payload:
    {
        "session_id": "uuid",
        "map": "canary_wharf",
        "enemy": "army",
        "budget": 2000000,
        "spent": 850000,
        "result": "victory" | "defeat",
        "timer": 180,
        "allies": [
            {
                "id": "a1", "name": "MQ-9 Reaper", "cat": "attack",
                "cost": 32000000, "x": 50, "y": 85, "hp": 80, "maxHp": 80,
                "kills": 3, "damageDealt": 300
            }
        ],
        "enemies": [
            {"id": "e1", "name": "INFANTRY", "hp": 0, "maxHp": 100}
        ],
        "initialPositions": {
            "a1": {"x": 50, "y": 85}
        }
    }
    """
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Calculate metrics
        allies = data.get('allies', [])
        enemies = data.get('enemies', [])
        initial_pos = data.get('initialPositions', {})
        
        alive_allies = sum(1 for a in allies if a.get('hp', 0) > 0)
        total_allies = len(allies)
        survival_rate = (alive_allies / total_allies * 100) if total_allies > 0 else 0
        
        killed_enemies = sum(1 for e in enemies if e.get('hp', 0) <= 0)
        total_enemies = len(enemies)
        
        spent = data.get('spent', 0)
        cost_per_kill = (spent / killed_enemies) if killed_enemies > 0 else 0
        
        attack_units = sum(1 for a in allies if a.get('cat') == 'attack')
        kill_efficiency = (killed_enemies / attack_units) if attack_units > 0 else 0
        
        # Insert simulation record
        cursor.execute('''
            INSERT INTO simulations 
            (session_id, map_id, enemy_type, budget, spent, result, 
             survival_rate, kill_efficiency, battle_duration, cost_per_kill)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('session_id'),
            data.get('map'),
            data.get('enemy'),
            data.get('budget'),
            spent,
            data.get('result'),
            survival_rate,
            kill_efficiency,
            data.get('timer', 0),
            cost_per_kill
        ))
        
        sim_id = cursor.lastrowid
        
        # Insert deployment records
        for ally in allies:
            unit_id = ally.get('id')
            init_x = initial_pos.get(unit_id, {}).get('x', ally.get('x', 50))
            init_y = initial_pos.get(unit_id, {}).get('y', ally.get('y', 85))
            
            cursor.execute('''
                INSERT INTO deployments 
                (simulation_id, unit_id, unit_name, unit_category, unit_cost,
                 start_x, start_y, survived, kills, damage_dealt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                sim_id,
                ally.get('id'),
                ally.get('name'),
                ally.get('cat'),
                ally.get('cost', 0),
                init_x,
                init_y,
                1 if ally.get('hp', 0) > 0 else 0,
                ally.get('kills', 0),
                ally.get('damageDealt', 0)
            ))
        
        conn.commit()
        
        # Update strategy patterns
        update_patterns(conn, data.get('map'), data.get('enemy'))
        
        conn.close()
        
        return jsonify({
            'success': True,
            'simulation_id': sim_id,
            'message': 'Simulation data recorded'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def update_patterns(conn, map_id, enemy_type):
    """Analyze recent simulations and update winning patterns."""
    cursor = conn.cursor()
    
    # Get recent simulations for this map/enemy combo
    cursor.execute('''
        SELECT s.id, s.result, s.survival_rate, s.cost_per_kill,
               GROUP_CONCAT(d.unit_category || ':' || d.unit_name) as composition
        FROM simulations s
        JOIN deployments d ON d.simulation_id = s.id
        WHERE s.map_id = ? AND s.enemy_type = ?
        GROUP BY s.id
        ORDER BY s.timestamp DESC
        LIMIT 100
    ''', (map_id, enemy_type))
    
    sims = cursor.fetchall()
    
    # Group by unit composition and calculate win rates
    compositions = defaultdict(lambda: {'wins': 0, 'total': 0, 'costs': []})
    
    for sim in sims:
        comp = sim['composition']
        compositions[comp]['total'] += 1
        if sim['result'] == 'victory':
            compositions[comp]['wins'] += 1
        if sim['cost_per_kill'] and sim['cost_per_kill'] > 0:
            compositions[comp]['costs'].append(sim['cost_per_kill'])
    
    # Store patterns with good win rates
    for comp, stats in compositions.items():
        if stats['total'] >= 3:  # Need at least 3 samples
            win_rate = stats['wins'] / stats['total']
            avg_cost = statistics.mean(stats['costs']) if stats['costs'] else 0
            pattern_hash = f"{map_id}:{enemy_type}:{comp}"
            
            cursor.execute('''
                INSERT INTO strategy_patterns 
                (map_id, enemy_type, pattern_hash, unit_composition, 
                 avg_win_rate, sample_count, avg_cost_efficiency, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(pattern_hash) DO UPDATE SET
                    avg_win_rate = excluded.avg_win_rate,
                    sample_count = excluded.sample_count,
                    avg_cost_efficiency = excluded.avg_cost_efficiency,
                    last_updated = excluded.last_updated
            ''', (
                map_id, enemy_type, pattern_hash, comp,
                win_rate, stats['total'], avg_cost, datetime.now()
            ))
    
    conn.commit()


@app.route('/api/recommend', methods=['POST'])
def get_recommendations():
    """
    Get AI-powered recommendations for a given scenario.
    
    Expected payload:
    {
        "map": "canary_wharf",
        "enemy": "army",
        "budget": 2000000
    }
    
    Returns quantitative recommendations based on winning patterns.
    """
    try:
        data = request.json
        map_id = data.get('map')
        enemy_type = data.get('enemy')
        budget = data.get('budget', 2000000)
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get best performing strategies for this scenario
        cursor.execute('''
            SELECT unit_composition, avg_win_rate, sample_count, avg_cost_efficiency
            FROM strategy_patterns
            WHERE map_id = ? AND enemy_type = ?
            ORDER BY avg_win_rate DESC, sample_count DESC
            LIMIT 5
        ''', (map_id, enemy_type))
        
        patterns = cursor.fetchall()
        
        # Get overall statistics for this scenario
        cursor.execute('''
            SELECT 
                COUNT(*) as total_sims,
                SUM(CASE WHEN result = 'victory' THEN 1 ELSE 0 END) as victories,
                AVG(survival_rate) as avg_survival,
                AVG(cost_per_kill) as avg_cost_per_kill
            FROM simulations
            WHERE map_id = ? AND enemy_type = ?
        ''', (map_id, enemy_type))
        
        stats = cursor.fetchone()
        
        # Get most successful unit types
        cursor.execute('''
            SELECT 
                d.unit_name,
                d.unit_category,
                d.unit_cost,
                COUNT(*) as usage_count,
                AVG(d.survived) as survival_rate,
                AVG(d.kills) as avg_kills
            FROM deployments d
            JOIN simulations s ON s.id = d.simulation_id
            WHERE s.map_id = ? AND s.enemy_type = ? AND s.result = 'victory'
            GROUP BY d.unit_name
            ORDER BY usage_count DESC, avg_kills DESC
            LIMIT 10
        ''', (map_id, enemy_type))
        
        winning_units = cursor.fetchall()
        
        # Get optimal deployment positions
        cursor.execute('''
            SELECT 
                d.unit_category,
                AVG(d.start_x) as avg_x,
                AVG(d.start_y) as avg_y,
                COUNT(*) as sample_size
            FROM deployments d
            JOIN simulations s ON s.id = d.simulation_id
            WHERE s.map_id = ? AND s.enemy_type = ? AND s.result = 'victory'
            AND d.survived = 1
            GROUP BY d.unit_category
        ''', (map_id, enemy_type))
        
        positions = cursor.fetchall()
        
        conn.close()
        
        # Build recommendations
        recommendations = build_recommendations(
            map_id, enemy_type, budget, 
            patterns, stats, winning_units, positions
        )
        
        return jsonify(recommendations)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def build_recommendations(map_id, enemy_type, budget, patterns, stats, winning_units, positions):
    """Build structured recommendations from the data."""
    
    # Parse winning compositions
    unit_counts = defaultdict(list)
    if patterns:
        for pattern in patterns:
            if pattern['unit_composition']:
                units = pattern['unit_composition'].split(',')
                for unit in units:
                    parts = unit.split(':')
                    if len(parts) == 2:
                        cat, name = parts
                        unit_counts[cat].append(name)
    
    # Calculate recommended composition
    recon_count = len([u for u in unit_counts.get('recon', [])])
    attack_count = len([u for u in unit_counts.get('attack', [])])
    defense_count = len([u for u in unit_counts.get('defense', [])])
    equip_count = len([u for u in unit_counts.get('equip', [])])
    
    # Normalize to typical deployment
    total = recon_count + attack_count + defense_count + equip_count
    if total > 0:
        rec_recon = max(1, round(recon_count / total * 6))
        rec_attack = max(2, round(attack_count / total * 6))
        rec_defense = round(defense_count / total * 6)
        rec_equip = round(equip_count / total * 6)
    else:
        # Default recommendations if no data
        rec_recon = 2
        rec_attack = 3
        rec_defense = 1 if enemy_type == 'army' else 0
        rec_equip = 1
    
    # Get specific unit recommendations
    recommended_units = []
    if winning_units:
        for unit in winning_units[:6]:
            recommended_units.append({
                'name': unit['unit_name'],
                'category': unit['unit_category'],
                'cost': unit['unit_cost'],
                'win_rate': round(unit['survival_rate'] * 100, 1),
                'avg_kills': round(unit['avg_kills'], 1)
            })
    
    # Get position recommendations
    position_recs = {}
    if positions:
        for pos in positions:
            position_recs[pos['unit_category']] = {
                'x': round(pos['avg_x'], 1),
                'y': round(pos['avg_y'], 1),
                'sample_size': pos['sample_size']
            }
    
    # Calculate confidence based on data volume
    total_sims = stats['total_sims'] if stats and stats['total_sims'] else 0
    confidence = min(100, total_sims * 5)  # 100% confidence at 20+ simulations
    
    win_rate = 0
    if stats and stats['total_sims'] and stats['victories']:
        win_rate = round(stats['victories'] / stats['total_sims'] * 100, 1)
    
    return {
        'scenario': {
            'map': map_id,
            'enemy': enemy_type,
            'budget': budget
        },
        'data_points': total_sims,
        'confidence': confidence,
        'overall_win_rate': win_rate,
        'recommended_composition': {
            'recon': rec_recon,
            'attack': rec_attack,
            'defense': rec_defense,
            'equipment': rec_equip,
            'explanation': f"Based on {total_sims} simulations, deploy {rec_recon} recon, {rec_attack} attack, {rec_defense} defense units."
        },
        'top_units': recommended_units,
        'deployment_zones': position_recs,
        'tactical_notes': generate_tactical_notes(map_id, enemy_type, stats)
    }


def generate_tactical_notes(map_id, enemy_type, stats):
    """Generate tactical notes based on scenario."""
    notes = []
    
    # Map-specific advice
    map_notes = {
        'canary_wharf': 'Urban high-rise environment. MQ-9 Reaper effective against infantry in buildings.',
        'gaza': 'Dense urban combat. Spread units to avoid grouped losses. Use recon to spot building entrances.',
        'afghanistan': 'Rural terrain with limited cover. Fast attack drones recommended.',
        'open_field': 'Minimal cover. Aggressive positioning viable. Speed advantage critical.',
        'minneapolis': 'Grid layout allows flanking. Use jammers to control corridors.'
    }
    
    enemy_notes = {
        'guerrilla': 'Erratic movement patterns. Maintain recon coverage. Budget for attrition.',
        'army': 'Heavy drone presence. Counter-UAS essential. Balanced approach works.',
        'mercenary': 'Fast elite infantry. Prioritize kill speed over economy. No enemy drones.'
    }
    
    if map_id in map_notes:
        notes.append(map_notes[map_id])
    if enemy_type in enemy_notes:
        notes.append(enemy_notes[enemy_type])
    
    # Data-driven notes
    if stats and stats['avg_cost_per_kill']:
        avg_cost = stats['avg_cost_per_kill']
        if avg_cost < 50000:
            notes.append(f"Cost efficiency is strong at ${avg_cost:,.0f}/kill. FPV drones performing well.")
        elif avg_cost > 150000:
            notes.append(f"High cost per kill (${avg_cost:,.0f}). Consider cheaper units like Switchblade 300.")
    
    return notes


@app.route('/api/recommend/llm', methods=['POST'])
def get_llm_recommendations():
    """
    Get natural language recommendations using Llama via Groq.
    Requires GROQ_API_KEY environment variable.
    """
    try:
        import requests as http_req
        
        groq_key = os.environ.get('GROQ_API_KEY')
        if not groq_key:
            return jsonify({
                'error': 'GROQ_API_KEY not configured',
                'fallback': 'Use /api/recommend for data-driven recommendations'
            }), 400
        
        data = request.json
        map_id = data.get('map')
        enemy_type = data.get('enemy')
        budget = data.get('budget', 2000000)
        
        # Get structured recommendations first
        conn = get_db()
        cursor = conn.cursor()
        
        # Get winning patterns
        cursor.execute('''
            SELECT unit_composition, avg_win_rate, sample_count
            FROM strategy_patterns
            WHERE map_id = ? AND enemy_type = ?
            ORDER BY avg_win_rate DESC
            LIMIT 3
        ''', (map_id, enemy_type))
        patterns = cursor.fetchall()
        
        # Get statistics
        cursor.execute('''
            SELECT COUNT(*) as total, 
                   AVG(CASE WHEN result='victory' THEN 1.0 ELSE 0.0 END) as win_rate
            FROM simulations WHERE map_id = ? AND enemy_type = ?
        ''', (map_id, enemy_type))
        stats = cursor.fetchone()
        
        conn.close()
        
        # Build context for LLM
        patterns_text = ""
        if patterns:
            patterns_text = "Top winning compositions:\n"
            for p in patterns:
                patterns_text += f"- {p['unit_composition']} (Win rate: {p['avg_win_rate']*100:.0f}%, {p['sample_count']} battles)\n"
        
        prompt = f"""You are a military drone tactics advisor for the BattleBottle training simulator.

SCENARIO:
- Map: {map_id.replace('_', ' ').title()}
- Enemy Type: {enemy_type.title()}
- Budget: ${budget:,}

DATA FROM {stats['total'] if stats else 0} PLAYER SIMULATIONS:
- Overall win rate: {(stats['win_rate']*100) if stats and stats['win_rate'] else 0:.0f}%
{patterns_text}

AVAILABLE UNITS:
Recon: RQ-11 Raven ($35k), PD-100 Black Hornet ($195k), Skydio X2D ($25k), ScanEagle ($100k)
Attack: Switchblade 300 ($6k, kamikaze), Switchblade 600 ($55k, kamikaze), FPV Drone ($500, kamikaze), MQ-9 Reaper ($32M, precision)
Defense: Coyote Block 3 ($28k), Anduril Anvil ($75k), DroneHunter F700 ($120k), Skywall Patrol ($45k)
Equipment: Silent Archer jammer ($350k), DroneGun ($32k), Orion Tether ($85k), MPU5 Radio ($18k)

Based on the player data, provide SPECIFIC quantitative recommendations:
1. Exact unit composition (e.g., "Deploy 2x RQ-11 Raven, 3x Switchblade 300, 1x Coyote Block 3")
2. Deployment positions as percentages (e.g., "Recon at x=30%, y=75%")
3. Priority target order
4. Budget allocation breakdown

Keep response under 200 words. Be direct and tactical."""

        # Call Groq API
        response = http_req.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'llama-3.1-8b-instant',
                'messages': [
                    {'role': 'system', 'content': 'You are a concise military tactics AI. Give specific, quantitative recommendations.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 500,
                'temperature': 0.7
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            llm_text = result['choices'][0]['message']['content']
            
            return jsonify({
                'scenario': {'map': map_id, 'enemy': enemy_type, 'budget': budget},
                'data_points': stats['total'] if stats else 0,
                'recommendation': llm_text,
                'model': 'llama-3.1-8b-instant'
            })
        else:
            return jsonify({
                'error': f'Groq API error: {response.status_code}',
                'fallback': 'Use /api/recommend for data-driven recommendations'
            }), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_global_stats():
    """Get global statistics about the data flywheel."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM simulations')
    total_sims = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(DISTINCT session_id) FROM simulations')
    unique_players = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT map_id, enemy_type, COUNT(*) as count,
               AVG(CASE WHEN result='victory' THEN 1.0 ELSE 0.0 END) as win_rate
        FROM simulations
        GROUP BY map_id, enemy_type
        ORDER BY count DESC
    ''')
    scenario_stats = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'total_simulations': total_sims,
        'unique_sessions': unique_players,
        'scenarios': scenario_stats,
        'flywheel_status': 'active' if total_sims > 10 else 'warming_up'
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG', 'false').lower() == 'true')
