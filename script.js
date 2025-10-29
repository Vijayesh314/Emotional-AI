// Global variables
let mediaRecorder
let audioContext
let analyser
let dataArray
let animationId
let isRecording = false
let recordingStartTime
let sessionId
let analysisQueue = []
let isAnalyzing = false
const emotionHistory = []

// Configuration
const CHUNK_DURATION = 3000 // Increased to 3 seconds to reduce API load
const MIN_CHUNK_SIZE = 5000 // Increased minimum size
const MAX_CONCURRENT_ANALYSIS = 1 // Only process one at a time

// DOM elements
const startBtn = document.getElementById("startBtn")
const stopBtn = document.getElementById("stopBtn")
const statusIndicator = document.getElementById("status-indicator")
const recordingStatus = document.getElementById("recording-status")
const resultsSection = document.getElementById("results-section")
const canvas = document.getElementById("waveform")
const canvasCtx = canvas.getContext("2d")

// Check API status on load
async function checkStatus() {
  try {
    const response = await fetch("/api/check-status")
    const data = await response.json()

    if (data.configured) {
      statusIndicator.classList.add("ready")
      statusIndicator.querySelector(".status-text").textContent = "System Ready"
    } else {
      statusIndicator.classList.add("error")
      statusIndicator.querySelector(".status-text").textContent = "API Key Missing"
      startBtn.disabled = true
    }
  } catch (error) {
    console.error("Status check failed:", error)
    statusIndicator.classList.add("error")
    statusIndicator.querySelector(".status-text").textContent = "Connection Error"
    startBtn.disabled = true
  }
}

// Handle API errors
async function handleApiError(error) {
    console.error("API Error:", error);
    statusIndicator.classList.add("error");
    statusIndicator.querySelector(".status-text").textContent = "API Error";
    startBtn.disabled = true;
    alert("Error connecting to the API. Please check the console for details.");
}

// Initialize audio visualization
function setupCanvas() {
  canvas.width = canvas.offsetWidth
  canvas.height = canvas.offsetHeight
}

// Draw waveform
function drawWaveform() {
  if (!isRecording) return

  animationId = requestAnimationFrame(drawWaveform)

  analyser.getByteTimeDomainData(dataArray)

  canvasCtx.fillStyle = "rgba(26, 32, 44, 0.5)"
  canvasCtx.fillRect(0, 0, canvas.width, canvas.height)

  canvasCtx.lineWidth = 2
  canvasCtx.strokeStyle = "#667eea"
  canvasCtx.beginPath()

  const sliceWidth = canvas.width / dataArray.length
  let x = 0

  for (let i = 0; i < dataArray.length; i++) {
    const v = dataArray[i] / 128.0
    const y = (v * canvas.height) / 2

    if (i === 0) {
      canvasCtx.moveTo(x, y)
    } else {
      canvasCtx.lineTo(x, y)
    }

    x += sliceWidth
  }

  canvasCtx.lineTo(canvas.width, canvas.height / 2)
  canvasCtx.stroke()
}

// Process audio chunk
async function processAudioChunk(audioBlob) {
  // Add to queue
  analysisQueue.push(audioBlob)
  
  // Process queue if not already processing
  if (!isAnalyzing) {
    processQueue()
  }
}

// Process analysis queue
async function processQueue() {
  if (analysisQueue.length === 0) {
    isAnalyzing = false
    return
  }
  
  isAnalyzing = true
  const audioBlob = analysisQueue.shift()
  
  // Skip if blob is too small
  if (audioBlob.size < MIN_CHUNK_SIZE) {
    console.log(`Skipping small chunk (${audioBlob.size} bytes)`)
    setTimeout(() => processQueue(), 100)
    return
  }
  
  try {
    // Convert blob to base64
    const reader = new FileReader()
    
    reader.onloadend = async () => {
      try {
        const base64Audio = reader.result
        
        // Show analyzing indicator
        updateStatusText("Analyzing...")
        
        const response = await fetch("/api/analyze-chunk", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ 
            audio: base64Audio,
            session_id: sessionId
          }),
        })

        if (response.ok) {
          const result = await response.json()
          
          if (!result.skipped) {
            updateUI(result)
            updateStatusText(`Recording... (${result.emotion} detected)`)
          } else {
            updateStatusText("Recording...")
          }
        } else {
          const errorData = await response.json()
          console.error("Analysis failed:", errorData)
          updateStatusText("Recording... (analysis error)")
          
          // Clear queue on persistent errors to prevent backup
          if (analysisQueue.length > 3) {
            console.warn("Clearing analysis queue due to errors")
            analysisQueue = []
          }
        }
      } catch (error) {
        console.error("Error analyzing chunk:", error)
        updateStatusText("Recording... (error)")
      } finally {
        // Wait before processing next to avoid rate limits
        setTimeout(() => processQueue(), 500)
      }
    }
    
    reader.readAsDataURL(audioBlob)
  } catch (error) {
    console.error("Error processing chunk:", error)
    setTimeout(() => processQueue(), 500)
  }
}

