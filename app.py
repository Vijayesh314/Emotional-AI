from flask import Flask, request, jsonify
import google.generativeai as genai
import tempfile
import os
import logging
from flask_cors import CORS
from dotenv import load_dotenv
import time
import json

load_dotenv()
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
CORS(app)

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.5-pro')

@app.route('/')
def home():
    try:
        with open('index.html', 'r') as f:
            return f.read()
    except Exception as e:
        logging.error(f"Error reading index.html: {e}")
        return f"Error loading page: {str(e)}", 500

@app.route('/analyze', methods=['POST'])
def analyze():
    video = request.files.get('video')
    audio = request.files.get('audio')
    text_prompt = request.form.get('text_prompt', '')

    results = {
        'video_emotions': [],
        'emotion_timeline': [],
        'body_language': '',
        'audio_analysis': {},
        'audio_feedback': {},
        'coaching_feedback': '',
        'strengths': [],
        'improvement_areas': [],
        'overall_score': 0,
        'professional_tips': []
    }

    prompt_parts = []

    # Process video
    if video:
        logging.info("Processing video...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_video:
            video_path = temp_video.name
            video.save(video_path)
        try:
            video_file = genai.upload_file(path=video_path, display_name="presentation_video")
            while video_file.state.name == "PROCESSING":
                time.sleep(1)
                video_file = genai.get_file(video_file.name)
            if video_file.state.name == "FAILED":
                raise ValueError("Video file processing failed.")
            prompt_parts.append(video_file)
            prompt_parts.append("Analyze this video for emotional expressions, body language, and presentation quality.")
        except Exception as e:
            logging.error(f"Video upload error: {e}")
            results['coaching_feedback'] = f"Video processing failed: {str(e)}"
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)

    # Process audio
    if audio:
        logging.info("Processing audio...")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            audio_path = temp_audio.name
            audio.save(audio_path)
        try:
            audio_file = genai.upload_file(path=audio_path, display_name="presentation_audio")
            while audio_file.state.name == "PROCESSING":
                time.sleep(1)
                audio_file = genai.get_file(audio_file.name)
            if audio_file.state.name == "FAILED":
                raise ValueError("Audio file processing failed.")
            prompt_parts.append(audio_file)
            prompt_parts.append("Analyze this audio for speaking pace, tone variation, confidence level, and vocal clarity.")
        except Exception as e:
            logging.error(f"Audio upload error: {e}")
            results['coaching_feedback'] = f"Audio processing failed: {str(e)}"
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)

    # Add user text prompt
    if text_prompt:
        prompt_parts.append(f"\nUser's specific question/context: {text_prompt}")

    # Construct JSON output request
    if prompt_parts:
        prompt_parts.append("""
        Please provide a comprehensive analysis in JSON format with these exact keys:
        {
            "video_emotions": ["list of detected emotions from video"],
            "emotion_timeline": [{"timestamp": 0.0, "emotion": "emotion_name", "confidence": 0.95}],
            "body_language": "analysis of posture, gestures, and non-verbal communication",
            "audio_feedback": {
                "pitch_analysis": "evaluation of pitch variation and appropriateness",
                "pace": "speaking pace assessment",
                "confidence_level": "vocal confidence rating 1-10",
                "areas_to_improve": ["list of specific audio improvements"]
            },
            "coaching_feedback": "personalized coaching advice based on all inputs",
            "strengths": ["list of presentation strengths"],
            "improvement_areas": ["specific areas needing work"],
            "overall_score": 85,
            "professional_tips": ["actionable tips for improvement"]
        }
        Be constructive, specific, and encouraging in your feedback. Focus on actionable improvements.
        """)

        try:
            response = model.generate_content(prompt_parts)
            response_text = response.text

            # Clean up response and extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            gemini_data = json.loads(response_text.strip())

            results.update({
                'video_emotions': gemini_data.get('video_emotions', []),
                'emotion_timeline': gemini_data.get('emotion_timeline', []),
                'body_language': gemini_data.get('body_language', ''),
                'audio_feedback': gemini_data.get('audio_feedback', {}),
                'coaching_feedback': gemini_data.get('coaching_feedback', ''),
                'strengths': gemini_data.get('strengths', []),
                'improvement_areas': gemini_data.get('improvement_areas', []),
                'overall_score': gemini_data.get('overall_score', 0),
                'professional_tips': gemini_data.get('professional_tips', [])
            })

            # Provide mock audio_analysis if audio exists but no detailed analysis
            if audio and not results.get('audio_analysis'):
                results['audio_analysis'] = {
                    'average_pitch': 150.0,
                    'intensity': 0.065,
                    'tempo': 120.0
                }

            logging.info("Gemini analysis completed successfully")

        except json.JSONDecodeError:
            logging.error("Failed to parse Gemini JSON output.")
            results['coaching_feedback'] = response.text
        except Exception as e:
            logging.error(f"Gemini API error: {e}")
            results['coaching_feedback'] = f"Analysis failed: {str(e)}"

    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True, port=5001, host='0.0.0.0')