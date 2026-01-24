import pytest
from unittest.mock import patch, MagicMock
from app.ai_guardian import TheArchitect
import json

def test_architect_analyze_heuristic(app):
    """Test analysis without API key (Heuristic Mode)."""
    with patch.dict('os.environ', {}, clear=True):
        # Case 1: INT/Study
        result = TheArchitect.analyze_quest("Study Algorithms")
        assert result['stat'] == 'INT'
        
        # Case 2: STR/Run
        result = TheArchitect.analyze_quest("Run 5km")
        assert result['stat'] == 'STR'

def test_architect_analyze_llm_success(app):
    """Test analysis WITH API key (Mock Gemini)."""
    # Gemini Structure
    mock_content = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": '{"rank": "B", "stat": "INT", "xp": 150}'}
                    ]
                }
            }
        ]
    }
    
    # Mock response object for urlopen
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_content).encode('utf-8')
    mock_response.status = 200
    
    # Context manager support
    mock_urlopen_context = MagicMock()
    mock_urlopen_context.__enter__.return_value = mock_response
    mock_urlopen_context.__exit__.return_value = None
    
    with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key'}):
        with patch('urllib.request.urlopen', return_value=mock_urlopen_context) as mock_urlopen:
            result = TheArchitect.analyze_quest("Build a complex backend")
            
            assert result['rank'] == 'B'
            assert result['stat'] == 'INT'
            assert result['xp'] == 150
            assert mock_urlopen.called

def test_architect_analyze_llm_failure_fallback(app):
    """Test API failure falls back to heuristic."""
    with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key'}):
        with patch('urllib.request.urlopen') as mock_urlopen:
            # Simulate an error (e.g., Exception during open)
            mock_urlopen.side_effect = Exception("API Down")
            
            # Should not crash, but return heuristic result
            result = TheArchitect.analyze_quest("Run 5km")
            assert result['stat'] == 'STR' # Fallback to keyword matching

def test_decompose_task_heuristic(app):
    """Test decomposition checks."""
    with patch.dict('os.environ', {}, clear=True):
        tasks = TheArchitect.decompose_task("Build an App")
        assert len(tasks) > 0

def test_decompose_task_llm(app):
    """Test decomposition with LLM (Gemini)."""
    mock_content_list = '["Design DB", "Setup Flask", "Create Frontend"]'
    mock_body = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": mock_content_list}
                    ]
                }
            }
        ]
    }
    
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(mock_body).encode('utf-8')
    mock_response.status = 200
    
    mock_urlopen_context = MagicMock()
    mock_urlopen_context.__enter__.return_value = mock_response
    mock_urlopen_context.__exit__.return_value = None
    
    with patch.dict('os.environ', {'GEMINI_API_KEY': 'fake-key'}):
        with patch('urllib.request.urlopen', return_value=mock_urlopen_context):
            tasks = TheArchitect.decompose_task("Build an App")
            assert len(tasks) == 3
            assert tasks[0] == "Design DB"
