# Shadow_OS: Solo Leveling Life-Management System

> "You do not level up. You survive."

A gamified life-management system inspired by *Solo Leveling*. Track your productive quests, manage your physical and mental attributes, and avoid the lethal penalties of 'The System'. This application transforms mundane tasks into a high-stakes RPG where your real-life efforts directly impact your character's progression.

## 🌑 Core Features

### 1. The Dashboard (The HUD)
The command center of your growth. It visually represents your current status with a high-fidelity interface.
- **Attributes**: Real-time tracking of **STR**, **INT**, **AGI**, **VIT**, and **SNS** (Sense).
    - **INT**: Increases XP gain (+5% per 10 points).
    - **STR**: Reduces penalty severity (Debuff protection).
    - **AGI**: Increases Coin drop rates (+5% per 10 points).
    - **VIT**: Reduces stat loss probability on failure.
    - **SNS**: Boosts Shadow Army passive effectiveness.
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
    - Log 7.5h+ of sleep for "WELL RESTED" (+10% XP). Under 6h makes you "TIRED" (-50% XP) until you log a better night.
    - If you fall into the "TIRED" condition from poor sleep, you can manually purchase the **Elixir of Life** from the Shop to immediately cure your fatigue and restore your Sleep Streak.

### 3b. Life Balance, Measured Quests & the Weekly System Report
- **Life Balance (real-life KPIs)**: A 0-100 score per area (STR/INT/AGI/VIT/SNS) based on what you actually did recently: rank-weighted quest completions (dailies included), focus time (INT) and good sleep (VIT). Effort fades with a 2-week half-life, so neglected areas drop. The dashboard shows each score with a 7-day trend and flags your weakest area; Analytics adds a radar chart comparing now with 30 days ago. Your RPG attributes are unaffected: they remain permanent character power.
- **Measured Quests**: Give any quest a target and unit (e.g. 50 pushups, 20 pages, 2 L water). Log amounts through the day; the progress bar fills and the quest completes when you hit the target. Dailies count today's total; one-off quests keep accumulating. Each measure gets a 30-day chart with its target line in Analytics.
- **Weekly System Report** (`/report`, SYSTEM COMMANDS → REPORT): Perfect days, quests by rank, league placing and duel result, focus hours, average sleep, Life Balance changes, measures vs targets and the area to work on next. Previous weeks are browsable, and a push notification arrives Monday 08:00 (Madrid).

### 4. The Void Focus (Study Timer)
- **Pomodoro Progression**: Enter the Void Focus mode and set a custom timer to concentrate on deep work.
- **Void Tasks & Interruption**: Utilize the built-in Void Task scratchpad to log distracting thoughts or secondary objectives without breaking focus.
- **Focus Pay**: 600 XP per hour of focus (10 XP/minute) plus 10 Coins/hour, so an hour of deep work is worth more than the all-dailies bonus.
- **Skip Rest**: A dedicated button to seamlessly skip the mandatory recovery phase if you hit flow state.

### 5. Gamification, Progression, & 2-Year Economy
- **Levelling Curve**: XP to next level = `100 + 60 × level^1.4` (rounded to 10): 160 XP at Lv 1, 2,760 at Lv 15, 14,450 at Lv 50, 37,960 at Lv 100. Rewards are fixed: quests give E 40 / D 80 / C 150 / B 300 / A 600 XP (non-daily B and A pay at least 5% / 15% of your current level so big quests stay relevant), S-Rank is an instant level up, each daily pays its rank XP, and finishing all dailies adds +500 XP. A typical active day is about 2,000 XP, which reaches Level 100 in roughly 2 years. There is no hard cap. When the curve changes, existing players keep their level and their percentage through it.
- **Class Evolution**: At Level 10, take the Job Change Quest (a **CHOOSE CLASS** button appears on the dashboard) to pick a class. Classes evolve further at Levels 20, 40, 60, 80 and 100.
    - **Assassin**: Coin Bonus.
    - **Mage**: XP Bonus.
    - **Tank**: Grace period against penalties.
