from flask import Flask, request, jsonify, send_from_directory
import os
import logging
from flask_cors import CORS
from dotenv import load_dotenv
import base64
import json
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import requests
import subprocess
import tempfile

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

# Hume AI Configuration
HUME_API_KEY = os.getenv("HUME_API_KEY")  # Get free key from platform.hume.ai
HUME_API_URL = "https://api.hume.ai/v0/batch/jobs"

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
    
@app.route('/style.css')
def serve_css():
    return send_from_directory('.', 'style.css', mimetype='text/css')

@app.route('/script.js')
def serve_js():
    from datetime import datetime
    # Add cache busting
    return send_from_directory('.', 'script.js', mimetype='application/javascript'), {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }

@app.route('/api/check-status', methods=['GET'])
def check_status():
    if not HUME_API_KEY:
        return jsonify({
            "configured": False,
            "message": "Hume API key not configured"
        }), 500
    
    return jsonify({
        "configured": True,
        "message": "System ready"
    })

@app.route('/api/analyze-chunk', methods=['POST'])
def analyze_chunk():
    """Analyze emotion using Hume AI's Expression Measurement API"""
    try:
        data = request.json
        if not data or 'audio' not in data:
            return jsonify({"error": "No audio data provided"}), 400
        
        audio_data = data['audio']
        session_id = data.get('session_id', 'default')
        
        if not HUME_API_KEY:
            return jsonify({"error": "API key not configured"}), 500
        
        # Decode audio data
        try:
            audio_bytes = base64.b64decode(
                audio_data.split(',')[1] if ',' in audio_data else audio_data
            )
        except Exception as decode_error:
            logging.error(f"Error decoding audio data: {decode_error}")
            return jsonify({"error": "Invalid audio data format"}), 400
        
        try:
            # Audio should already be WAV from frontend
            logging.info(f"Received audio: {len(audio_bytes)} bytes")
            
            # Use Hume's Expression Measurement API
            url = "https://api.hume.ai/v0/batch/jobs"
            
            headers = {
                "X-Hume-Api-Key": HUME_API_KEY
            }
            
            files = {
                'file': ('audio.wav', audio_bytes, 'audio/wav')
            }
            
            # Request prosody analysis
            models_config = {
                "models": {
                    "prosody": {}
                }
            }
            
            data_payload = {
                'json': json.dumps(models_config)
            }
            
            # Submit the job
            response = requests.post(url, headers=headers, files=files, data=data_payload)
            
            if response.status_code != 200:
                logging.error(f"Hume API error: {response.status_code} - {response.text}")
                # Return neutral fallback
                return jsonify({
                    "emotion": "neutral",
                    "confidence": 0.5,
                    "voice_features": {
                        "pitch": "medium",
                        "pace": "moderate",
                        "energy": "moderate",
                        "clarity": "good"
                    },
                    "analysis": "Processing..."
                })
            
            job_data = response.json()
            job_id = job_data.get('job_id')
            
            if not job_id:
                raise Exception("No job_id returned from Hume API")
            
            # Poll for completion (with timeout)
            import time
            max_wait = 15  # Increase to 15 seconds
            check_interval = 0.8
            attempts = int(max_wait / check_interval)
            
            for i in range(attempts):
                time.sleep(check_interval)
                
                predictions_url = f"{url}/{job_id}/predictions"
                pred_response = requests.get(predictions_url, headers=headers)
                
                if pred_response.status_code == 400:
                    # Job not ready yet, continue polling
                    continue
                
                if pred_response.status_code == 200:
                    predictions_data = pred_response.json()
                    
                    # Debug: log the structure
                    if i == 0:
                        logging.debug(f"Response structure: {json.dumps(predictions_data, indent=2)[:500]}")
                    
                    # Check if we have results
                    if predictions_data and len(predictions_data) > 0:
                        result_item = predictions_data[0]
                        
                        # Navigate the response structure
                        results = result_item.get('results', {})
                        predictions_list = results.get('predictions', [])
                        
                        if predictions_list and len(predictions_list) > 0:
                            first_prediction = predictions_list[0]
                            models_data = first_prediction.get('models', {})
                            prosody_data = models_data.get('prosody', {})
                            grouped = prosody_data.get('grouped_predictions', [])
                            
                            if grouped and len(grouped) > 0:
                                emotions_list = grouped[0].get('predictions', [])
                                
                                if emotions_list and len(emotions_list) > 0:
                                    # Sort by confidence
                                    emotions_list.sort(key=lambda x: x.get('score', 0), reverse=True)
                                    
                                    top_emotion = emotions_list[0]
                                    emotion_name = top_emotion.get('name', 'neutral').lower()
                                    score = top_emotion.get('score', 0.5)
                                    
                                    # Map Hume emotions to our UI emotions
                                    emotion_map = {
                                        'admiration': 'happy',
                                        'adoration': 'happy',
                                        'aesthetic appreciation': 'calm',
                                        'amusement': 'happy',
                                        'anger': 'angry',
                                        'anxiety': 'nervous',
                                        'awe': 'surprised',
                                        'awkwardness': 'nervous',
                                        'boredom': 'neutral',
                                        'calmness': 'calm',
                                        'concentration': 'confident',
                                        'confusion': 'neutral',
                                        'contemplation': 'calm',
                                        'contempt': 'frustrated',
                                        'contentment': 'calm',
                                        'craving': 'excited',
                                        'determination': 'confident',
                                        'disappointment': 'sad',
                                        'disgust': 'frustrated',
                                        'distress': 'fearful',
                                        'doubt': 'nervous',
                                        'ecstasy': 'excited',
                                        'embarrassment': 'nervous',
                                        'empathic pain': 'sad',
                                        'entrancement': 'surprised',
                                        'excitement': 'excited',
                                        'fear': 'fearful',
                                        'guilt': 'sad',
                                        'horror': 'fearful',
                                        'interest': 'confident',
                                        'joy': 'happy',
                                        'love': 'happy',
                                        'nostalgia': 'calm',
                                        'pain': 'sad',
                                        'pride': 'confident',
                                        'realization': 'surprised',
                                        'relief': 'calm',
                                        'romance': 'happy',
                                        'sadness': 'sad',
                                        'satisfaction': 'calm',
                                        'desire': 'excited',
                                        'shame': 'sad',
                                        'surprise (negative)': 'surprised',
                                        'surprise (positive)': 'surprised',
                                        'sympathy': 'calm',
                                        'tiredness': 'neutral',
                                        'triumph': 'confident'
                                    }
                                    
                                    mapped_emotion = emotion_map.get(emotion_name, 'neutral')
                                    
                                    # Analyze voice features from top emotions
                                    energy_emotions = ['excitement', 'anger', 'joy', 'triumph']
                                    calm_emotions = ['calmness', 'contentment', 'relief']
                                    
                                    energy_level = "high" if emotion_name in energy_emotions else (
                                        "low" if emotion_name in calm_emotions else "moderate"
                                    )
                                    
                                    result = {
                                        "emotion": mapped_emotion,
                                        "confidence": min(score, 1.0),
                                        "voice_features": {
                                            "pitch": "high" if score > 0.7 else "medium",
                                            "pace": "fast" if energy_level == "high" else "moderate",
                                            "energy": energy_level,
                                            "clarity": "excellent" if score > 0.6 else "good"
                                        },
                                        "analysis": f"Voice analysis detected {mapped_emotion} emotion (original: {emotion_name})"
                                    }
                                    
                                    # Store in session
                                    if session_id not in active_sessions:
                                        active_sessions[session_id] = {
                                            'results': [],
                                            'last_active': datetime.now()
                                        }
                                    
                                    active_sessions[session_id]['last_active'] = datetime.now()
                                    active_sessions[session_id]['results'].append(result)
                                    
                                    if len(active_sessions[session_id]['results']) > 5:
                                        active_sessions[session_id]['results'].pop(0)
                                    
                                    logging.info(f"Emotion detected: {mapped_emotion} ({score:.2f}) from {emotion_name}")
                                    return jsonify(result)
            
            # Timeout - return neutral
            logging.warning("Analysis timed out, returning neutral")
            return jsonify({
                "emotion": "neutral",
                "confidence": 0.5,
                "voice_features": {
                    "pitch": "medium",
                    "pace": "moderate", 
                    "energy": "moderate",
                    "clarity": "good"
                },
                "analysis": "Analysis is still processing..."
            })
                
        except Exception as api_error:
            logging.error(f"Hume API processing error: {api_error}")
            return jsonify({
                "emotion": "neutral",
                "confidence": 0.5,
                "voice_features": {
                    "pitch": "medium",
                    "pace": "moderate",
                    "energy": "moderate",
                    "clarity": "good"
                },
                "analysis": f"Error: {str(api_error)}"
            })
        
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

if __name__ == '__main__':
    if not HUME_API_KEY:
        logging.warning("HUME_API_KEY not configured! Get one from platform.hume.ai")
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanup_expired_sessions, "interval", minutes=15)
    scheduler.start()
    try:
        app.run(debug=True, host="0.0.0.0", port=5000)
    finally:
        scheduler.shutdown()
