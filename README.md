# The System: Gamified Life Manager

A gamified to-do list application that turns your life into an RPG. Built with Flask, it features an intelligent "System Administrator" (AI) that ranks your tasks, a penalty zone for failures, and a verification oath to keep you honest.

## 🌟 Key Features

### 1. The Architect (AI Integration)
The application includes an intelligent agent called **"The Architect"** that analyzes your tasks.
-   **Auto-Ranking**: select `✨ AUTO ✨` when creating a quest, and the AI will determine:
    -   **Rank (E-S)**: Difficulty level.
    -   **Attributes**: Is this a Strength (STR), Intellect (INT), or Discipline (SEN) task?
    -   **XP Rewards**: Calculated based on difficulty.
-   **Gemini Powered**: Uses Google's **Gemini 2.5 Flash** model for high-speed, low-cost analysis.
-   **Offline Fallback**: If no API key is present, it gracefully falls back to a Keyword Engine (e.g., "Run" = STR).

### 2. The Verification Oath
Completing a task isn't just a click.
-   **The Oath**: When you mark a task as done, you are taken to a dedicated "Verification" page.
-   **Commitment**: You must explicitly "Swear on your word" to claim the rewards, adding a psychological layer of accountability.

### 3. Core Gamification
-   **RPG Stats**: Track STR, AGI, INT, VIT, and SEN (Sense/Spirit).
-   **XP & Leveling**: Gain XP to level up.
-   **Currency (Gold)**: Earn gold to buy rewards in the shop.
-   **Penalty Zone**: Fail 3 daily quests? You enter the Penalty Zone, incurring debuffs until you complete a punishment quest.

## 🛠️ Technical Stack
-   **Backend**: Python (Flask), SQLAlchemy (SQLite).
-   **Frontend**: HTML/Jinja2, Pure CSS (Dark Mode aesthetic).
-   **AI Service**: Custom `TheArchitect` class using standard `urllib` (Zero dependencies beyond `python-dotenv`).

## 🚀 Setup & Installation

### 1. Clone & Install
```bash
git clone https://github.com/yourusername/The-System.git
cd The-System
pip install -r requirements.txt
```

### 2. Configure Environment
Create a `.env` file in the root directory:
```bash
# Optional: For AI Features
GEMINI_API_KEY=your_google_api_key_here
```

### 3. Run the System
```bash
python run.py
```
Access the app at `http://127.0.0.1:5000`.

## 📂 Project Structure
-   `app/ai_guardian.py`: The AI logic (Gemini + Heuristics).
-   `app/routes/`: Route controllers (Main, Auth).
-   `app/models.py`: Database schema (Player, Quest, Item).
-   `app/templates/`: UI Templates (Dashboard, Verification, etc.).
