# Solo Leveling: The System

> "You do not level up. You survive."

A gamified life-management system inspired by *Solo Leveling*. Track your quests, maintain your stats, and avoid the penalties of the System.

## Features

### 1. The Dashboard (The HUD)
- **Status Window**: Real-time display of STR, INT, AGI, VIT, SENSE.
- **Dynamic UI**: Interface glitching and distortion based on penalty status and health.
- **Title System**: Unlock and equip titles (e.g., *Wolf Slayer*, *Monarch of Shadows*) for buffs.
- **Active Effects**: Visual indicators for conditions (Well Rested, Tired) and stat bonuses.

### 2. Quests & Progression
- **Daily Quests**: Recurring tasks that must be completed every 24 hours.
- **Ranked Quests**: E-Rank to S-Rank tasks with exponential XP/Gold rewards.
- **Hunter Rank**: Climb from **Rank E** to **Rank S** by meeting Stat and Level requirements.
- **Class System**: Evolve your class at Levels 20, 40, 60, 80, and 100.
    - **Paths**: *Assassin* (Gold), *Mage* (XP), *Tank* (Survival).
- **Shadow Army**: Extract the shadows of S-Rank bosses to build your own army (Stat Buffs).

### 3. The Economy & Equipment
- **Gold (G)**: Currency for standard rewards.
- **Coins (C)**: Premium currency for endgame items.
- **Shop**: Buy equipment (Weapons, Armor) and real-life rewards.
- **Inventory**: Equip items to "Weapon", "Head", "Body", and "Accessory" slots.
- **Weekly Reset**: Gold resets to 0 every Sunday night.

### 4. The Penalty System
If you fail your Daily Quests:
1.  **Stage 1 (Debuff)**: Stats reduced by 20%. Glitch effect applied.
2.  **Stage 2 (Lockdown)**: Shop locked. Penalty Quest issued.
3.  **Stage 3 (Level Down)**: Level -1. Stats permanent reduction.

## Setup & Installation

### Prerequisites
- Python 3.10+
- Virtual Environment (Recommended)

### Installation
1.  Clone the repository.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Initialize the database:
    ```bash
    # (Optional) Seed initial data
    python -c "from app.services import seed_database; from app.extensions import db; from app import create_app; app=create_app(); app.app_context().push(); db.create_all(); seed_database()"
    ```
    *Note: The app handles initialization automatically on first run.*

### Running the System
```bash
python run.py
```
Access the interface at `http://127.0.0.1:5000`.

### Running Tests
```bash
pytest
```

## Developer Notes
- **Scripts**: Utility scripts are located in `scripts/`.
- **Database**: Uses SQLite (`instance/system.db`).
- **Architecture**: Flask Blueprint structure (`app/routes`, `app/models`, `app/templates`).

---
*"I alone level up."*
