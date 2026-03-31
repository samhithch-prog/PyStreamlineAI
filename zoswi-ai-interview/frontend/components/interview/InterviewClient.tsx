"use client";

import { useEffect, useRef, useState } from "react";

import {
  createWebSocketToken,
  exchangeStreamlitLaunchToken,
  getClientAccessToken,
  getInterviewResult,
  getInterviewWebSocketUrl,
  startInterview as startInterviewSession
} from "../../lib/api";
import type { EvaluationSignals, InterviewResultResponse, TranscriptMessage } from "../../lib/types";

import { CameraPreview } from "./CameraPreview";
import { EvaluationPanel } from "./EvaluationPanel";
import { TimerBar } from "./TimerBar";

type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "listening"
  | "thinking"
  | "speaking"
  | "completed"
  | "closed";

type InterviewType = "mixed" | "technical" | "behavioral";
const AUTH_RESOLVE_TIMEOUT_MS = 45000;

function getRecorderMimeCandidates() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.filter((candidate) => {
    try {
      return MediaRecorder.isTypeSupported(candidate);
    } catch {
      return false;
    }
  });
}

function blobToBase64(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Unable to encode audio blob."));
    reader.onloadend = () => {
      const dataUrl = String(reader.result || "");
      const commaIndex = dataUrl.indexOf(",");
      if (commaIndex < 0) {
        reject(new Error("Invalid audio encoding payload."));
        return;
      }
      resolve(dataUrl.slice(commaIndex + 1));
    };
    reader.readAsDataURL(blob);
  });
}

function base64ToArrayBuffer(base64: string) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function getErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "Unexpected error occurred.";
}

function clearClientAccessToken() {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem("zoswi_access_token");
}

function isAuthFailureMessage(message: string) {
  const lowered = String(message || "").toLowerCase();
  return (
    lowered.includes("missing bearer token") ||
    lowered.includes("invalid token") ||
    lowered.includes("token expired") ||
    lowered.includes("unauthorized") ||
    lowered.includes("401")
  );
}

function normalizeInterviewType(rawValue: string | null | undefined): InterviewType {
  const cleaned = String(rawValue || "")
    .trim()
    .toLowerCase();
  if (cleaned === "technical") {
    return "technical";
  }
  if (cleaned === "behavioral" || cleaned === "behavioural") {
    return "behavioral";
  }
  return "mixed";
}

