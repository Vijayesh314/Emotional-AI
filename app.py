from flask import Flask, request, jsonify, send_from_directory
import os
import logging
from flask_cors import CORS
from dotenv import load_dotenv
import base64
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import google.generativeai as genai

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Gemini AI Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Store active analysis sessions
active_sessions = {}
SESSION_TIMEOUT = timedelta(minutes=30)

@app.route('/')
def home():
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logging.error(f"Error serving index.html: {e}")
        return f"Error loading page: {str(e)}", 500
    
@app.route('/login.html')
def login():
    try:
        return send_from_directory('.', 'login.html')
    except Exception as e:
        logging.error(f"Error serving login.html: {e}")
        return f"Error loading page: {str(e)}", 500
    
@app.route('/style.css')
def serve_css():
    return send_from_directory('.', 'style.css', mimetype='text/css')

@app.route('/script.js')
def serve_js():
    return send_from_directory('.', 'script.js', mimetype='text/javascript')

@app.route('/api/check-status')
def check_status():
    return jsonify({"configured": bool(GEMINI_API_KEY)})

@app.route('/api/analyze-chunk', methods=['POST'])
def analyze_chunk():
    # Analyze emotion using Gemini's multimodal capabilities
    try:
        data = request.json
        if not data or 'audio' not in data:
            return jsonify({"error": "No audio data provided"}), 400
        
        audio_data = data['audio']
        session_id = data.get('session_id', 'default')
        
        if not GEMINI_API_KEY:
            return jsonify({"error": "API key not configured"}), 500
        
        # Decode audio data
        try:
            audio_bytes = base64.b64decode(
                audio_data.split(',')[1] if ',' in audio_data else audio_data
            )
        except Exception as decode_error:
            logging.error(f"Error decoding audio data: {decode_error}")
            return jsonify({"error": "Invalid audio data format"}), 400
        
        # Define the emotion mapping
        emotion_map = {
            'happy': 'happy', 'joyful': 'happy', 'pleased': 'happy', 'cheerful': 'happy',
            'sad': 'sad', 'unhappy': 'sad', 'sorrowful': 'sad', 'melancholy': 'sad',
            'angry': 'angry', 'frustrated': 'frustrated', 'irritated': 'frustrated',
            'fearful': 'fearful', 'afraid': 'fearful', 'anxious': 'nervous', 'worried': 'nervous',
            'surprised': 'surprised', 'shocked': 'surprised', 'amazed': 'surprised',
            'neutral': 'neutral', 'calm': 'calm', 'relaxed': 'calm', 'peaceful': 'calm',
            'confident': 'confident', 'assured': 'confident', 'certain': 'confident',
            'nervous': 'nervous', 'tense': 'nervous', 'uneasy': 'nervous',
            'excited': 'excited', 'enthusiastic': 'excited', 'energetic': 'excited'
        }
        
        default_result = {
            "emotion": "neutral",
            "confidence": 0.5,
            "voice_features": {
                "pitch": "medium",
                "pace": "moderate", 
                "energy": "moderate",
                "clarity": "good"
            },
            "analysis": "Could not analyze audio. Please ensure clear speech is present."
        }
        
        try:
            logging.info(f"Received audio: {len(audio_bytes)} bytes")
            
            # Initialize Gemini model (using gemini-2.0-flash)
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # Prepare audio for Gemini
            audio_part = {
                'mime_type': 'audio/wav',
                'data': audio_bytes
            }
            
            # Create a detailed prompt for emotion analysis
            prompt = """Analyze the emotional content of this audio clip. 
            
            Provide your analysis in the following JSON format:
            {
                "primary_emotion": "the main emotion detected (e.g., happy, sad, angry, fearful, surprised, neutral, calm, confident, nervous, excited, frustrated)",
                "confidence": a number between 0 and 1 indicating confidence,
                "voice_characteristics": {
                    "pitch": "high, medium, or low",
                    "pace": "fast, moderate, or slow",
                    "energy": "high, moderate, or low",
                    "clarity": "excellent, good, fair, or poor"
                },
                "explanation": "brief explanation of the detected emotion and vocal patterns"
            }
            
            Focus on vocal prosody, tone, pitch, pace, and energy levels to determine the emotion.
            If no clear speech is detected, return neutral emotion with low confidence."""
            
            # Generate content with timeout
            response = model.generate_content(
                [prompt, audio_part],
                request_options={'timeout': 30}
            )
            
            # Parse the response
            response_text = response.text.strip()
            logging.info(f"Gemini response: {response_text}")
            
            # Try to extract JSON from the response
            # Gemini might wrap JSON in markdown code blocks
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end].strip()
            
            try:
                analysis = json.loads(response_text)
            except json.JSONDecodeError:
                logging.warning(f"Could not parse JSON, using default result")
                return jsonify(default_result)
            
            # Extract emotion and map it
            primary_emotion = analysis.get('primary_emotion', 'neutral').lower()
            mapped_emotion = emotion_map.get(primary_emotion, 'neutral')
            
            confidence = float(analysis.get('confidence', 0.5))
            voice_chars = analysis.get('voice_characteristics', {})
            explanation = analysis.get('explanation', 'Emotion detected from voice analysis')
            
            result = {
                "emotion": mapped_emotion,
                "confidence": min(max(confidence, 0.0), 1.0),
                "voice_features": {
                    "pitch": voice_chars.get('pitch', 'medium'),
                    "pace": voice_chars.get('pace', 'moderate'),
                    "energy": voice_chars.get('energy', 'moderate'),
                    "clarity": voice_chars.get('clarity', 'good')
                },
                "analysis": explanation
            }
            
            # Store in session
            if session_id not in active_sessions:
                active_sessions[session_id] = {'results': [], 'last_active': datetime.now()}
            
            active_sessions[session_id]['last_active'] = datetime.now()
            active_sessions[session_id]['results'].append(result)
            
            if len(active_sessions[session_id]['results']) > 5:
                active_sessions[session_id]['results'].pop(0)
            
            logging.info(f"Emotion detected: {mapped_emotion} ({confidence:.2f})")
            return jsonify(result)
                
        except Exception as api_error:
            logging.error(f"Gemini API processing error: {api_error}")
            default_result["analysis"] = f"Error: {str(api_error)}"
            return jsonify(default_result)
        
    except Exception as e:
        logging.error(f"Error analyzing emotion: {e}")
        return jsonify({
            "error": "Server Error",
            "message": str(e)
        }), 500
    
