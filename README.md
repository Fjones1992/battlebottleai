# BattleBottle AI Data Flywheel

A proprietary AI system that collects player simulation data and generates tactical recommendations using machine learning. The more players engage with BattleBottle, the smarter the AI becomes.

## How It Works

1. **Data Collection**: Every time a player completes a battle simulation, the system captures:
   - Unit composition (which drones were deployed)
   - Deployment positions (where units were placed)
   - Battle outcome (victory/defeat)
   - Efficiency metrics (survival rate, cost per kill, time to complete)

2. **Pattern Analysis**: The backend aggregates this data to identify:
   - Winning unit compositions for each map/enemy combination
   - Optimal deployment zones
   - Most effective units by survival and kill rates

3. **AI Recommendations**: Players receive quantitative tactical advice:
   - "Deploy 2x RQ-11 Raven, 3x Switchblade 300, 1x Coyote Block 3"
   - "Position recon at x=30%, y=75% for optimal coverage"
   - "Budget allocation: 60% attack, 25% recon, 15% defense"

4. **Optional LLM Enhancement**: Using Llama 3.1 via Groq (free tier), the system generates natural language tactical briefings.

---

## Quick Start (Free Deployment)

### Option A: Deploy to Render.com (Recommended)

1. **Create a Render account** at https://render.com (free tier available)

2. **Create a new Web Service**:
   - Connect your GitHub repo or use "Manual Deploy"
   - Runtime: Python
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`

3. **Add a Disk** (for persistent data):
   - Name: `data`
   - Mount Path: `/data`
   - Size: 1 GB (free tier)

4. **Set Environment Variables**:
   - `DB_PATH`: `/data/battlebottle.db`
   - `GROQ_API_KEY`: (optional, get free key from https://console.groq.com)

5. **Deploy** and note your URL (e.g., `https://battlebottle-ai.onrender.com`)

### Option B: Deploy to Railway.app

1. Create account at https://railway.app
2. New Project > Deploy from GitHub
3. Add a volume mounted at `/data`
4. Set environment variables as above

### Option C: Run Locally for Testing

```bash
cd battlebottle-ai
pip install -r requirements.txt
python app.py
```

Server runs at http://localhost:5000

---

## Integrating with BattleBottle

### Step 1: Add the JavaScript Module

Add this script tag to your HTML (before the closing `</body>` tag):

```html
<script src="battlebottle-ai.js"></script>
<script>
    // Set your deployed backend URL
    BattleBottleAI.setApiUrl('https://your-backend.onrender.com');
</script>
```

### Step 2: Track Initial Positions

In your `deploy()` function, store the initial position:

```javascript
function deploy(data, x, y) {
    // ... existing code ...
    u.initialX = x;  // ADD THIS
    u.initialY = y;  // ADD THIS
    // ... rest of function ...
}
```

### Step 3: Track Unit Performance

In your combat loop, track kills and damage. Add these properties to allies:

```javascript
// When an ally kills an enemy:
ally.kills = (ally.kills || 0) + 1;
ally.damageDealt = (ally.damageDealt || 0) + damageAmount;
```

### Step 4: Submit Data After Battle

In your `showResult()` or `endCombat()` function:

```javascript
function showResult(result) {
    // ... existing result display code ...
    
    // Submit to AI flywheel
    BattleBottleAI.submitSimulation(G, result);
}
```

### Step 5: Show Recommendations During Deployment

In your `startMission()` function, after entering deploy phase:

```javascript
function startMission() {
    // ... existing code ...
    
    // Fetch and display AI recommendations
    BattleBottleAI.getRecommendations(G.map, G.enemy, G.budget)
        .then(function(recs) {
            var container = document.querySelector('.select-content');
            BattleBottleAI.renderRecommendations(recs, container);
        });
}
```

---

## API Endpoints

### POST /api/submit
Submit simulation data after a battle.

