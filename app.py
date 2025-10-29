from flask import Flask, request, jsonify, send_from_directory
import google.generativeai as genai
import os
import logging
from flask_cors import CORS
from dotenv import load_dotenv
import base64
import json
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import urllib3
import io
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)
# Update CORS configuration
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:5000"],
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type"]
    }
})

# Custom HTTP Adapter with SSL settings
class CustomHTTPAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = create_urllib3_context()
        kwargs['ssl_context'] = context
        return super(CustomHTTPAdapter, self).init_poolmanager(*args, **kwargs)

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY not found in environment variables")
else:
    try:
        # Configure Gemini API with the key
        genai.configure(api_key=GEMINI_API_KEY)

        # Create model instance
        model = genai.GenerativeModel("gemini-2.0-flash")
        logging.info("Gemini API configured successfully with gemini-2.0-flash")
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")

# Store active analysis sessions
active_sessions = {}
SESSION_TIMEOUT = timedelta(minutes=30)

def check_api_status():
    try:
        if not GEMINI_API_KEY:
            logging.error("GEMINI_API_KEY not found")
            return False
        
        # Test API connection
        test_response = model.generate_content("Test connection")
        if test_response:
            logging.info("Successfully connected to Gemini API")
            return True
        else:
            logging.error("Failed to get response from Gemini API")
            return False
            
    except Exception as e:
        logging.error(f"API connectivity test failed: {e}")
        return False

@app.route('/')
def home():
    # Serve the main application page
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logging.error(f"Error serving index.html: {e}")
        return f"Error loading page: {str(e)}", 500
    
@app.route('/style.css')
def serve_css():
    # Serve the CSS file
    return send_from_directory('.', 'style.css', mimetype='text/css')

@app.route('/script.js')
def serve_js():
    # Serve the JavaScript file
    return send_from_directory('.', 'script.js', mimetype='application/javascript')

@app.route('/api/check-status', methods=['GET'])
def check_status():
    # Check if API key is configured and working
    if not GEMINI_API_KEY:
        return jsonify({
            "configured": False,
            "message": "API key not configured"
        }), 500
    
    api_working = check_api_status()
    return jsonify({
        "configured": api_working,
        "message": "System ready" if api_working else "API connection failed"
    })

@app.route('/api/analyze-chunk', methods=['POST'])
def analyze_chunk():
    # Analyze emotion from audio chunk in real-time
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
        
        # Create concise prompt for faster response
        prompt = """
        Analyze the emotion in this audio. Be CONCISE and respond ONLY with valid JSON (no markdown):
        {
            "emotion": "one of: happy, sad, angry, fearful, surprised, neutral, confident, nervous, calm, frustrated, excited",
            "confidence": 0.0-1.0,
            "voice_features": {
                "pitch": "low/medium/high",
                "pace": "slow/moderate/fast",
                "energy": "low/moderate/high",
                "clarity": "poor/fair/good/excellent"
            },
            "analysis": "one brief sentence about the emotional state"
        }
        """
        
        try:
            # Upload and analyze with custom session
            audio_file = genai.upload_file(
                path=io.BytesIO(audio_bytes),
                mime_type="audio/webm"
            )
            
            # Generate analysis
            response = model.generate_content([audio_file, prompt])
        except Exception as api_error:
            logging.error(f"Gemini API error: {api_error}")
            return jsonify({
                "error": "API Error",
                "message": "Unable to process audio analysis",
                "details": str(api_error)
            }), 503
            
        # Parse response
        try:
            response_text = response.text.strip()
            
            # Extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            result = json.loads(response_text)
            
            # Validate structure
            if not all(key in result for key in ['emotion', 'confidence', 'voice_features', 'analysis']):
                raise ValueError("Invalid response structure")
            
            # Replace the session storage section in analyze_chunk
            # Store in session (keep last 5 results for smoothing)
            if session_id not in active_sessions:
                active_sessions[session_id] = {
                    'results': [],
                    'last_active': datetime.now()
                }
            else:
                active_sessions[session_id]['last_active'] = datetime.now()

            active_sessions[session_id]['results'].append(result)
            if len(active_sessions[session_id]['results']) > 5:
                active_sessions[session_id]['results'].pop(0)
            
            logging.info(f"Analysis complete: {result['emotion']} ({result['confidence']:.2f})")
            return jsonify(result)
            
        except json.JSONDecodeError as json_error:
            logging.error(f"Error parsing API response: {json_error}")
            return jsonify({
                "error": "Parse Error",
                "message": "Failed to parse API response",
                "details": str(json_error)
            }), 500
        
    except Exception as e:
        logging.error(f"Error analyzing emotion: {e}")
        return jsonify({
            "error": "Server Error",
            "message": "An unexpected error occurred",
            "details": str(e)
        }), 500

@app.route('/api/end-session', methods=['POST'])
def end_session():
    # Clean up session data
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
    # Remove expired sessions
    current_time = datetime.now()
    expired = []
    for session_id, session_data in active_sessions.items():
        if 'last_active' in session_data and current_time - session_data['last_active'] > SESSION_TIMEOUT:
            expired.append(session_id)
    
    for session_id in expired:
        del active_sessions[session_id]
        logging.info(f"Expired session removed: {session_id}")

if __name__ == '__main__':
    if not check_api_status():
        logging.warning("Gemini API is not properly configured or enabled")
    
    # Start session cleanup scheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanup_expired_sessions, "interval", minutes=15)
    scheduler.start()
    try:
        app.run(debug=True, host="0.0.0.0", port=5000)
    finally:
        scheduler.shutdown()