@app.route('/api/end-session', methods=['POST'])
def end_session():
    try:
        data = request.json
        session_id = data.get('session_id', 'default')
        
        if session_id in active_sessions:
            del active_sessions[session_id]
            logging.info(f"Session {session_id} ended")
        
        return jsonify({"message": "Session ended"})
    except Exception as e:
        logging.error(f"Error ending session: {e}")
        return jsonify({"error": str(e)}), 500
    
def cleanup_expired_sessions():
    current_time = datetime.now()
    expired = []
    for session_id, session_data in active_sessions.items():
        if 'last_active' in session_data and current_time - session_data['last_active'] > SESSION_TIMEOUT:
            expired.append(session_id)
    
    for session_id in expired:
        del active_sessions[session_id]
        logging.info(f"Expired session removed: {session_id}")

# Start the background scheduler for session cleanup
scheduler = BackgroundScheduler()
scheduler.add_job(cleanup_expired_sessions, 'interval', minutes=15)
scheduler.start()

if __name__ == '__main__':
    if not GEMINI_API_KEY:
        logging.warning("GEMINI_API_KEY not configured! Get one from https://aistudio.google.com/app/apikey")
    
    print(f"Local access: http://localhost:5000/")
    print(f"Login page:   http://localhost:5000/login.html")
    print(f"Main app:     http://localhost:5000/")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
