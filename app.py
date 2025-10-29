from flask import Flask, request, jsonify, send_from_directory
import google.generativeai as genai
import os
import logging
from flask_cors import CORS
from dotenv import load_dotenv
import base64
import json
import tempfile
import time

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

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY not found in environment variables")
else:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        # Use Gemini 2.0 Flash for fast audio processing
        model = genai.GenerativeModel('gemini-2.0-flash')
        logging.info("Gemini API configured successfully with gemini-2.0-flash model")
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")

# Store active analysis sessions
active_sessions = {}

def check_api_status():
    """Verify Gemini API connectivity"""
    try:
        if not GEMINI_API_KEY:
            logging.error("GEMINI_API_KEY not found")
            return False
        
        try:
            # List available models
            logging.info("Checking available models...")
            models = genai.list_models()
            
            # Log models that support generateContent and audio
            audio_models = []
            for m in models:
                if 'generateContent' in m.supported_generation_methods:
                    logging.info(f"Available model: {m.name}")
                    # Check if model supports audio
                    if hasattr(m, 'supported_input_types'):
                        logging.info(f"  - Supported inputs: {m.supported_input_types}")
                        if 'audio' in str(m.supported_input_types).lower():
                            audio_models.append(m.name)
            
            if audio_models:
                logging.info(f"Models supporting audio: {audio_models}")
            
            logging.info("Successfully connected to Gemini API")
            return True
        except Exception as e:
            logging.error(f"API test failed: {e}")
            return False
            
    except Exception as e:
        logging.error(f"API connectivity test failed: {e}")
        return False

@app.route('/')
def home():
    """Serve the main application page"""
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logging.error(f"Error serving index.html: {e}")
        return f"Error loading page: {str(e)}", 500
    
@app.route('/style.css')
def serve_css():
    """Serve the CSS file"""
    return send_from_directory('.', 'style.css', mimetype='text/css')

@app.route('/script.js')
def serve_js():
    """Serve the JavaScript file"""
    return send_from_directory('.', 'script.js', mimetype='application/javascript')

@app.route('/api/check-status', methods=['GET'])
def check_status():
    """Check if API key is configured and working"""
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
    """Analyze emotion from audio chunk in real-time"""
    temp_file_path = None
    
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
        
        # Check minimum audio size (skip very small chunks)
        if len(audio_bytes) < 1000:
            logging.info("Audio chunk too small, skipping analysis")
            return jsonify({
                "skipped": True,
                "message": "Audio chunk too small"
            })
        
        # Save audio to temporary file
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                temp_file.write(audio_bytes)
                temp_file_path = temp_file.name
            
            logging.info(f"Audio chunk saved: {temp_file_path} ({len(audio_bytes)} bytes)")
        except Exception as file_error:
            logging.error(f"Error saving audio file: {file_error}")
            return jsonify({"error": "Failed to save audio file"}), 500
        
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
            # Upload and analyze
            logging.info(f"Processing chunk for session {session_id}...")
            
            # Upload file with retry
            max_retries = 2
            audio_file = None
            
            for attempt in range(max_retries):
                try:
                    audio_file = genai.upload_file(path=temp_file_path, mime_type="audio/webm")
                    logging.info(f"File uploaded: {audio_file.name}")
                    break
                except Exception as upload_error:
                    if attempt < max_retries - 1:
                        logging.warning(f"Upload attempt {attempt + 1} failed, retrying...")
                        time.sleep(0.5)
                    else:
                        raise upload_error
            
            if not audio_file:
                raise Exception("Failed to upload audio file")
            
            # Wait for file to be ready
            time.sleep(0.3)
            
            # Generate content
            response = model.generate_content(
                [audio_file, prompt],
                generation_config=genai.GenerationConfig(
                    temperature=0.4,
                    max_output_tokens=300,
                )
            )
            
            # Cleanup uploaded file immediately
            try:
                genai.delete_file(audio_file.name)
                logging.info(f"Deleted uploaded file: {audio_file.name}")
            except Exception as cleanup_error:
                logging.warning(f"Failed to delete uploaded file: {cleanup_error}")
            
        except Exception as api_error:
            error_msg = str(api_error)
            logging.error(f"Gemini API error: {error_msg}")
            
            # Provide more specific error messages
            if "400" in error_msg:
                if "invalid argument" in error_msg.lower():
                    return jsonify({
                        "error": "Invalid Request",
                        "message": "Audio format may be incompatible. Try refreshing the page.",
                        "details": error_msg
                    }), 503
            
            return jsonify({
                "error": "API Error",
                "message": "Unable to process audio analysis",
                "details": error_msg
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
            
            # Store in session (keep last 5 results for smoothing)
            if session_id not in active_sessions:
                active_sessions[session_id] = []
            
            active_sessions[session_id].append(result)
            if len(active_sessions[session_id]) > 5:
                active_sessions[session_id].pop(0)
            
            logging.info(f"Analysis complete: {result['emotion']} ({result['confidence']:.2f})")
            return jsonify(result)
            
        except (json.JSONDecodeError, ValueError) as parse_error:
            logging.error(f"Parse error: {parse_error}")
            logging.error(f"Response: {response_text}")
            return jsonify({
                "error": "Parse Error",
                "message": "Failed to parse response",
                "details": str(parse_error)
            }), 500
        
    except Exception as e:
        logging.error(f"Error analyzing emotion: {e}")
        return jsonify({
            "error": "Server Error",
            "message": str(e)
        }), 500
    
    finally:
        # Cleanup temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except Exception as cleanup_error:
                logging.warning(f"Failed to delete temporary file: {cleanup_error}")

@app.route('/api/end-session', methods=['POST'])
def end_session():
    """Clean up session data"""
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

if __name__ == '__main__':
    if not check_api_status():
        logging.warning("Gemini API is not properly configured or enabled")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
