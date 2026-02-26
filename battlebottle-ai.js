/**
 * BattleBottle AI Data Flywheel Integration
 * ==========================================
 * Add this to your BattleBottle HTML file to enable the AI data flywheel.
 * 
 * Usage:
 * 1. Include this script in your HTML
 * 2. Set FLYWHEEL_API_URL to your deployed backend
 * 3. Call BattleBottleAI.submitSimulation(gameState) after battles
 * 4. Call BattleBottleAI.getRecommendations(map, enemy, budget) before deployment
 */

var BattleBottleAI = (function() {
    
    // Configure this to your deployed backend URL
    var API_URL = 'https://your-backend.onrender.com';  // Change this!
    
    // Generate or retrieve session ID
    var SESSION_ID = localStorage.getItem('bb_session') || generateSessionId();
    localStorage.setItem('bb_session', SESSION_ID);
    
    function generateSessionId() {
        return 'bb_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    /**
     * Submit simulation data after a battle completes.
     * Call this in your endCombat() or showResult() function.
     * 
     * @param {Object} gameState - The game state object (G)
     * @param {string} result - 'victory' or 'defeat'
     */
    function submitSimulation(gameState, result) {
        if (!API_URL || API_URL.includes('your-backend')) {
            console.log('[AI Flywheel] Backend not configured. Set API_URL.');
            return Promise.resolve(null);
        }
        
        // Build the payload from game state
        var payload = {
            session_id: SESSION_ID,
            map: gameState.map,
            enemy: gameState.enemy,
            budget: gameState.budget,
            spent: gameState.spent,
            result: result,
            timer: gameState.timer,
            allies: [],
            enemies: [],
            initialPositions: {}
        };
        
        // Capture ally data with initial positions
        for (var i = 0; i < gameState.allies.length; i++) {
            var ally = gameState.allies[i];
            payload.allies.push({
                id: ally.id,
                name: ally.name,
                cat: ally.cat,
                cost: ally.cost || 0,
                x: ally.x,
                y: ally.y,
                hp: ally.hp,
                maxHp: ally.maxHp,
                kills: ally.kills || 0,
                damageDealt: ally.damageDealt || 0
            });
            
            // Store initial position if available
            if (ally.initialX !== undefined) {
                payload.initialPositions[ally.id] = {
                    x: ally.initialX,
                    y: ally.initialY
                };
            }
        }
        
        // Capture enemy data
        for (var j = 0; j < gameState.enemies.length; j++) {
            var enemy = gameState.enemies[j];
            payload.enemies.push({
                id: enemy.id,
                name: enemy.name,
                hp: enemy.hp,
                maxHp: enemy.maxHp
            });
        }
        
        // Send to backend
        return fetch(API_URL + '/api/submit', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            console.log('[AI Flywheel] Simulation submitted:', data);
            return data;
        })
        .catch(function(error) {
            console.error('[AI Flywheel] Submit error:', error);
            return null;
        });
    }
    
    /**
     * Get AI recommendations for the current scenario.
     * Call this when the player enters the deployment phase.
     * 
     * @param {string} map - Map ID (e.g., 'canary_wharf')
     * @param {string} enemy - Enemy type (e.g., 'army')
     * @param {number} budget - Available budget
     * @param {boolean} useLLM - Whether to use LLM for natural language (requires GROQ_API_KEY)
     * @returns {Promise<Object>} Recommendations object
     */
    function getRecommendations(map, enemy, budget, useLLM) {
        if (!API_URL || API_URL.includes('your-backend')) {
            console.log('[AI Flywheel] Backend not configured. Set API_URL.');
            return Promise.resolve(getDefaultRecommendations(map, enemy, budget));
        }
        
        var endpoint = useLLM ? '/api/recommend/llm' : '/api/recommend';
        
        return fetch(API_URL + endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                map: map,
                enemy: enemy,
                budget: budget
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(data) {
            console.log('[AI Flywheel] Recommendations received:', data);
            return data;
        })
        .catch(function(error) {
            console.error('[AI Flywheel] Recommend error:', error);
            return getDefaultRecommendations(map, enemy, budget);
        });
    }
    
    /**
     * Get default recommendations when the API is unavailable.
     */
    function getDefaultRecommendations(map, enemy, budget) {
        var recs = {
            scenario: { map: map, enemy: enemy, budget: budget },
            data_points: 0,
            confidence: 0,
            recommended_composition: {
                recon: 2,
                attack: 3,
                defense: enemy === 'army' ? 1 : 0,
                equipment: 1,
                explanation: 'Default recommendation (no player data available yet).'
            },
            top_units: [],
            deployment_zones: {
                recon: { x: 50, y: 85 },
                attack: { x: 50, y: 90 },
                defense: { x: 50, y: 88 }
            },
            tactical_notes: ['Deploy recon first to spot enemies.', 'Spread attack units to avoid grouped losses.']
        };
        
        // Adjust for enemy type
        if (enemy === 'mercenary') {
            recs.recommended_composition.defense = 0;
            recs.tactical_notes.push('No enemy drones - skip defense units.');
        }
        if (enemy === 'army') {
            recs.tactical_notes.push('Enemy has heavy drone presence - use counter-UAS.');
        }
        
        return recs;
    }
    
    /**
     * Get global flywheel statistics.
     */
    function getStats() {
        if (!API_URL || API_URL.includes('your-backend')) {
            return Promise.resolve({ total_simulations: 0, flywheel_status: 'not_configured' });
        }
        
        return fetch(API_URL + '/api/stats')
            .then(function(response) { return response.json(); })
            .catch(function() { return { total_simulations: 0, flywheel_status: 'error' }; });
    }
    
    /**
     * Render recommendations in the game UI.
     * This creates a small panel showing AI suggestions.
     * 
     * @param {Object} recs - Recommendations object from getRecommendations()
     * @param {HTMLElement} container - Container element to render into
     */
    function renderRecommendations(recs, container) {
        if (!container) return;
        
        var html = '<div class="ai-recommendations" style="' +
            'background:rgba(156,39,176,0.15);border:1px solid #9C27B0;border-radius:6px;' +
            'padding:10px;margin-bottom:10px;font-size:10px;color:#CE93D8;">';
        
        html += '<div style="font-weight:700;margin-bottom:6px;color:#E1BEE7;">🤖 AI TACTICAL ADVISOR</div>';
        
        if (recs.confidence !== undefined) {
            html += '<div style="margin-bottom:6px;color:#A0A8B8;">Based on ' + 
                    (recs.data_points || 0) + ' player simulations (' + 
                    (recs.confidence || 0) + '% confidence)</div>';
        }
        
        if (recs.recommended_composition) {
            var comp = recs.recommended_composition;
            html += '<div style="margin-bottom:4px;"><strong>Suggested Deployment:</strong></div>';
            html += '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px;">';
            html += '<span>🦅 Recon: ' + (comp.recon || 0) + '</span>';
            html += '<span>💥 Attack: ' + (comp.attack || 0) + '</span>';
            html += '<span>🛡️ Defense: ' + (comp.defense || 0) + '</span>';
            html += '<span>📡 Equip: ' + (comp.equipment || 0) + '</span>';
            html += '</div>';
        }
        
        if (recs.top_units && recs.top_units.length > 0) {
            html += '<div style="margin-bottom:4px;"><strong>Top Performing Units:</strong></div>';
            html += '<div style="font-size:9px;color:#A0A8B8;">';
            for (var i = 0; i < Math.min(3, recs.top_units.length); i++) {
                var unit = recs.top_units[i];
                html += unit.name + ' (' + (unit.win_rate || 0) + '% survival)';
                if (i < Math.min(3, recs.top_units.length) - 1) html += ', ';
            }
            html += '</div>';
        }
        
        if (recs.tactical_notes && recs.tactical_notes.length > 0) {
            html += '<div style="margin-top:6px;font-size:9px;color:#A0A8B8;font-style:italic;">';
            html += '💡 ' + recs.tactical_notes[0];
            html += '</div>';
        }
        
        if (recs.overall_win_rate !== undefined && recs.data_points > 0) {
            html += '<div style="margin-top:6px;font-size:9px;color:' + 
                    (recs.overall_win_rate > 50 ? '#4CAF50' : '#FF9800') + ';">';
            html += 'Overall win rate for this scenario: ' + recs.overall_win_rate + '%';
            html += '</div>';
        }
        
        html += '</div>';
        
        container.innerHTML = html + container.innerHTML;
    }
    
    /**
     * Set the API URL for the backend.
     */
    function setApiUrl(url) {
        API_URL = url;
        console.log('[AI Flywheel] API URL set to:', url);
    }
    
    // Public API
    return {
        submitSimulation: submitSimulation,
        getRecommendations: getRecommendations,
        getStats: getStats,
        renderRecommendations: renderRecommendations,
        setApiUrl: setApiUrl,
        getSessionId: function() { return SESSION_ID; }
    };
    
})();

// Optional: Auto-initialize message
console.log('[AI Flywheel] BattleBottle AI module loaded. Session:', BattleBottleAI.getSessionId());