export function InterviewClient() {
  const [authChecked, setAuthChecked] = useState(false);
  const [hasAccessToken, setHasAccessToken] = useState(false);
  const [candidateName, setCandidateName] = useState("");
  const [role, setRole] = useState("Software Engineer");
  const [interviewType, setInterviewType] = useState<InterviewType>("mixed");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("idle");
  const [isLive, setIsLive] = useState(false);
  const [statusMessage, setStatusMessage] = useState("Enter your details to begin a live voice interview.");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [currentQuestion, setCurrentQuestion] = useState<string>("");
  const [transcripts, setTranscripts] = useState<TranscriptMessage[]>([]);
  const [signals, setSignals] = useState<EvaluationSignals | null>(null);
  const [durationLeft, setDurationLeft] = useState(0);
  const [totalDuration, setTotalDuration] = useState(0);
  const [maxTurns, setMaxTurns] = useState(5);
  const [tabSwitchWarnings, setTabSwitchWarnings] = useState(0);
  const [focusLossWarnings, setFocusLossWarnings] = useState(0);
  const [cameraDropWarnings, setCameraDropWarnings] = useState(0);
  const [facePresenceWarnings, setFacePresenceWarnings] = useState(0);
  const [cameraEnabled, setCameraEnabled] = useState(true);
  const strictProctorMode = true;
  const integritySignalLimit = 2;
  const [copiedSession, setCopiedSession] = useState(false);
  const [cameraPreviewStream, setCameraPreviewStream] = useState<MediaStream | null>(null);
  const [cameraWarningMessage, setCameraWarningMessage] = useState<string | null>(null);
  const [, setFaceGuardMode] = useState<"native" | "mediapipe" | "mediapipe-loading" | "fallback">(
    "mediapipe-loading"
  );
  const [activeSpeaker, setActiveSpeaker] = useState<"ai" | "candidate" | "none">("none");
  const [finalResult, setFinalResult] = useState<InterviewResultResponse | null>(null);

  useEffect(() => {
    let isMounted = true;
    const resolveAccess = async () => {
      let token = "";
      let launchAuthFailureMessage = "";
      try {
        token = getClientAccessToken();
      } catch {
        clearClientAccessToken();
        token = "";
      }

      try {
        const params = new URLSearchParams(window.location.search);
        const launchToken = String(params.get("launch_token") || params.get("amp;launch_token") || "").trim();
        if (launchToken) {
          try {
            const launchResponse = (await Promise.race([
              exchangeStreamlitLaunchToken(launchToken),
              new Promise<never>((_, reject) => {
                setTimeout(() => reject(new Error("Launch auth check timed out.")), AUTH_RESOLVE_TIMEOUT_MS);
              })
            ])) as Awaited<ReturnType<typeof exchangeStreamlitLaunchToken>>;
            const accessToken = String(launchResponse.access_token || "").trim();
            if (accessToken) {
              window.localStorage.setItem("zoswi_access_token", accessToken);
              token = accessToken;
            } else if (!token) {
              clearClientAccessToken();
              token = "";
            }
            params.delete("launch_token");
            params.delete("amp;launch_token");
            const nextQuery = params.toString();
            const nextUrl = `${window.location.pathname}${nextQuery ? `?${nextQuery}` : ""}`;
            window.history.replaceState({}, "", nextUrl);
          } catch (error) {
            launchAuthFailureMessage = getErrorMessage(error);
            if (!token) {
              clearClientAccessToken();
              token = "";
            }
          }
        }
      } catch {
        if (!token) {
          clearClientAccessToken();
          token = "";
        }
      } finally {
        if (!isMounted) {
          return;
        }
        const authenticated = token.length > 0;
        setHasAccessToken(authenticated);
        setAuthChecked(true);
        if (!authenticated) {
          const launchFailure = String(launchAuthFailureMessage || "").trim();
          if (launchFailure) {
            setStatusMessage(`Access restricted. ${launchFailure}`);
            setErrorMessage(`Login required. ${launchFailure}`);
          } else {
            setStatusMessage("Access restricted. Open interview only from your ZoSwi dashboard.");
            setErrorMessage("Login required. This interview room is available only for authenticated users.");
          }
        } else {
          setErrorMessage(null);
        }
      }
    };
    void resolveAccess();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const candidateFromQuery = String(params.get("candidate") || "").trim();
      const roleFromQuery = String(params.get("role") || "").trim();
      const typeFromQuery = normalizeInterviewType(params.get("type"));

      if (candidateFromQuery) {
        setCandidateName(candidateFromQuery.slice(0, 200));
      }
      if (roleFromQuery) {
        setRole(roleFromQuery.slice(0, 200));
      }
      setInterviewType(typeFromQuery);
    } catch {
      // Ignore malformed query params.
    }
  }, []);

  const websocketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const previewStreamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const aiAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const faceDetectionVideoRef = useRef<HTMLVideoElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const connectionStatusRef = useRef<ConnectionStatus>("idle");
  const activeSpeakerRef = useRef<"ai" | "candidate" | "none">("none");
  const voiceHeardThisTurnRef = useRef(false);
  const lastVoiceAtRef = useRef<number>(0);
  const turnEndingRef = useRef(false);
  const hasTurnAudioRef = useRef(false);
  const turnAudioBlobRef = useRef<Blob | null>(null);
  const recordingStartedAtRef = useRef<number>(0);
  const strictActionTriggeredRef = useRef(false);
  const cameraWarningMessageRef = useRef<string | null>(null);
  const faceMissingStreakRef = useRef(0);
  const multiFaceCooldownRef = useRef(0);
  const faceDetectionSupportNoticeRef = useRef(false);
  const staticFrameStreakRef = useRef(0);
  const lowLightStreakRef = useRef(0);
  const lastGrayFrameRef = useRef<Uint8Array | null>(null);
  const focusPollCooldownRef = useRef(0);

  function updateConnectionStatus(status: ConnectionStatus) {
    connectionStatusRef.current = status;
    setConnectionStatus(status);
  }

  function updateActiveSpeaker(speaker: "ai" | "candidate" | "none") {
    activeSpeakerRef.current = speaker;
    setActiveSpeaker(speaker);
  }

  function appendTranscript(speaker: "ai" | "candidate" | "system", text: string) {
    setTranscripts((previous) => [
      ...previous,
      {
        speaker,
        text,
        timestamp: new Date().toISOString()
      }
    ]);
  }

  function stopAiSpeechPlayback() {
    const currentSource = aiAudioSourceRef.current;
    aiAudioSourceRef.current = null;
    if (!currentSource) {
      return;
    }
    currentSource.onended = null;
    try {
      currentSource.stop(0);
    } catch {
      // Source may already be stopped.
    }
    currentSource.disconnect();
    updateActiveSpeaker("none");
  }

  async function playAiAudio(base64Audio: string) {
    if (!base64Audio) {
      return;
    }

    if (recorderRef.current && recorderRef.current.state === "recording") {
      turnEndingRef.current = false;
      hasTurnAudioRef.current = false;
      turnAudioBlobRef.current = null;
      recorderRef.current.stop();
    }

    const context = audioContextRef.current ?? new AudioContext();
    audioContextRef.current = context;
    if (context.state === "suspended") {
      await context.resume();
    }

    updateConnectionStatus("speaking");
    updateActiveSpeaker("ai");

    const audioBuffer = await context.decodeAudioData(base64ToArrayBuffer(base64Audio));
    stopAiSpeechPlayback();
    const source = context.createBufferSource();
    aiAudioSourceRef.current = source;
    source.buffer = audioBuffer;
    source.connect(context.destination);
    source.onended = () => {
      if (aiAudioSourceRef.current !== source) {
        return;
      }
      aiAudioSourceRef.current = null;
      updateActiveSpeaker("none");
      updateConnectionStatus("listening");
      voiceHeardThisTurnRef.current = false;
      turnEndingRef.current = false;
      hasTurnAudioRef.current = false;
      turnAudioBlobRef.current = null;
      lastVoiceAtRef.current = Date.now();
      if (
        streamRef.current &&
        websocketRef.current?.readyState === WebSocket.OPEN &&
        connectionStatusRef.current !== "closed" &&
        connectionStatusRef.current !== "completed"
      ) {
        void startMicrophoneStreaming(streamRef.current);
      }
    };
    source.start(0);
  }

  async function sendTurnEndSignal() {
    const socket = websocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || turnEndingRef.current) {
      return;
    }

    const recorder = recorderRef.current;
    if (recorder && recorder.state === "recording") {
      const elapsedMs = Date.now() - recordingStartedAtRef.current;
      if (elapsedMs < 900) {
        return;
      }
      turnEndingRef.current = true;
      recorder.stop();
      return;
    }

    turnEndingRef.current = true;
    socket.send(JSON.stringify({ type: "candidate_turn_end" }));
    updateConnectionStatus("thinking");
  }

  function stopVoiceActivityDetector() {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    sourceNodeRef.current?.disconnect();
    analyserRef.current?.disconnect();
    sourceNodeRef.current = null;
    analyserRef.current = null;
  }

  function startVoiceActivityDetector(stream: MediaStream) {
    const context = audioContextRef.current ?? new AudioContext();
    audioContextRef.current = context;

    const source = context.createMediaStreamSource(stream);
    const analyser = context.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    sourceNodeRef.current = source;
    analyserRef.current = analyser;

    const data = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(data);
      let total = 0;
      for (let i = 0; i < data.length; i += 1) {
        const normalized = (data[i] - 128) / 128;
        total += normalized * normalized;
      }
      const rms = Math.sqrt(total / data.length);
      const now = Date.now();

      if (rms > 0.03 && activeSpeakerRef.current !== "ai") {
        voiceHeardThisTurnRef.current = true;
        lastVoiceAtRef.current = now;
        updateActiveSpeaker("candidate");
      } else if (activeSpeakerRef.current === "candidate" && now - lastVoiceAtRef.current > 1000) {
        updateActiveSpeaker("none");
      }

      if (
        voiceHeardThisTurnRef.current &&
        activeSpeakerRef.current !== "ai" &&
        connectionStatusRef.current === "listening" &&
        now - lastVoiceAtRef.current > 1500
      ) {
        void sendTurnEndSignal();
      }

      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }

  async function startMicrophoneStreaming(stream: MediaStream) {
    const socket = websocketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    if (recorderRef.current && recorderRef.current.state === "recording") {
      return;
    }

    const audioTracks = stream.getAudioTracks().filter((track) => track.readyState === "live");
    if (audioTracks.length === 0) {
      setErrorMessage("Microphone track is unavailable.");
      updateConnectionStatus("closed");
      setIsLive(false);
      return;
    }

    const recordingStream = new MediaStream(audioTracks);
    const mimeCandidates = getRecorderMimeCandidates();
    let recorder: MediaRecorder | null = null;
    let selectedMimeType = "";

    for (const candidate of mimeCandidates) {
      try {
        recorder = new MediaRecorder(recordingStream, { mimeType: candidate });
        selectedMimeType = candidate;
        break;
      } catch {
        // Try the next supported candidate.
      }
    }

    if (!recorder) {
      try {
        recorder = new MediaRecorder(recordingStream);
      } catch (error) {
        setErrorMessage(`Microphone recorder init failed: ${getErrorMessage(error)}`);
        updateConnectionStatus("closed");
        setIsLive(false);
        return;
      }
    }

    recorderRef.current = recorder;
    hasTurnAudioRef.current = false;
    turnAudioBlobRef.current = null;
    recordingStartedAtRef.current = Date.now();

    recorder.ondataavailable = (event) => {
      if (event.data.size === 0) {
        return;
      }
      if (activeSpeakerRef.current === "ai") {
        return;
      }
      turnAudioBlobRef.current = event.data;
      hasTurnAudioRef.current = true;
    };

    recorder.onstop = async () => {
      recorderRef.current = null;
      const ws = websocketRef.current;
      if (!turnEndingRef.current || !ws || ws.readyState !== WebSocket.OPEN) {
        turnAudioBlobRef.current = null;
        return;
      }
      const turnBlob = turnAudioBlobRef.current;
      turnAudioBlobRef.current = null;
      if (!hasTurnAudioRef.current || !turnBlob || turnBlob.size === 0) {
        turnEndingRef.current = false;
        updateConnectionStatus("listening");
        setStatusMessage("No speech detected. Please answer again.");
        if (streamRef.current) {
          void startMicrophoneStreaming(streamRef.current);
        }
        return;
      }

      const chunkBase64 = await blobToBase64(turnBlob);
      ws.send(
        JSON.stringify({
          type: "audio_chunk",
          mime_type: turnBlob.type || selectedMimeType || "audio/webm",
          chunk_base64: chunkBase64
        })
      );
      ws.send(JSON.stringify({ type: "candidate_turn_end" }));
      updateConnectionStatus("thinking");
    };

    recorder.onerror = () => {
      setErrorMessage("Microphone streaming failed.");
      updateConnectionStatus("closed");
      setIsLive(false);
    };

    try {
      recorder.start();
    } catch (error) {
      recorderRef.current = null;
      setErrorMessage(`Failed to start microphone recording: ${getErrorMessage(error)}`);
      updateConnectionStatus("closed");
      setIsLive(false);
    }
  }

  function stopPreviewStream() {
    previewStreamRef.current?.getTracks().forEach((track) => track.stop());
    previewStreamRef.current = null;
  }

  async function startInterview() {
    if (connectionStatusRef.current === "connecting") {
      return;
    }
    if (strictProctorMode && (!cameraEnabled || !hasLiveCameraPreview)) {
      setErrorMessage("Camera preview is required before starting interview.");
      setStatusMessage("Enable camera and allow permission to continue.");
      updateConnectionStatus("idle");
      return;
    }
    setStatusMessage("Connecting to ZoSwi interviewer...");
    updateConnectionStatus("connecting");
    teardownLiveResources();
    setErrorMessage(null);
    setFinalResult(null);
    setSignals(null);
    setTranscripts([]);
    setCurrentQuestion("");
    setSessionId(null);
    setTabSwitchWarnings(0);
    setFocusLossWarnings(0);
    setFacePresenceWarnings(0);
    setDurationLeft(0);
    setTotalDuration(0);
    setMaxTurns(5);
    setCameraDropWarnings(0);
    setCameraWarningMessage(null);
    setFaceGuardMode("mediapipe-loading");
    strictActionTriggeredRef.current = false;
    faceMissingStreakRef.current = 0;
    multiFaceCooldownRef.current = 0;
    staticFrameStreakRef.current = 0;
    lowLightStreakRef.current = 0;
    lastGrayFrameRef.current = null;
    focusPollCooldownRef.current = 0;

    const accessToken = getClientAccessToken();
    if (!accessToken) {
      setHasAccessToken(false);
      setStatusMessage("Access restricted. Please sign in through ZoSwi and relaunch the interview.");
      setErrorMessage("Login required. This interview room is available only for authenticated users.");
      updateConnectionStatus("idle");
      return;
    }

    try {
      const mediaConstraints: MediaStreamConstraints = {
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        },
        video: cameraEnabled
          ? {
              facingMode: "user",
              width: { ideal: 960 },
              height: { ideal: 540 }
            }
          : false
      };

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia(mediaConstraints);
      } catch (primaryError) {
        if (strictProctorMode) {
          throw new Error("Camera access is required to continue.");
        }
        if (!cameraEnabled) {
          throw primaryError;
        }
        setCameraWarningMessage("Camera access failed. Interview will continue in audio-only mode.");
        stream = await navigator.mediaDevices.getUserMedia({
          audio: mediaConstraints.audio,
          video: false
        });
      }

      stopPreviewStream();
      streamRef.current = stream;
      const videoTracks = stream.getVideoTracks();
      setCameraPreviewStream(videoTracks.length > 0 ? new MediaStream(videoTracks) : null);
      const startResponse = await startInterviewSession(
        {
          candidate_name: candidateName.trim(),
          role: role.trim(),
          interview_type: interviewType
        },
        accessToken
      );
      const preStartedSessionId = String(startResponse.session_id || "").trim();
      if (!preStartedSessionId) {
        throw new Error("Unable to initialize interview session.");
      }
      const wsTokenResponse = await createWebSocketToken(preStartedSessionId, accessToken);
      const wsToken = String(wsTokenResponse.ws_token || "").trim();
      if (!wsToken) {
        throw new Error("Unable to initialize secure websocket session.");
      }

      const wsParams: Record<string, string> = {};
      wsParams.session_id = preStartedSessionId;
      wsParams.ws_token = wsToken;
      const socket = new WebSocket(getInterviewWebSocketUrl("/ws/interview", wsParams));
      websocketRef.current = socket;

      socket.onopen = async () => {
        setIsLive(true);
        updateConnectionStatus("connected");
        setStatusMessage("AI interviewer joined. Preparing the first question...");
        startVoiceActivityDetector(stream);
        socket.send(
          JSON.stringify({
            type: "session_start",
            session_id: preStartedSessionId || undefined,
            candidate_name: candidateName.trim(),
            role: role.trim(),
            interview_type: interviewType
          })
        );
      };

      socket.onmessage = async (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "connection_status") {
          const nextStatus = payload.status as ConnectionStatus;
          updateConnectionStatus(nextStatus);
          if (nextStatus === "listening" && activeSpeakerRef.current !== "ai" && streamRef.current) {
            await startMicrophoneStreaming(streamRef.current);
          }
          return;
        }
        if (payload.type === "session_started") {
          setSessionId(payload.session_id);
          setCurrentQuestion(payload.opening_question);
          setInterviewType(normalizeInterviewType(payload.interview_type));
          setDurationLeft(payload.interview_duration_seconds);
          setTotalDuration(payload.interview_duration_seconds);
          setMaxTurns(typeof payload.max_turns === "number" ? payload.max_turns : 5);
          setStatusMessage("Interview is live. Speak naturally when the AI finishes asking.");
          appendTranscript("system", `Session started (${payload.session_id})`);
          return;
        }
        if (payload.type === "transcript") {
          appendTranscript(payload.speaker, payload.text);
          if (payload.speaker === "ai") {
            setCurrentQuestion(payload.text);
          }
          return;
        }
        if (payload.type === "evaluation_signals") {
          setSignals({
            technical_accuracy: payload.technical_accuracy,
            communication_clarity: payload.communication_clarity,
            confidence: payload.confidence,
            overall_rating: payload.overall_rating,
            summary_text: payload.summary_text
          });
          return;
        }
        if (payload.type === "next_question") {
          setCurrentQuestion(payload.question_text);
          turnEndingRef.current = false;
          return;
        }
        if (payload.type === "ai_audio") {
          await playAiAudio(payload.audio_base64);
          return;
        }
        if (payload.type === "session_complete") {
          setStatusMessage("Interview completed. Review your final evaluation.");
          updateConnectionStatus("completed");
          setIsLive(false);
          updateActiveSpeaker("none");
          if (payload.session_id) {
            const token = getClientAccessToken();
            const result = await getInterviewResult(payload.session_id, token || undefined);
            setFinalResult(result);
          }
          return;
        }
        if (payload.type === "warning") {
          setStatusMessage(payload.message);
          return;
        }
        if (payload.type === "error") {
          setErrorMessage(payload.message ?? "Live interview error.");
        }
      };

      socket.onclose = (event) => {
        stopAiSpeechPlayback();
        updateConnectionStatus("closed");
        setIsLive(false);
        updateActiveSpeaker("none");
        if (event.code !== 1000) {
          const reason = event.reason ? `: ${event.reason}` : "";
          setErrorMessage(`WebSocket closed (${event.code}${reason}).`);
        }
      };

      socket.onerror = () => {
        stopAiSpeechPlayback();
        setErrorMessage("WebSocket connection failed.");
        updateConnectionStatus("closed");
        setIsLive(false);
        updateActiveSpeaker("none");
      };
    } catch (error) {
      const message = getErrorMessage(error);
      if (isAuthFailureMessage(message)) {
        clearClientAccessToken();
        setHasAccessToken(false);
        setStatusMessage("Session expired. Sign in on ZoSwi dashboard and relaunch interview.");
        setErrorMessage("Login required. Please relaunch the interview from ZoSwi.");
        updateConnectionStatus("idle");
        setIsLive(false);
        return;
      }
      setErrorMessage(message);
      updateConnectionStatus("closed");
      setIsLive(false);
    }
  }

  async function stopInterview() {
    const activeSessionId = sessionId;
    const ws = websocketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "session_end" }));
    }
    teardownLiveResources();
    setIsLive(false);
    updateConnectionStatus("closed");
    setStatusMessage("Interview session ended.");
    if (activeSessionId) {
      try {
        const token = getClientAccessToken();
        const result = await getInterviewResult(activeSessionId, token || undefined);
        setFinalResult(result);
      } catch {
        // Ignore fetch errors during forced shutdown.
      }
    }
  }

  function teardownLiveResources() {
    stopVoiceActivityDetector();
    stopAiSpeechPlayback();
    turnEndingRef.current = false;
    hasTurnAudioRef.current = false;
    turnAudioBlobRef.current = null;
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.ondataavailable = null;
      recorderRef.current.onstop = null;
      recorderRef.current.onerror = null;
      recorderRef.current.stop();
    }
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    stopPreviewStream();
    setCameraPreviewStream(null);
    websocketRef.current?.close();
    websocketRef.current = null;
  }

  useEffect(() => {
    if (!cameraEnabled) {
      if (!isLive) {
        stopPreviewStream();
        setCameraPreviewStream(null);
      }
      return;
    }

    if (isLive || connectionStatus === "connecting" || cameraPreviewStream) {
      return;
    }

    let cancelled = false;
    const requestPreview = async () => {
      try {
        const previewStream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: "user",
            width: { ideal: 960 },
            height: { ideal: 540 }
          }
        });
        if (cancelled) {
          previewStream.getTracks().forEach((track) => track.stop());
          return;
        }
        stopPreviewStream();
        previewStreamRef.current = previewStream;
        setCameraPreviewStream(previewStream);
        setCameraWarningMessage(null);
      } catch (error) {
        if (cancelled) {
          return;
        }
        setCameraPreviewStream(null);
        setCameraWarningMessage(`Camera preview unavailable: ${getErrorMessage(error)}`);
      }
    };
    void requestPreview();

    return () => {
      cancelled = true;
    };
  }, [cameraEnabled, isLive, connectionStatus, cameraPreviewStream]);

  useEffect(() => {
    if (!isLive || !cameraEnabled) {
      return;
    }

    const liveStream = streamRef.current;
    if (!liveStream) {
      return;
    }

    const videoTrack = liveStream.getVideoTracks()[0];
    if (!videoTrack) {
      setCameraDropWarnings((value) => value + 1);
      setCameraWarningMessage("Camera is not available during this interview.");
      appendTranscript("system", "Camera became unavailable.");
      return;
    }

    const registerCameraIncident = (message: string, transcriptText: string) => {
      setCameraDropWarnings((value) => value + 1);
      setCameraWarningMessage(message);
      appendTranscript("system", transcriptText);
    };

    const handleTrackEnded = () => {
      registerCameraIncident("Camera feed stopped during interview.", "Camera feed stopped.");
      setCameraPreviewStream(null);
    };

    const handleTrackMute = () => {
      registerCameraIncident("Camera feed muted during interview.", "Camera feed muted.");
    };

    const handleTrackUnmute = () => {
      setCameraWarningMessage(null);
    };

    videoTrack.addEventListener("ended", handleTrackEnded);
    videoTrack.addEventListener("mute", handleTrackMute);
    videoTrack.addEventListener("unmute", handleTrackUnmute);
    return () => {
      videoTrack.removeEventListener("ended", handleTrackEnded);
      videoTrack.removeEventListener("mute", handleTrackMute);
      videoTrack.removeEventListener("unmute", handleTrackUnmute);
    };
  }, [isLive, cameraEnabled]);

  useEffect(() => {
    const video = faceDetectionVideoRef.current;
    if (!video) {
      return;
    }
    video.srcObject = cameraPreviewStream;
    if (cameraPreviewStream) {
      void video.play().catch(() => undefined);
    }
    return () => {
      video.srcObject = null;
    };
  }, [cameraPreviewStream]);

  useEffect(() => {
    if (!isLive || !cameraEnabled || !cameraPreviewStream) {
      faceMissingStreakRef.current = 0;
      multiFaceCooldownRef.current = 0;
      staticFrameStreakRef.current = 0;
      lowLightStreakRef.current = 0;
      lastGrayFrameRef.current = null;
      return;
    }

    type FaceBox = { x: number; y: number; width: number; height: number };
    type RawFaceBoundingBox = {
      x?: number;
      y?: number;
      width?: number;
      height?: number;
      originX?: number;
      originY?: number;
    };
    type RawFace = {
      boundingBox?: RawFaceBoundingBox;
    };
    type NativeDetectorLike = {
      detect: (input: HTMLVideoElement) => Promise<Array<RawFace>>;
    };
    type NativeDetectorCtor = new (options?: { fastMode?: boolean; maxDetectedFaces?: number }) => NativeDetectorLike;
    type MediaPipeFaceResult = {
      detections?: Array<RawFace>;
    };
    type MediaPipeDetectorLike = {
      detectForVideo: (input: HTMLVideoElement, timestampMs: number) => MediaPipeFaceResult;
      close?: () => void;
    };

    const FaceDetectorApi = (window as Window & { FaceDetector?: NativeDetectorCtor }).FaceDetector;
    const nativeDetector = FaceDetectorApi ? new FaceDetectorApi({ fastMode: true, maxDetectedFaces: 2 }) : null;
    let mediaPipeDetector: MediaPipeDetectorLike | null = null;
    const intervalMs = 350;
    let cancelled = false;
    let fallbackCanvas: HTMLCanvasElement | null = null;
    let fallbackCtx: CanvasRenderingContext2D | null = null;

    if (nativeDetector) {
      setFaceGuardMode("native");
    } else {
      setFaceGuardMode("mediapipe-loading");
      void (async () => {
        try {
          const vision = await import("@mediapipe/tasks-vision");
          if (cancelled) {
            return;
          }
          const filesetResolver = await vision.FilesetResolver.forVisionTasks(
            "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
          );
          if (cancelled) {
            return;
          }
          mediaPipeDetector = await vision.FaceDetector.createFromOptions(filesetResolver, {
            baseOptions: {
              modelAssetPath:
                "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
            },
            runningMode: "VIDEO",
            minDetectionConfidence: 0.58,
            minSuppressionThreshold: 0.25
          });
          if (cancelled) {
            mediaPipeDetector.close?.();
            return;
          }
          setFaceGuardMode("mediapipe");
        } catch {
          if (cancelled) {
            return;
          }
          setFaceGuardMode("fallback");
          if (!faceDetectionSupportNoticeRef.current) {
            faceDetectionSupportNoticeRef.current = true;
            appendTranscript("system", "Face model unavailable. Running fallback camera behavior checks.");
          }
        }
      })();
    }

    const registerFaceSignal = (message: string, transcriptText: string, severity: 1 | 2 = 1) => {
      setFacePresenceWarnings((value) => value + severity);
      setCameraWarningMessage(message);
      appendTranscript("system", transcriptText);
    };

    const normalizeFace = (face: RawFace): FaceBox | null => {
      const box = face.boundingBox;
      if (!box) {
        return null;
      }
      const x = typeof box.x === "number" ? box.x : typeof box.originX === "number" ? box.originX : 0;
      const y = typeof box.y === "number" ? box.y : typeof box.originY === "number" ? box.originY : 0;
      const width = Math.max(typeof box.width === "number" ? box.width : 0, 0);
      const height = Math.max(typeof box.height === "number" ? box.height : 0, 0);
      if (width <= 0 || height <= 0) {
        return null;
      }
      return { x, y, width, height };
    };

    const clearFaceWarnings = () => {
      if (
        cameraWarningMessageRef.current?.includes("No face detected") ||
        cameraWarningMessageRef.current?.includes("Multiple faces detected") ||
        cameraWarningMessageRef.current?.includes("Face not centered") ||
        cameraWarningMessageRef.current?.includes("Face appears too far") ||
        cameraWarningMessageRef.current?.includes("Camera frame looks static") ||
        cameraWarningMessageRef.current?.includes("Camera frame is too dark")
      ) {
        setCameraWarningMessage(null);
      }
    };

    const evaluateFaceSignals = (faces: Array<FaceBox>, video: HTMLVideoElement) => {
      if (faces.length === 0) {
        faceMissingStreakRef.current += 1;
        if (faceMissingStreakRef.current >= 2) {
          faceMissingStreakRef.current = 0;
          registerFaceSignal("No face detected. Please stay visible in the camera frame.", "No face detected in camera frame.");
        }
        return true;
      }

      faceMissingStreakRef.current = 0;
      if (faces.length > 1) {
        if (multiFaceCooldownRef.current > 0) {
          multiFaceCooldownRef.current -= 1;
          return true;
        }
        multiFaceCooldownRef.current = 3;
        registerFaceSignal(
          "Multiple faces detected. Only the candidate should be visible.",
          "Multiple faces detected in camera frame.",
          2
        );
        return true;
      }

      const faceBox = faces[0];
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        const faceAreaRatio = (faceBox.width * faceBox.height) / (video.videoWidth * video.videoHeight);
        const faceCenterX = (faceBox.x + faceBox.width / 2) / video.videoWidth;
        const faceCenterY = (faceBox.y + faceBox.height / 2) / video.videoHeight;
        const faceNotCentered = faceCenterX < 0.2 || faceCenterX > 0.8 || faceCenterY < 0.14 || faceCenterY > 0.86;
        if (faceAreaRatio < 0.032) {
          if (multiFaceCooldownRef.current <= 0) {
            multiFaceCooldownRef.current = 2;
            registerFaceSignal("Face appears too far from camera. Move closer.", "Face appeared too far from camera.");
          } else {
            multiFaceCooldownRef.current -= 1;
          }
          return true;
        }
        if (faceNotCentered) {
          if (multiFaceCooldownRef.current <= 0) {
            multiFaceCooldownRef.current = 2;
            registerFaceSignal("Face not centered. Stay fully in frame.", "Face was not centered in camera frame.");
          } else {
            multiFaceCooldownRef.current -= 1;
          }
          return true;
        }
      }

      if (multiFaceCooldownRef.current > 0) {
        multiFaceCooldownRef.current -= 1;
      }
      clearFaceWarnings();
      return false;
    };

    const runCheck = async () => {
      if (cancelled || strictActionTriggeredRef.current) {
        return;
      }
      const video = faceDetectionVideoRef.current;
      if (!video) {
        return;
      }
      if (video.paused && video.srcObject) {
        await video.play().catch(() => undefined);
      }
      if (video.readyState < HTMLMediaElement.HAVE_METADATA || video.videoWidth === 0) {
        return;
      }

      if (nativeDetector) {
        try {
          const faces = (await nativeDetector.detect(video)).map(normalizeFace).filter((face): face is FaceBox => Boolean(face));
          evaluateFaceSignals(faces, video);
        } catch {
          // Ignore transient detector failures.
        }
        return;
      }

      if (mediaPipeDetector) {
        try {
          const result = mediaPipeDetector.detectForVideo(video, performance.now());
          const faces = (result.detections ?? []).map(normalizeFace).filter((face): face is FaceBox => Boolean(face));
          evaluateFaceSignals(faces, video);
        } catch {
          setFaceGuardMode("fallback");
        }
        return;
      }

      {
        const width = 48;
        const height = 36;
        if (!fallbackCanvas) {
          fallbackCanvas = document.createElement("canvas");
          fallbackCanvas.width = width;
          fallbackCanvas.height = height;
          fallbackCtx = fallbackCanvas.getContext("2d", { willReadFrequently: true });
        }
        if (!fallbackCtx) {
          return;
        }

        fallbackCtx.drawImage(video, 0, 0, width, height);
        const frame = fallbackCtx.getImageData(0, 0, width, height).data;
        const pixelCount = width * height;
        const grayFrame = new Uint8Array(pixelCount);
        let luminanceSum = 0;
        let diffSum = 0;
        for (let idx = 0; idx < pixelCount; idx += 1) {
          const offset = idx * 4;
          const gray = (frame[offset] * 77 + frame[offset + 1] * 150 + frame[offset + 2] * 29) >> 8;
          grayFrame[idx] = gray;
          luminanceSum += gray;
          if (lastGrayFrameRef.current) {
            diffSum += Math.abs(gray - lastGrayFrameRef.current[idx]);
          }
        }

        const avgLuminance = luminanceSum / pixelCount;
        const avgMotion = lastGrayFrameRef.current ? diffSum / pixelCount : 255;
        lastGrayFrameRef.current = grayFrame;

        if (avgLuminance < 20) {
          lowLightStreakRef.current += 1;
        } else {
          lowLightStreakRef.current = 0;
        }
        if (avgMotion < 1.0) {
          staticFrameStreakRef.current += 1;
        } else {
          staticFrameStreakRef.current = 0;
        }

        if (lowLightStreakRef.current >= 2) {
          lowLightStreakRef.current = 0;
          registerFaceSignal(
            "Camera frame is too dark. Keep your face clearly visible.",
            "Camera frame too dark for verification."
          );
          return;
        }
        if (staticFrameStreakRef.current >= 5) {
          staticFrameStreakRef.current = 3;
          registerFaceSignal(
            "Camera frame looks static. Keep your face in active view.",
            "Camera frame remained static for too long."
          );
          return;
        }
        clearFaceWarnings();
      }
    };

    void runCheck();
    const timerId = setInterval(() => {
      void runCheck();
    }, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timerId);
      faceMissingStreakRef.current = 0;
      multiFaceCooldownRef.current = 0;
      staticFrameStreakRef.current = 0;
      lowLightStreakRef.current = 0;
      lastGrayFrameRef.current = null;
      mediaPipeDetector?.close?.();
    };
  }, [isLive, cameraEnabled, cameraPreviewStream]);

  useEffect(() => {
    cameraWarningMessageRef.current = cameraWarningMessage;
  }, [cameraWarningMessage]);

  useEffect(() => {
    const visibilityHandler = () => {
      if (document.hidden && isLive) {
        setTabSwitchWarnings((value) => value + 1);
        appendTranscript("system", "Tab switch detected.");
      }
    };
    document.addEventListener("visibilitychange", visibilityHandler);
    return () => {
      document.removeEventListener("visibilitychange", visibilityHandler);
    };
  }, [isLive]);

  useEffect(() => {
    const blurHandler = () => {
      if (isLive) {
        setFocusLossWarnings((value) => value + 1);
        appendTranscript("system", "Window focus lost.");
      }
    };
    window.addEventListener("blur", blurHandler);
    return () => {
      window.removeEventListener("blur", blurHandler);
    };
  }, [isLive]);

  useEffect(() => {
    if (!isLive) {
      focusPollCooldownRef.current = 0;
      return;
    }
    const timerId = setInterval(() => {
      if (!document.hasFocus()) {
        if (focusPollCooldownRef.current <= 0) {
          setFocusLossWarnings((value) => value + 1);
          appendTranscript("system", "Window focus lost (poll check).");
          focusPollCooldownRef.current = 2;
        } else {
          focusPollCooldownRef.current -= 1;
        }
      } else if (focusPollCooldownRef.current > 0) {
        focusPollCooldownRef.current -= 1;
      }
    }, 350);

    return () => {
      clearInterval(timerId);
      focusPollCooldownRef.current = 0;
    };
  }, [isLive]);

  useEffect(() => {
    const totalWarnings = tabSwitchWarnings + focusLossWarnings + cameraDropWarnings + facePresenceWarnings;
    if (!isLive || !strictProctorMode || strictActionTriggeredRef.current) {
      return;
    }
    if (totalWarnings < integritySignalLimit) {
      return;
    }
    strictActionTriggeredRef.current = true;
    setErrorMessage("Interview ended due to integrity policy.");
    setStatusMessage("Interview ended automatically due to repeated integrity signals.");
    appendTranscript("system", "Session ended automatically by integrity policy.");
    void stopInterview();
  }, [
    isLive,
    strictProctorMode,
    tabSwitchWarnings,
    focusLossWarnings,
    cameraDropWarnings,
    facePresenceWarnings,
    integritySignalLimit
  ]);

  useEffect(() => {
    if (!isLive || totalDuration <= 0) {
      return;
    }
    timerRef.current = setInterval(() => {
      setDurationLeft((value) => {
        if (value <= 1) {
          void stopInterview();
          return 0;
        }
        return value - 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isLive, totalDuration]);

  useEffect(() => {
    return () => {
      teardownLiveResources();
      audioContextRef.current?.close();
    };
  }, []);

  const hasLiveCameraPreview = Boolean(
    cameraPreviewStream?.getVideoTracks().some((track) => track.readyState === "live")
  );
  const totalIntegrityWarnings = tabSwitchWarnings + focusLossWarnings + cameraDropWarnings + facePresenceWarnings;
  const canStart =
    !isLive &&
    connectionStatus !== "connecting" &&
    hasAccessToken &&
    candidateName.trim().length >= 2 &&
    role.trim().length >= 2 &&
    cameraEnabled &&
    hasLiveCameraPreview;
  const statusTone: Record<ConnectionStatus, string> = {
    idle: "bg-slate-500/20 text-slate-200 border-slate-400/30",
    connecting: "bg-amber-400/20 text-amber-200 border-amber-300/40",
    connected: "bg-sky-400/20 text-sky-200 border-sky-300/40",
    listening: "bg-emerald-400/20 text-emerald-200 border-emerald-300/40",
    thinking: "bg-violet-400/20 text-violet-200 border-violet-300/40",
    speaking: "bg-cyan-400/20 text-cyan-100 border-cyan-300/40",
    completed: "bg-fuchsia-400/20 text-fuchsia-100 border-fuchsia-300/40",
    closed: "bg-slate-500/20 text-slate-200 border-slate-400/30"
  };
  const activeSpeakerLabel =
    activeSpeaker === "candidate"
      ? candidateName.trim() || "You"
      : activeSpeaker === "ai"
        ? "ZoSwi"
        : "No one";
  const sessionDisplay = sessionId ? `${sessionId.slice(0, 8)}...` : "Not started";
  const summaryStatus = finalResult?.status ?? "in_progress";
  const summaryTurns =
    finalResult?.turn_count ?? transcripts.filter((line) => line.speaker === "candidate").length;
  const summaryMaxTurns = finalResult?.max_turns ?? maxTurns;
  const summaryOverall = finalResult?.evaluation_summary?.overall_rating;
  const quotaExhaustedMessage = (() => {
    const message = String(errorMessage || "").trim();
    if (!message) {
      return "";
    }
    return message.toLowerCase().includes("ai interview chances exhausted") ? message : "";
  })();

  async function copySessionId() {
    if (!sessionId) {
      return;
    }
    try {
      await navigator.clipboard.writeText(sessionId);
      setCopiedSession(true);
      setTimeout(() => setCopiedSession(false), 1600);
    } catch {
      setErrorMessage("Unable to copy session id.");
    }
  }

  if (!authChecked) {
    return (
      <div className="relative overflow-hidden rounded-[34px] border border-white/20 bg-[linear-gradient(165deg,rgba(16,41,67,0.8),rgba(24,57,88,0.72))] p-5 shadow-[0_24px_70px_rgba(9,24,46,0.35)] sm:p-8">
        <p className="text-sm text-slate-200">Verifying access...</p>
      </div>
    );
  }

  if (!hasAccessToken) {
    return (
      <div className="relative overflow-hidden rounded-[34px] border border-rose-300/35 bg-rose-500/12 p-5 text-rose-100 shadow-[0_24px_70px_rgba(60,9,20,0.22)] sm:p-8">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-rose-100/90">Access Denied</p>
        <h2 className="mt-2 font-[var(--font-display)] text-2xl font-semibold text-white">Login Required</h2>
        <p className="mt-3 text-sm leading-relaxed text-rose-100/95">
          This interview room is restricted. Sign in on{" "}
          <a
            href="https://zoswiai.streamlit.app"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold text-rose-50 underline underline-offset-2 hover:text-white"
          >
            ZoSwi
          </a>{" "}
          first, then relaunch from the dashboard.
        </p>
        {errorMessage ? <p className="mt-2 text-xs leading-relaxed text-rose-100/90">{errorMessage}</p> : null}
      </div>
    );
  }

  return (
    <div className="relative overflow-hidden rounded-[34px] border border-white/20 bg-[linear-gradient(165deg,rgba(16,41,67,0.8),rgba(24,57,88,0.72))] p-5 shadow-[0_24px_70px_rgba(9,24,46,0.35)] sm:p-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_14%_12%,rgba(125,211,252,0.24),transparent_34%),radial-gradient(circle_at_90%_2%,rgba(52,211,153,0.2),transparent_38%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-100/65 to-transparent" />
      {quotaExhaustedMessage ? (
        <section className="relative z-20 mb-4 rounded-2xl border border-amber-300/45 bg-amber-500/14 px-4 py-3 text-sm text-amber-100 shadow-[0_10px_28px_rgba(180,83,9,0.25)]">
          {quotaExhaustedMessage}
        </section>
      ) : null}
      <header className="relative">
        <div className="absolute right-0 top-0 z-20">
          <div className="group relative inline-flex">
            <button
              type="button"
              className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-cyan-100/40 bg-cyan-400/15 text-cyan-100 transition hover:bg-cyan-400/25 focus:outline-none focus:ring-2 focus:ring-cyan-200/70"
              aria-label="Interview benefits information"
              title="Interview benefits information"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 10v6" />
                <path d="M12 7h.01" />
              </svg>
            </button>
            <div className="pointer-events-none absolute right-0 top-10 w-[300px] rounded-xl border border-cyan-200/35 bg-slate-950/95 p-3 text-xs leading-relaxed text-cyan-50 opacity-0 shadow-[0_14px_30px_rgba(3,10,24,0.6)] transition group-hover:opacity-100 group-focus-within:opacity-100">
              Share your resume, complete your interview, and ZoSwi will organize recruiter-ready findings so your profile gets noticed faster with aligned opportunities.
            </div>
          </div>
        </div>
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-200/90">ZoSwi Interview Suite</p>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="font-[var(--font-display)] text-3xl font-semibold tracking-tight text-slate-50 sm:text-4xl">
            Live Interview Room
          </h1>
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-slate-300">{statusMessage}</p>
      </header>

      <div className="relative mt-7 grid gap-6 xl:grid-cols-[1.5fr_0.92fr]">
        <div className="space-y-6">
          <section className="panel p-5 sm:p-6">
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">
                Candidate Name
                <input
                  value={candidateName}
                  onChange={(event) => setCandidateName(event.target.value)}
                  disabled={isLive}
                  className="soft-input"
                />
              </label>
              <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">
                Target Role
                <input
                  value={role}
                  onChange={(event) => setRole(event.target.value)}
                  disabled={isLive}
                  className="soft-input"
                />
              </label>
              <label className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-300">
                Requirement Type
                <select
                  value={interviewType}
                  onChange={(event) => setInterviewType(normalizeInterviewType(event.target.value))}
                  disabled={isLive}
                  className="soft-input"
                >
                  <option value="mixed">Mixed</option>
                  <option value="technical">Technical</option>
                  <option value="behavioral">Behavioral</option>
                </select>
              </label>
            </div>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={startInterview}
                disabled={!canStart}
                className="rounded-xl border border-cyan-100/70 bg-[linear-gradient(120deg,rgba(81,233,255,0.98),rgba(66,235,196,0.95))] px-5 py-2.5 text-sm font-bold text-slate-950 shadow-[0_8px_20px_rgba(8,145,178,0.35)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-slate-700 disabled:text-slate-300 disabled:shadow-none"
              >
                Start Live Interview
              </button>
              <button
                type="button"
                onClick={sendTurnEndSignal}
                disabled={!isLive || connectionStatus !== "listening"}
                className="rounded-xl border border-emerald-200/45 bg-emerald-500/16 px-5 py-2.5 text-sm font-semibold text-emerald-50 transition hover:bg-emerald-400/28 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-slate-700 disabled:text-slate-300"
              >
                I Finished Speaking
              </button>
              <button
                type="button"
                onClick={stopInterview}
                disabled={!isLive}
                className="rounded-xl border border-rose-200/55 bg-[linear-gradient(120deg,rgba(252,108,141,0.96),rgba(244,63,94,0.94))] px-5 py-2.5 text-sm font-bold text-white shadow-[0_8px_20px_rgba(190,24,93,0.34)] transition hover:brightness-110 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-slate-700 disabled:text-slate-300 disabled:shadow-none"
              >
                End Interview
              </button>
            </div>
          </section>

          <section className="panel p-5 sm:p-6">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-cyan-200/25 bg-gradient-to-br from-cyan-400/14 to-sky-500/10 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-cyan-100/85">Session</p>
                  <button
                    type="button"
                    onClick={copySessionId}
                    disabled={!sessionId}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-cyan-100/40 bg-cyan-400/15 text-cyan-100 transition hover:bg-cyan-400/25 disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/5 disabled:text-slate-500"
                    aria-label="Copy session id"
                    title={sessionId ? "Copy session id" : "Session id not available"}
                  >
                    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2">
                      <rect x="9" y="9" width="10" height="10" rx="2" />
                      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
                    </svg>
                  </button>
                </div>
                <p className="mt-1 text-sm font-semibold text-slate-50">{sessionDisplay}</p>
                {copiedSession ? <p className="mt-1 text-xs text-cyan-100/90">Session copied</p> : null}
              </div>
              <div className="rounded-xl border border-emerald-200/25 bg-gradient-to-br from-emerald-400/14 to-teal-500/10 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-100/85">Connection</p>
                <span className={`mt-1 inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone[connectionStatus]}`}>
                  {connectionStatus}
                </span>
              </div>
              <div className="rounded-xl border border-white/20 bg-gradient-to-br from-white/10 to-white/5 p-3">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-200/85">Speaker</p>
                <p className="mt-1 flex items-center gap-2 text-sm font-semibold text-slate-50">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    activeSpeaker === "ai"
                      ? "animate-pulse bg-cyan-300"
                      : activeSpeaker === "candidate"
                        ? "animate-pulse bg-emerald-300"
                        : "bg-slate-500"
                  }`}
                />
                {activeSpeakerLabel}
                </p>
              </div>
            </div>

            <h3 className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Current Question</h3>
            <div className="mt-2 rounded-xl border border-cyan-200/35 bg-gradient-to-br from-cyan-400/14 via-sky-500/12 to-emerald-400/10 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-cyan-100/80">ZoSwi AI</p>
              <p className="mt-2 text-base leading-relaxed text-cyan-50">
                {currentQuestion || "The first AI question will appear here once the session starts."}
              </p>
            </div>

            <h3 className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Live Transcript</h3>
            <div className="transcript-scroll mt-2 h-[360px] space-y-2 overflow-y-auto rounded-xl border border-white/10 bg-slate-950/55 p-3.5">
              {transcripts.length === 0 ? (
                <div className="rounded-xl border border-dashed border-white/15 bg-white/5 p-5 text-sm text-slate-400">
                  Transcript will stream here in real time after the first turn.
                </div>
              ) : (
                transcripts.map((line, index) => (
                  <div
                    key={`${line.timestamp}-${index}`}
                    className={`rounded-lg border p-2.5 text-sm ${
                      line.speaker === "ai"
                        ? "border-cyan-300/30 bg-cyan-500/12 text-cyan-50"
                        : line.speaker === "candidate"
                          ? "border-emerald-300/30 bg-emerald-500/12 text-emerald-50"
                          : "border-white/10 bg-white/5 text-slate-200"
                    }`}
                  >
                    <p className="text-[11px] font-semibold uppercase tracking-wide opacity-80">
                      {line.speaker === "ai"
                        ? "ZoSwi"
                        : line.speaker === "candidate"
                          ? candidateName.trim() || "You"
                          : "System"}
                    </p>
                    <p className="mt-1 leading-relaxed">{line.text}</p>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>

        <aside className="space-y-6">
          <section className="panel p-4 sm:p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Final Summary</h3>
            <div className="mt-3 space-y-2 text-sm text-slate-200">
              <p>Status: {summaryStatus}</p>
              <p>
                Turns: {summaryTurns} / {summaryMaxTurns}
              </p>
              <p>Overall: {typeof summaryOverall === "number" ? summaryOverall.toFixed(1) : "N/A"} / 10</p>
            </div>
          </section>

          <CameraPreview
            stream={cameraPreviewStream}
            enabled={cameraEnabled}
            warning={cameraWarningMessage}
            disabled={isLive || connectionStatus === "connecting"}
            onToggle={(nextEnabled) => {
              setCameraEnabled(nextEnabled);
              if (!nextEnabled) {
                setCameraWarningMessage(
                  "Keeping your camera on can improve trust and increase job opportunities."
                );
              } else {
                setCameraWarningMessage(null);
              }
            }}
          />

          <TimerBar secondsLeft={Math.max(durationLeft, 0)} totalSeconds={totalDuration > 0 ? totalDuration : 1} />
          <EvaluationPanel signals={signals} />

          <section className="panel p-4 sm:p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-300">Integrity Signals</h3>
            <p className="mt-3 text-sm text-slate-200">
              Policy: session auto-ends after {integritySignalLimit} integrity signals.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-slate-200">
              <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Total: {totalIntegrityWarnings}</p>
              <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">
                Remaining: {Math.max(integritySignalLimit - totalIntegrityWarnings, 0)}
              </p>
              <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Focus: {focusLossWarnings}</p>
              <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Tabs: {tabSwitchWarnings}</p>
              <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Camera: {cameraDropWarnings}</p>
              <p className="rounded-lg border border-white/10 bg-white/5 px-3 py-2">Face: {facePresenceWarnings}</p>
            </div>
            {cameraWarningMessage ? (
              <p className="mt-3 rounded-lg border border-rose-300/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                {cameraWarningMessage}
              </p>
            ) : null}
          </section>
        </aside>
      </div>

      <video ref={faceDetectionVideoRef} className="hidden" autoPlay muted playsInline aria-hidden="true" />

      {errorMessage && !quotaExhaustedMessage ? (
        <section className="relative mt-6 rounded-2xl border border-rose-300/35 bg-rose-500/12 p-4 text-sm text-rose-100">
          {errorMessage}
        </section>
      ) : null}
    </div>
  );
}
