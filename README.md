# Solo Leveling: The System

> "You do not level up. You survive."

A gamified life-management system inspired by *Solo Leveling*. Track your productive quests, manage your physical and mental attributes, and avoid the lethal penalties of 'The System'. This application transforms mundane tasks into a high-stakes RPG where your real-life efforts directly impact your character's progression.

## 🌑 Core Features

### 1. The Dashboard (The HUD)
The command center of your growth. It visually represents your current status with a high-fidelity interface.
- **Attributes**: Real-time tracking of **STR**, **INT**, **AGI**, **VIT**, and **SEN**.
    - **INT**: Increases XP gain (+5% per 10 points).
    - **STR**: Reduces penalty severity (Debuff protection).
    - **AGI**: Increases Coin drop rates (+5% per 10 points).
    - **VIT**: Reduces stat loss probability on failure.
    - **SEN**: Boosts Shadow Army passive effectiveness.
- **Currency System**:
    - **Gold (G)**: Standard currency for buying shop items.
    - **Coins (C)**: Premium currency for rare artifacts.
- **Visual Feedback**: The UI actively glitches and distorts when penalties are active or health is low.
- **Audio Settings**: Toggle sound effects (Level Up, Quest Complete, Arise) and music directly from the navbar.
- **Active Effects**: Icons for conditions (Well Rested, Tired, System Frozen) and passive buffs.

### 2. Quests & The AI Architect
- **Ranked Quests**: Tasks are assigned Ranks (E to S) based on difficulty. Higher ranks yield greater rewards.
- **The Architect AI**: Integrated Google Gemini AI automatically analyzes your task descriptions to:
    - Assign an appropriate Rank (E-S).
    - Determine the primary Stat reward (e.g., Coding -> INT, Workout -> STR).
- **Task Decomposition**: Use the **"⚡" (Breakdown)** feature to let the AI shatter a large S-Rank goal into actionable sub-tasks.
- **History Log**: A comprehensive audit trail of every quest completed, timestamped for accountability.

### 3. Analytics, Rejuvenation & Heatmap
- **Activity Heatmap**: A GitHub-style contribution grid visualizing your consistency over the last 365 days. Darker cells indicate higher productivity.
- **Sleep Log & The Elixir of Life**: 
    - Track sleep duration to maintain the "WELL RESTED" status (+10% XP Bonus).
    - If you fall into the "TIRED" condition from poor sleep, you can manually purchase the **Elixir of Life** from the Shop to immediately cure your fatigue and restore your Sleep Streak.

### 4. The Void Focus (Study Timer)
- **Pomodoro Progression**: Enter the Void Focus mode and set a custom timer to concentrate on deep work.
- **Void Tasks & Interruption**: Utilize the built-in Void Task scratchpad to log distracting thoughts or secondary objectives without breaking focus.
- **Dynamic Paced Rewards**: The Void natively hooks into the game's economy engine. 1 Hour of focus guarantees **~2.5%** of your current level's XP requirement, ensuring study time is forever viable at all levels. It also generates 10 Coins per hour.
- **Skip Rest**: A dedicated button to seamlessly skip the mandatory recovery phase if you hit flow state.

### 5. Gamification, Progression, & 2-Year Economy
- **Hyper-Scaled Economy**: Leveling up is balanced for immense long-term retention. Reaching Level 100 as an active player will take **approximately 2 years** of active play (Dailies + Quests + Focus Time). There is no hard cap.
- **Class Evolution**: Unlock specialized classes at Level 10, 25, and 50.
    - **Assassin**: Coin Bonus.
    - **Mage**: XP Bonus.
    - **Tank**: Grace period against penalties.
- **Shadow Army**: "Extract" completed S-Rank quests to turn them into Shadows. Shadows provide passive permanent buffs to your stats.
- **Titles**: Unlock titles (e.g., "The Awakened", "Wolf Slayer") based on achievements. Titles provide unique stat multipliers.
- **Inventory & Shop**: Purchase standard and S-Rank endgame equipment (costing up to 15,000 Coins) requiring months of consistent effort.
- **Leaderboard**: Compete with other 'Hunters'.