**Request:**
```json
{
    "session_id": "bb_123456",
    "map": "canary_wharf",
    "enemy": "army",
    "budget": 2000000,
    "spent": 850000,
    "result": "victory",
    "timer": 180,
    "allies": [
        {
            "id": "a1",
            "name": "MQ-9 Reaper",
            "cat": "attack",
            "cost": 32000000,
            "x": 50,
            "y": 85,
            "hp": 80,
            "maxHp": 80,
            "kills": 3,
            "damageDealt": 300
        }
    ],
    "enemies": [
        {"id": "e1", "name": "INFANTRY", "hp": 0, "maxHp": 100}
    ],
    "initialPositions": {
        "a1": {"x": 50, "y": 85}
    }
}
```

### POST /api/recommend
Get data-driven recommendations.

**Request:**
```json
{
    "map": "canary_wharf",
    "enemy": "army",
    "budget": 2000000
}
```

**Response:**
```json
{
    "scenario": {"map": "canary_wharf", "enemy": "army", "budget": 2000000},
    "data_points": 47,
    "confidence": 100,
    "overall_win_rate": 68.1,
    "recommended_composition": {
        "recon": 2,
        "attack": 3,
        "defense": 1,
        "equipment": 1,
        "explanation": "Based on 47 simulations, deploy 2 recon, 3 attack, 1 defense units."
    },
    "top_units": [
        {"name": "Switchblade 300", "category": "attack", "cost": 6000, "win_rate": 75.0, "avg_kills": 1.8},
        {"name": "RQ-11 Raven", "category": "recon", "cost": 35000, "win_rate": 82.0, "avg_kills": 0}
    ],
    "deployment_zones": {
        "recon": {"x": 45.2, "y": 82.1, "sample_size": 31},
        "attack": {"x": 52.8, "y": 88.4, "sample_size": 89}
    },
    "tactical_notes": [
        "Urban high-rise environment. MQ-9 Reaper effective against infantry in buildings.",
        "Heavy drone presence. Counter-UAS essential. Balanced approach works."
    ]
}
```

### POST /api/recommend/llm
Get LLM-enhanced natural language recommendations (requires GROQ_API_KEY).

### GET /api/stats
Get global flywheel statistics.

**Response:**
```json
{
    "total_simulations": 1247,
    "unique_sessions": 89,
    "scenarios": [
        {"map_id": "canary_wharf", "enemy_type": "army", "count": 412, "win_rate": 0.68}
    ],
    "flywheel_status": "active"
}
```

---

## Getting a Free Groq API Key

1. Go to https://console.groq.com
2. Sign up for free
3. Create an API key
4. Add it as `GROQ_API_KEY` environment variable

Groq provides free access to Llama 3.1 with very fast inference. The free tier is generous for demo purposes.

---

## Defence Pitch Value

This AI data flywheel directly supports BattleBottle's dual-use value proposition:

**For Defence Stakeholders:**
- "Every game session generates crowdsourced tactical intelligence"
- "Player data trains AI models for optimal drone deployment strategies"
- "Quantitative recommendations based on thousands of simulated battles"
- "Self-improving system that gets smarter as engagement scales"

**Metrics to Track:**
- Total simulations collected
- Winning patterns discovered
- Recommendation accuracy (if players follow suggestions, do they win more?)
- Data volume growth over time

---

## Files in This Package

```
battlebottle-ai/
├── app.py              # Python backend API
├── requirements.txt    # Python dependencies
├── render.yaml         # Render.com deployment config
├── battlebottle-ai.js  # JavaScript integration module
└── README.md           # This file
```

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with debug mode
DEBUG=true python app.py

# Test the API
curl http://localhost:5000/api/health
curl -X POST http://localhost:5000/api/recommend \
    -H "Content-Type: application/json" \
    -d '{"map":"canary_wharf","enemy":"army","budget":2000000}'
```

---

## Next Steps

1. Deploy the backend to Render.com
2. Integrate the JavaScript module into your demo
3. Test with a few simulations
4. Watch the data accumulate and patterns emerge
5. Demo the "AI Tactical Advisor" feature at your next defence industry event

The system starts with sensible defaults and progressively improves as more players engage with BattleBottle.
