# Solo Leveling: The System

> "You do not level up. You survive."

A gamified life-management system inspired by *Solo Leveling*. Track your productive quests, manage your physical and mental attributes, and avoid the lethal penalties of 'The System'.

## 🌑 Core Features

### 1. The Dashboard (The HUD)
- **Status Window**: Real-time display of **STR**, **INT**, **AGI**, **VIT**, and **SEN**.
- **Visual Feedback**: Interface glitching and distortion based on health and penalty status.
- **Active Effects**: Icons for conditions (Well Rested, Tired, System Frozen) and passive buffs.
- **Persistent Header**: A dynamic banner displaying your Level, Rank, and XP progress.

### 2. Quests & The AI Architect
- **Ranked Quests**: E-Rank to S-Rank tasks with varying rewards.
- **The Architect AI**: Integrated LLM (Gemini) that automatically assigns Stat attributes and Ranks to new tasks.
- **Task Decomposition**: Use the "⚡" (Architect Breakdown) to shatter large S-Rank goals into actionable sub-tasks.
- **AI Security**: Hardened prompts with input sanitization and XML-style tagging to prevent instruction overrides.

### 3. Penalty & Recovery
- **Daily Protocols**: Recurring tasks that must be completed every 24 hours to avoid penalties.
- **The Penalty Zone**: Failing dailies triggers state-based punishments:
    1. **Debuff (-20% Stats)**: System glitching active.
    2. **Lockdown**: Access to the Shop is restricted.
    3. **Level Down (-3 Levels)**: Major setback for failing to redeem yourself.
- **Sleep Log**: Track sleep hours to maintain your "WELL RESTED" condition (+10% XP bonus).

### 4. Vacation Mode (System Freeze) 🌴
- **Emergency Suspension**: Freeze the system to stop daily quest timers and avoid penalties while away.
- **The Price of Peace**: Every full week spent on vacation reduces all stats by **1 point** upon return.
- **Monthly Limit**: Highly restricted usage—only one vacation activation permitted per calendar month.
- **Visual Overlay**: A full-screen "FROZEN" effect with a persistent bottom control bar for termination.

### 5. Progression & Economy
- **Class Advancement**: Unlock specialized paths (*Assassin*, *Mage*, *Tank*) at key milestones.
- **The Economy**: Earn **Gold (G)** for purchases and **Coins (C)** for rare artifacts.
- **Inventory & Shop**: Equip artifacts in Head, Body, Weapon, and Accessory slots to boost stats.
- **Leaderboard**: Compete with other 'Hunters' to see who has leveled up the most or taken the most vacations.
- **History Log**: Comprehensive log of all completed quests and cleared penalties.

## 🛠 Setup & Installation

### Prerequisites
- Python 3.10+
- Gemini API Key (Optional, for "The Architect" functionality)

### Installation
1.  **Clone the Repository**
2.  **Environment Setup**:
    ```bash
    python -m venv env
    source env/bin/activate  # or env\Scripts\activate on Windows
    pip install -r requirements.txt
    ```
3.  **Global Variables**:
    Create a `.env` file or export `GEMINI_API_KEY` for AI features.
4.  **Database Initialization**:
    ```bash
    flask db upgrade  # or let the app auto-initialize on first run
    ```

### Running the System
```bash
python run.py
```
Access the interface at `http://localhost:5000`.

## 🧪 Testing
The system includes a comprehensive test suite for verifying core logic:
```bash
pytest
```

---
*"I alone level up."*
