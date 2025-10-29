from flask import Flask, request, jsonify, send_from_directory
import google.generativeai as genai
import os
import logging
from flask_cors import CORS
from dotenv import load_dotenv
import base64
import json
import io
import ssl
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        genai.configure(api_key=GEMINI_API_KEY)
        # Change to gemini-pro model instead of experimental
        model = genai.GenerativeModel('gemini-pro')
        logging.info("Gemini API configured successfully with gemini-pro model")
    except Exception as e:
        logging.error(f"Failed to configure Gemini API: {e}")

def check_api_status():
    """Verify Gemini API connectivity"""
    try:
        if not GEMINI_API_KEY:
            logging.error("GEMINI_API_KEY not found")
            return False
        
        # Test API connection with custom session
        session = requests.Session()
        session.mount('https://', CustomHTTPAdapter())
        
        response = session.get(
            'https://generativelanguage.googleapis.com/v1beta/models',
            params={'key': GEMINI_API_KEY},
            verify=False
        )
        
        if response.status_code == 200:
            logging.info("Successfully connected to Gemini API")
            return True
        elif response.status_code == 403:
            logging.error("API access denied. Check IP restrictions and API key permissions")
            return False
        else:
            logging.error(f"API test failed with status code: {response.status_code}")
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

@app.route('/api/analyze-emotion', methods=['POST'])
def analyze_emotion():
    """Analyze emotion from audio data"""
    try:
        # Validate request data
        data = request.json
        if not data or 'audio' not in data:
            return jsonify({"error": "No audio data provided"}), 400
        
        audio_data = data['audio']
        
        # Validate API configuration
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
        
        # Create analysis prompt
        prompt = """
        Analyze the emotional content of this audio recording. Provide a detailed analysis including:
        1. Primary emotion detected
        2. Confidence level (0-1)
        3. Voice features (pitch, pace, energy, clarity)
        4. Brief analysis of emotional indicators

        Return the results in the following JSON format:
        {
            "emotion": "detected_emotion",
            "confidence": confidence_score,
            "voice_features": {
                "pitch": "description",
                "pace": "description",
                "energy": "description",
                "clarity": "description"
            },
            "analysis": "detailed_analysis"
        }
        """
        
        try:
            # Process audio with custom session
            audio_file = genai.upload_file(
                path=io.BytesIO(audio_bytes),
                mime_type="audio/webm"
            )
            
            # Generate analysis
            response = model.generate_content([audio_file, prompt])
            
        except ssl.SSLError as ssl_error:
            logging.error(f"SSL Error: {ssl_error}")
            return jsonify({
                "error": "SSL Error",
                "message": "Failed to establish secure connection to API",
                "details": str(ssl_error)
            }), 503
        except Exception as api_error:
            logging.error(f"Gemini API error: {api_error}")
            return jsonify({
                "error": "API Error",
                "message": "Unable to process audio analysis",
                "details": str(api_error)
            }), 503
            
        # Parse response
        try:
            response_text = response.text
            
            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            result = json.loads(response_text.strip())
            logging.info(f"Emotion analysis result: {result}")
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

if __name__ == '__main__':
    # Initial API status check
    if not check_api_status():
        logging.warning("Gemini API is not properly configured or enabled")
    
    # Start Flask application
    app.run(debug=True, host='0.0.0.0', port=5000)