### 6. Penalty System
Failure is not without consequence. The System demands consistency.
- **Daily Protocols**: Mandatory Dailies that reset every 24 hours.
- **The Penalty Zone**: Failing to complete Dailies by midnight triggers:
    1.  **Debuff**: -20% to all stats (System Glitching).
    2.  **Shop Lockdown**: Inability to purchase recovery items.
    3.  **Level Regression**: Loss of levels if penalties accumulate.
- **Penalty Quest**: A generated "Survival Quest" (e.g., 50 Pushups) to clear the penalty status.

### 7. Vacation Mode (System Freeze) 🌴
- **Emergency Suspension**: Freeze the system to stop daily quest timers and avoid penalties while away.
- **The Price of Peace**: Every full week spent on vacation reduces all stats by **1 point** upon return.
- **Monthly Limit**: Highly restricted usage—only one vacation activation permitted per calendar month.

---

## 🛡️ Security Implementation
The system is architected with security-first principles to ensure data integrity and safe operation.

### 1. CSRF Protection (Cross-Site Request Forgery)
- **Implementation**: Utilizes `Flask-WTF` to generate unique CSRF tokens for every session.
- **Scope**: All HTML forms and AJAX (Fetch API) requests require a valid `X-CSRFToken` header.
- **Validation**: Server-side checks reject any state-changing request (POST/PUT/DELETE) without a matching token, preventing unauthorized actions from external sites.

### 2. Authentication & Session Management
- **Library**: `Flask-Login` handles user session management.
- **Password Security**: Passwords are **never** stored in plain text. They are hashed using `Werkzeug`'s PBKDF2 (SHA256) implementation with unique salts.
- **Route Protection**: The `@login_required` decorator secures all sensitive endpoints, redirecting unauthenticated traffic to the login gate.

### 3. Input Sanitization & Validation
- **AI Safety**: Prompts sent to Gemini include strict system instructions (xml-tagging) to prevent Prompt Injection attacks.
- **Data Integrity**: Route logic validates inputs (e.g., preventing negative values for "Focus Mode" duration or Shop purchases).
- **ORM Security**: `SQLAlchemy` is used for all database interactions. Its parameterization automatically prevents SQL Injection attacks by treating inputs as data, not executable code.
- **XSS Prevention**: Semantic templating with Jinja2 auto-escaping.

---

## 🛠 Tech Stack
- **Backend**: Python 3.12+, Flask 3.0+
- **Database**: SQLite (Development), SQLAlchemy ORM
- **Frontend**: HTML5, CSS3 (Variables, Grid/Flexbox), JavaScript (ES6+, Fetch API)
- **AI Integration**: Google Generative AI (Gemini Pro)
- **Visuals**: Chart.js (Analytics), Canvas Confetti (VFX)

---

## � Setup & Installation

### Prerequisites
- Python 3.10+
- Gemini API Key (Optional, for "The Architect" functionality)

### Installation
1.  **Clone the Repository**
    ```bash
    git clone https://github.com/your-username/solo-leveling-system.git
    cd solo-leveling-system
    ```

2.  **Environment Setup**:
    ```bash
    python3 -m venv env
    source env/bin/activate  # Windows: env\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Global Variables**:
    Create a `.env` file in the root directory:
    ```env
    FLASK_APP=run.py
    FLASK_ENV=development
    SECRET_KEY=your-super-secret-key-change-this
    GEMINI_API_KEY=your-google-gemini-api-key
    ```

4.  **Database Initialization**:
    Run the migration script to set up the schema and create tables.
    ```bash
    python3 migrate_db.py
    # Then ensure tables are created
    python3 -c "from app import create_app, db; app=create_app(); app.app_context().push(); db.create_all()"
    ```

5.  **Running the System**:
    ```bash
    python3 run.py
    ```
    Access the interface at `http://localhost:5000`.

### Testing
To run the automated test suite (covering Logic, Economy, and Security):
```bash
# Verify all existing functionality
python3 -m pytest tests/
```

---
> *"I alone level up."*
