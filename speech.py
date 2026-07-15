"""macOS speech-to-text using Apple's native Speech framework.

Requires: pyobjc-framework-Speech
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from Foundation import NSObject
from Speech import (
    SFSpeechAudioBufferRecognitionRequest,
    SFSpeechRecognizer,
    SFSpeechRecognitionTask,
)
from AVFoundation import (
    AVAudioEngine,
    AVAudioFormat,
    AVAudioSession,
    AVAudioInputNode,
)
import objc


class SpeechRecorder(NSObject):
    """Wraps Apple's SFSpeechRecognizer for live microphone transcription.

    Usage:
        recorder = SpeechRecorder.alloc().init()
        recorder.authorize(callback)
        recorder.start_recording(callback)   # starts mic + recognition
        recorder.stop_recording()            # stops, fires callback with text
    """

    def init(self):
        self = objc.super(SpeechRecorder, self).init()
        if self is None:
            return None
        self._engine = None
        self._recognition_task = None
        self._request = None
        self._recording = False
        self._callback = None
        self._final_text = ""
        self._lock = threading.Lock()
        self._timeout_handle = None
        return self

    # ── Authorization ──────────────────────────────────────────────

    def authorize(self, callback: Callable[[bool], None] | None = None):
        """Request microphone and speech recognition permissions.

        callback(True) on grant, callback(False) on denial.
        If the system alert doesn't appear, the user can grant via
        System Preferences > Privacy & Security > Microphone / Speech Recognition.
        """
        auth_callback = callback

        def _auth_handler(granted: bool):
            if auth_callback:
                auth_callback(granted)

        SFSpeechRecognizer.requestAuthorization_(_auth_handler)

    # ── Recording ──────────────────────────────────────────────────

    def start_recording(self, callback: Callable[[str], None]) -> None:
        """Start capturing audio and transcribing.

        callback(transcribed_text) fires when stop_recording() is called
        or when the recognizer finalizes on its own.
        """
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._callback = callback
            self._final_text = ""

        try:
            self._setup_audio_engine()
        except Exception:
            with self._lock:
                self._recording = False
                if self._callback:
                    self._callback("")
            return

        # Safety timeout: Apple allows max 60s per request
        self._timeout_handle = threading.Timer(60.0, self._on_timeout)
        self._timeout_handle.daemon = True
        self._timeout_handle.start()

    def stop_recording(self) -> str:
        """Stop microphone capture and return the transcribed text.

        The callback provided to start_recording is also fired.
        """
        with self._lock:
            if not self._recording:
                return ""
            self._recording = False

        if self._timeout_handle:
            self._timeout_handle.cancel()
            self._timeout_handle = None

        text = self._finalize()

        with self._lock:
            cb = self._callback
            self._callback = None

        if cb:
            cb(text)
        return text

    # ── Internal ───────────────────────────────────────────────────

    def _setup_audio_engine(self) -> None:
        self._engine = AVAudioEngine.alloc().init()

        session = AVAudioSession.sharedInstance()
        session.setCategory_error_(
            "AVAudioSessionCategoryRecord",
            None,
        )
        session.setActive_error_(True, None)

        recognizer = SFSpeechRecognizer.alloc().init()
        if not recognizer.isAvailable():
            raise RuntimeError("Speech recognizer not available")

        self._request = SFSpeechAudioBufferRecognitionRequest.alloc().init()
        self._request.setShouldReportPartialResults_(True)

        input_node = self._engine.inputNode()
        recording_format = input_node.outputFormatForBus_(0)

        def on_buffer(buffer, when):
            if self._recording and self._request:
                self._request.appendAudioBuffer_(buffer)

        input_node.installTapOnBus_bufferSize_format_inputCallback_(
            0, 1024, recording_format, on_buffer
        )

        self._engine.prepare()
        self._engine.startAndReturnError_(None)

        def on_recognition_task(task, result, error):
            if result:
                self._final_text = result.bestTranscription().formattedString()
            if error or (result and result.isFinal()):
                self._finalize()

        self._recognition_task = recognizer.recognitionTaskWithRequest_resultHandler_(
            self._request, on_recognition_task
        )

    def _finalize(self) -> str:
        with self._lock:
            text = self._final_text

        try:
            if self._engine:
                self._engine.stop()
                self._engine.inputNode().removeTapOnBus_(0)
        except Exception:
            pass

        try:
            if self._recognition_task:
                self._recognition_task.cancel()
        except Exception:
            pass

        try:
            if self._request:
                self._request.endAudio()
        except Exception:
            pass

        self._engine = None
        self._recognition_task = None
        self._request = None

        return text

    def _on_timeout(self) -> None:
        if self._recording:
            self.stop_recording()