- **Shadow Army**: After clearing an S-Rank quest, choose **ARISE** to extract it as a Shadow (+1% to all stats each, boosted by SNS). Unclaimed extractions wait in the ARMY panel.
- **Titles**: Unlock titles (e.g., "The Awakened", "Wolf Slayer") by level, streaks, stats and wealth. The equipped title grants a bonus (XP %, Coin %, or flat stats). Definitions live in `TITLE_DEFINITIONS` in `app/services.py`.
- **My Rewards**: Define your own real-life rewards with your own Gold prices (e.g. Cinema night 400G). Buy them in the Shop and mark them claimed once enjoyed. Gold is halved every Monday 01:00 rather than wiped, so you can save for bigger rewards.
- **Inventory & Shop**: Purchase standard and S-Rank endgame equipment (costing up to 15,000 Coins) requiring months of consistent effort.
- **Weekly Leagues**: The leaderboard's default view is a weekly league that resets Monday 01:00. Points are base XP earned that week ÷ 10, before personal bonuses (S-Rank = 100 pts), so hunters of any level compete fairly. Daily completion % and focus hours are shown too, and the all-time level ranking is one tab away. You get a notification when someone overtakes you, and a popup with last week's results on your first visit each week.
- **Raids**: Shared goals everyone contributes to (e.g. run 100 km together in 30 days). Anyone can start one (max 5 active); clearing the target before the deadline gives every contributor +500 XP and +100 Coins (50 league points). Individual logs earn no XP but count toward Life Balance.
- **Hall of Feats & Kudos**: The leaderboard lists everyone's S-rank clears from the last 30 days. Friends react with 🔥 👏 💪 👑 (one reaction each, tap again to remove) and the owner gets a notification.
- **Your Timezone & Reminder**: Each hunter's daily reset (01:00), weekly Gold halving, penalty deadlines and sleep log follow their own timezone, detected from the device at registration and changeable in Settings. The weekly league keeps one shared boundary (Monday 01:00 Madrid) so everyone competes over the same week. Pick your own daily reminder time; if dailies are unfinished you get one push + inbox reminder that day.
- **Installable App**: Add Shadow OS to your phone's home screen (Android: Install app / iPhone: Share → Add to Home Screen). It runs full-screen with its own icon, and shows an offline screen when there's no connection.
- **Rivals**: Challenge one hunter for a weekly head-to-head duel on your dashboard, with a running win/loss record.
- **Rank Caps**: At most 1 S-rank and 3 A-rank quests per week (dailies and penalties exempt; deleting a quest doesn't refund its slot). Extra requests drop to the next free rank. When Gemini is configured, the Architect gives a second opinion on hand-picked A/S ranks and can only lower them. Set `ARCHITECT_RANK_REVIEW=0` to turn this off.

### 6. Penalty System
Failure is not without consequence. The System demands consistency.
- **Daily Protocols**: Mandatory Dailies that reset every 24 hours.
- **The Penalty Zone**: Failing to complete Dailies by the 1:00 AM reset (Europe/Madrid) triggers:
    1.  **Day 1 – Debuff**: -20% to all stats, reduced by STR (System Glitching).
    2.  **Day 2 – Penalty Zone**: Red UI and a Survival Quest with a deadline.
    3.  **Deadline missed – XP Debt**: You owe half a level of XP (capped at one level). New XP pays the debt before filling your bar. You never lose levels or stats in normal mode.
- **❄️ Streak Freezes**: Earn one for every 7-day streak (bank up to 2). A missed day automatically uses one: your streak survives and no debuff or penalty progress is applied.
- **💀 Hardcore Mode** (opt-in in Settings): +10% XP and a Hardcore badge on the leaderboard and profile, but a failed Penalty Quest costs one level (no stat loss) instead of XP debt. Turning it off ends your Hardcore streak.
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
- **Password Security**: Passwords are **never** stored in plain text. They are hashed with `Werkzeug`'s `generate_password_hash` (salted scrypt). Accounts created before this change used salted SHA-256 and are transparently upgraded on their next successful login.
- **Secret Key**: `SECRET_KEY` must be set in production. If it is missing, a random per-process key is generated (sessions won't survive restarts or be shared between workers).
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
- **AI Integration**: Google Gemini API (`v1beta` `generateContent`, model configurable via `GEMINI_MODEL`)
- **Visuals**: Chart.js (Analytics), Canvas Confetti (VFX)

---

## � Setup & Installation

### Prerequisites
- Python 3.12+ (developed on 3.15)
- Gemini API Key (Optional, for "The Architect" functionality)

### Installation
1.  **Clone the Repository**
    ```bash
    git clone https://github.com/RickyAllitt/Shadow_OS.git
    cd Shadow_OS
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
    # Optional
    GEMINI_MODEL=gemini-3.1-flash-lite
    DATABASE_URL=postgresql://...      # defaults to sqlite:///system.db
    VAPID_PUBLIC_KEY=...               # Web Push
    VAPID_PRIVATE_KEY=...
    CRON_SECRET=long-random-string     # enables the /tasks/run wake-up hook (see Background Jobs)
    SCHEDULER_ENABLED=1                # set 0 to turn off the in-process scheduler
    ```

4.  **Database Initialization**:
    Nothing to run manually. On startup `run.py` creates missing tables, applies the idempotent upgrades in `app/schema_upgrades.py` (e.g. widening `player.password_hash` on Postgres/MySQL) and seeds the shop.

5.  **Running the System**:
    ```bash
    python3 run.py
    ```
    Access the interface at `http://localhost:5000`.

### Background Jobs (reminders, deadline nudges, Weekly Report)
- The jobs start automatically with the app however it's launched (`gunicorn wsgi:app`, `python run.py`, `flask run`). With several gunicorn workers, a file lock ensures only **one** process runs them.
- Every 5 minutes a tick sends whatever is *due*: each player's daily reminder at their own time, deadline nudges from 08:00 in their timezone, and the Weekly Report after Monday 08:00. Each is sent once per day or week, so a late tick still delivers.
- **Free hosts that sleep (e.g. Render free):** nothing runs while the app is asleep. Set `CRON_SECRET` and point a free cron service (e.g. [cron-job.org](https://cron-job.org)) at your app every 5-10 minutes:
  - URL: `https://<your-app>/tasks/run`, method `POST`
  - Header: `X-Cron-Secret: <your CRON_SECRET>` (never put the secret in the URL)
  - This also keeps a free Render service awake. One service running all month uses ~730 of Render's 750 free instance hours.

### Testing
To run the automated test suite (covering Logic, Economy, and Security):
```bash
# Verify all existing functionality
python3 -m pytest tests/

# With a coverage report (currently ~98% of app code)
python3 -m pytest tests/ --cov=app --cov=config --cov-report=term-missing
```

---
> *"I alone level up."*
