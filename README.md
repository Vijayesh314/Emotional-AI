# Emotional-AI
Live feedback for audio to judge how a person is feeling on call to analyze their emotions and act accordingly. Potential use cases include in healthcare in order to find out if a person is nervous, and in business with investors.

## How it works
* Recording starts
* Every 2 seconds chunk is captured
* API analyzes it
* Updates UI with feedback
* Continue recording (loop)

## Why it matters
* In tele-health and remote therapy settings, clinicians may not notice subtle anxiety, distress or disengagement when only voice is available, so this tool adds an extra layer of emotional awareness
* In business, sales, investor-calls or negotiations, presenters can monitor how their audience (or themselves) are feeling and adjust their tone, pacing or content accordingly
* In remote or hybrid interactions, where visual cues are limited, voice is the main means of communication, so tracking emotion via audio becomes especially valuable

## Tech Stack
* Backend: Python Flask for robust and manageable backend server along with Javascript for various functions
* Emotion Detection: Emotion detected using a AI model, allowing us to analyze voice audio
* AI Model: The API key utilizes gemini's 2.0 flash as our core AI model to provide human-like feedback
* Frontend: The user interface was built using HTML/CSS and JSON for a responsive experience

## Usage
* Make sure your browser allows microphone access with no interruptions or delays in the microphone
* Be close to the computer so that the microphone can properly hear and track your voice