// Update status text
function updateStatusText(text) {
  const statusSpan = recordingStatus.querySelector("span:last-child")
  statusSpan.textContent = text
  
  // Add analyzing indicator
  if (text.includes("Analyzing")) {
    statusSpan.style.color = "#f6ad55"
  } else if (text.includes("error")) {
    statusSpan.style.color = "#fc8181"
  } else {
    statusSpan.style.color = ""
  }
}

// Start recording
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      } 
    })

    // Setup audio context for visualization
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
    analyser = audioContext.createAnalyser()
    const source = audioContext.createMediaStreamSource(stream)
    source.connect(analyser)
    analyser.fftSize = 2048
    const bufferLength = analyser.frequencyBinCount
    dataArray = new Uint8Array(bufferLength)

    // Setup media recorder with time slicing
    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus'
    })
    
    // Generate session ID
    sessionId = `session_${Date.now()}`
    
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > MIN_CHUNK_SIZE) {
        // Process this chunk
        processAudioChunk(event.data)
      }
    }

    // Start recording with time slicing (get chunks automatically)
    mediaRecorder.start(CHUNK_DURATION)
    isRecording = true
    recordingStartTime = Date.now()

    // Update UI
    startBtn.disabled = true
    stopBtn.disabled = false
    recordingStatus.classList.add("recording")
    updateStatusText("Recording... initializing")
    resultsSection.classList.add("active")

    // Start visualization
    setupCanvas()
    drawWaveform()

    console.log("Recording started with real-time analysis")
  } catch (error) {
    console.error("Error starting recording:", error)
    alert("Could not access microphone. Please check permissions.")
  }
}

// Stop recording
async function stopRecording() {
  if (mediaRecorder && isRecording) {
    isRecording = false
    
    // Stop media recorder
    mediaRecorder.stop()
    
    // Stop all tracks
    if (mediaRecorder.stream) {
      mediaRecorder.stream.getTracks().forEach(track => track.stop())
    }

    if (audioContext) {
      audioContext.close()
    }

    if (animationId) {
      cancelAnimationFrame(animationId)
    }

    // End session
    try {
      await fetch("/api/end-session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ session_id: sessionId }),
      })
    } catch (error) {
      console.error("Error ending session:", error)
    }

    // Update UI
    startBtn.disabled = false
    stopBtn.disabled = true
    recordingStatus.classList.remove("recording")
    updateStatusText("Recording stopped")

    // Clear canvas
    canvasCtx.fillStyle = "rgba(26, 32, 44, 0.5)"
    canvasCtx.fillRect(0, 0, canvas.width, canvas.height)
    
    console.log("Recording stopped")
  }
}

// Update UI with emotion results
function updateUI(result) {
  const { emotion, confidence, voice_features, analysis } = result

  // Update emotion indicator
  const indicator = document.getElementById("emotion-indicator")
  indicator.className = `emotion-indicator ${emotion}`
  
  // Update emoji based on emotion
  const emojiMap = {
    happy: "😊",
    sad: "😢",
    angry: "😠",
    fearful: "😨",
    surprised: "😲",
    neutral: "😐",
    confident: "😎",
    nervous: "😰",
    calm: "😌",
    frustrated: "😤",
    excited: "🤩"
  }
  
  indicator.querySelector(".emotion-icon").textContent = emojiMap[emotion] || "😐"
  indicator.querySelector(".emotion-label").textContent = emotion
  indicator.querySelector(".emotion-confidence").textContent = `${Math.round(confidence * 100)}% confidence`

  // Update analysis text
  document.getElementById("emotion-analysis-text").textContent = analysis

  // Update voice features
  document.getElementById("pitch-value").textContent = voice_features.pitch
  document.getElementById("pace-value").textContent = voice_features.pace
  document.getElementById("energy-value").textContent = voice_features.energy
  document.getElementById("clarity-value").textContent = voice_features.clarity

  // Add to timeline
  const timestamp = new Date().toLocaleTimeString()
  emotionHistory.unshift({ timestamp, emotion, confidence })

  // Keep only last 10 entries
  if (emotionHistory.length > 10) {
    emotionHistory.pop()
  }

  updateTimeline()
}

// Update emotion timeline
function updateTimeline() {
  const timeline = document.getElementById("emotion-timeline")

  if (emotionHistory.length === 0) {
    timeline.innerHTML = '<p class="timeline-empty">No data yet. Start recording to see your emotion timeline.</p>'
    return
  }

  timeline.innerHTML = emotionHistory
    .map(
      (item) => `
        <div class="timeline-item">
            <div class="timeline-time">${item.timestamp}</div>
            <div class="timeline-emotion">${item.emotion}</div>
            <div class="timeline-confidence">${Math.round(item.confidence * 100)}%</div>
        </div>
    `,
    )
    .join("")
}

// Event listeners
startBtn.addEventListener("click", startRecording)
stopBtn.addEventListener("click", stopRecording)
window.addEventListener("resize", setupCanvas)

// Initialize
checkStatus()
setupCanvas()
