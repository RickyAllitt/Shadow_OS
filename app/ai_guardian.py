import os
import json
import urllib.request
import re

class TheArchitect:
    """
    The System Administrator AI.
    Integrates with LLMs if available, falls back to Heuristics if not.
    Uses standard library 'urllib' to avoid external dependencies.
    """
    
    @staticmethod
    def _call_llm(prompt, json_mode=True):
        """Helper to call Gemini API using urllib."""
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return None
            
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            headers = {
                "Content-Type": "application/json"
            }
            
            system_prompt = "You are 'The Architect', a gamification system admin."
            if json_mode:
                system_prompt += " Output ONLY valid JSON."
                
            # Gemini Prompt Structure
            data = {
                "contents": [{
                    "parts": [{
                        "text": f"{system_prompt}\n\n{prompt}"
                    }]
                }]
            }
            
            # Encode data
            encoded_data = json.dumps(data).encode('utf-8')
            
            # Create Request
            req = urllib.request.Request(url, data=encoded_data, headers=headers, method='POST')
            
            # Execute
            with urllib.request.urlopen(req, timeout=15) as response:
                if response.status == 200:
                    response_body = response.read().decode('utf-8')
                    json_response = json.loads(response_body)
                    
                    # Gemini Response Parsing
                    content = json_response['candidates'][0]['content']['parts'][0]['text']
                    
                    # Clean potential markdown
                    content = content.replace("```json", "").replace("```", "").strip()
                    
                    if json_mode:
                        try:
                            return json.loads(content)
                        except json.JSONDecodeError:
                            return None
                    return content
                    
        except Exception as e:
            # Silently fail to fallback
            # print(f"⚠️ AI Error: {e}") 
            return None
            
        return None

    @staticmethod
    def _heuristic_analysis(title):
        """Offline analysis based on keywords."""
        title_lower = title.lower()
        
        stat = "INT" # Default
        rank = "E"
        xp = 10
        
        # Stat Heuristics
        if any(w in title_lower for w in ['run', 'gym', 'lift', 'sport', 'walk', 'pushup']):
            stat = "STR"
        elif any(w in title_lower for w in ['medit', 'focus', 'sleep', 'fast', 'yoga']):
            stat = "SEN" # Sense/Spirit
        elif any(w in title_lower for w in ['cook', 'eat', 'clean', 'health', 'water']):
            stat = "VIT"
        elif any(w in title_lower for w in ['cod', 'writ', 'study', 'read', 'learn']):
            stat = "INT"
        elif any(w in title_lower for w in ['pay', 'sched', 'email', 'call']):
            stat = "AGI" # Agility/Efficiency
            
        # Rank Heuristics
        if any(w in title_lower for w in ['marathon', 'exam', 'project', 'week', 'hard']):
            rank = "C"
            xp = 50
        if any(w in title_lower for w in ['final', 'thesis', 'launch']):
            rank = "B"
            xp = 100
            
        return {"rank": rank, "stat": stat, "xp": xp}

    @classmethod
    def analyze_quest(cls, title):
        """
        Determines Difficulty (Rank), Attribute (Stat), and XP.
        """
        # 1. Try LLM
        prompt = f"""
        Analyze the task: "{title}".
        Determine:
        1. Rank (E=Trivial, D=Easy, C=Medium, B=Hard, A=Very Hard, S=Impossible)
        2. Stat (STR=Physical, INT=Mental, VIT=Health, AGI=Speed, SEN=Discipline)
        3. XP (10-500)
        
        Return JSON: {{ "rank": "...", "stat": "...", "xp": ... }}
        """
        
        llm_result = cls._call_llm(prompt)
        # Validation
        if llm_result and all(k in llm_result for k in ['rank', 'stat']):
            if 'xp' not in llm_result: llm_result['xp'] = 50
            return llm_result
            
        # 2. Fallback
        return cls._heuristic_analysis(title)

    @classmethod
    def decompose_task(cls, title):
        """
        Breaks down a task into sub-tasks.
        """
        # 1. Try LLM
        prompt = f"""
        Break down the objective "{title}" into 3-5 concrete, actionable steps.
        Return ONLY a JSON list of strings. Example: ["Step 1", "Step 2"]
        """
        
        llm_result = cls._call_llm(prompt)
        if llm_result and isinstance(llm_result, list):
            return llm_result
            
        # 2. Fallback
        return [
            f"Research: {title}",
            f"Drafting: {title}",
            f"Execution: {title}",
            f"Review: {title}"
        ]
