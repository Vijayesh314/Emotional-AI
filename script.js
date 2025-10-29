// Global variables
let mediaRecorder
let audioContext
let analyser
let dataArray
let animationId
let isRecording = false
let audioChunks = []
let recordingStartTime
const emotionHistory = []

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

// Start recording
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })

    // Setup audio context for visualization
    audioContext = new (window.AudioContext || window.webkitAudioContext)()
    analyser = audioContext.createAnalyser()
    const source = audioContext.createMediaStreamSource(stream)
    source.connect(analyser)
    analyser.fftSize = 2048
    const bufferLength = analyser.frequencyBinCount
    dataArray = new Uint8Array(bufferLength)

    // Setup media recorder
    mediaRecorder = new MediaRecorder(stream)
    audioChunks = []

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data)
      }
    }

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: "audio/webm" })
      await analyzeEmotion(audioBlob)
    }

    mediaRecorder.start()
    isRecording = true
    recordingStartTime = Date.now()

    // Update UI
    startBtn.disabled = true
    stopBtn.disabled = false
    recordingStatus.classList.add("recording")
    recordingStatus.querySelector("span:last-child").textContent = "Recording..."
    resultsSection.classList.add("active")

    // Start visualization
    setupCanvas()
    drawWaveform()

    // Analyze every 3 seconds
    const analysisInterval = setInterval(() => {
      if (!isRecording) {
        clearInterval(analysisInterval)
        return
      }

      mediaRecorder.stop()
      setTimeout(() => {
        if (isRecording) {
          mediaRecorder.start()
          audioChunks = []
        }
      }, 100)
    }, 3000)
  } catch (error) {
    console.error("Error starting recording:", error)
    alert("Could not access microphone. Please check permissions.")
  }
}

// Stop recording
function stopRecording() {
  if (mediaRecorder && isRecording) {
    isRecording = false
    mediaRecorder.stop()

    if (audioContext) {
      audioContext.close()
    }

    if (animationId) {
      cancelAnimationFrame(animationId)
    }

    // Update UI
    startBtn.disabled = false
    stopBtn.disabled = true
    recordingStatus.classList.remove("recording")
    recordingStatus.querySelector("span:last-child").textContent = "Recording stopped"

    // Clear canvas
    canvasCtx.fillStyle = "rgba(26, 32, 44, 0.5)"
    canvasCtx.fillRect(0, 0, canvas.width, canvas.height)
  }
}

// Analyze emotion from audio
async function analyzeEmotion(audioBlob) {
  try {
    // Convert blob to base64
    const reader = new FileReader()
    reader.readAsDataURL(audioBlob)

    reader.onloadend = async () => {
      const base64Audio = reader.result

      const response = await fetch("/api/analyze-emotion", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ audio: base64Audio }),
      })

      if (!response.ok) {
        throw new Error("Analysis failed")
      }

      const result = await response.json()
      updateUI(result)
    }
  } catch (error) {
    console.error("Error analyzing emotion:", error)
  }
}

// Update UI with emotion results
function updateUI(result) {
  const { emotion, confidence, voice_features, analysis } = result

  // Update emotion indicator
  const indicator = document.getElementById("emotion-indicator")
  indicator.className = `emotion-indicator ${emotion}`
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
