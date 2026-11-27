// GPT-Live over WebRTC, exactly as Lonora's Expo client joins a call
// (apps/mobile/lib/voice-transport.ts `MobileVoiceJoin`, voice-device.native.ts):
//
// 1. microphone (`getUserMedia({audio: true})`), in-call audio on the speaker;
// 2. `RTCPeerConnection({})` (no ICE servers from the client), the microphone track, and the
//    `oai-events` data channel before the offer;
// 3. offer → local description → wait for ICE gathering to complete (10 s): the server needs
//    a full non-trickle SDP;
// 4. `POST /voice/sessions {agent_id, thread_id, mode: "gpt_live", client_nonce, sdp,
//    incoming_call_id?}` → `{session_id, sdp}` → remote answer;
// 5. data-channel events `session.started` (connected), `session.output_audio.delta` /
//    `session.output_transcript.delta` (speaking), `error`, `session.closed`; `getStats()`
//    every 150 ms for the input/output levels (speaking held 650 ms);
// 6. end: `{"type":"session.close"}` on the channel, ≤ 2.5 s for `session.closed`, then
//    `DELETE /voice/sessions/{id}` (or `POST /voice/cancel-initialization {client_nonce}` when
//    no session exists yet); a muted microphone is unmuted phone-wide, tracks stopped, the peer
//    closed and disposed (disposing the last peer is what ends flutter_webrtc's in-call audio
//    session: audio mode, focus, mute and speaker come back), as Expo's `stopAudio` does with
//    `InCallManager.setMicrophoneMute(false)` + `InCallManager.stop()`. A peer that
//    disconnects or fails is `voice_connection_failed`.
import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter_webrtc/flutter_webrtc.dart';

import '../../core/api/api_client.dart';
import '../../core/api/api_error.dart';
import '../../core/json.dart';

/// What the call reports while it runs.
class VoiceActivity {
  const VoiceActivity({this.speaking = false, this.level = 0});
  final bool speaking;
  final double level;
}

class VoiceTransportCallbacks {
  const VoiceTransportCallbacks({
    required this.onConnected,
    required this.onError,
    required this.onActivity,
    required this.onClosed,
  });

  final void Function() onConnected;

  /// An API error code (`voice_connection_failed`, `voice_permission_denied`, …).
  final void Function(String code) onError;
  final void Function(VoiceActivity activity) onActivity;
  final void Function() onClosed;
}

/// One call's media and server session.
abstract class VoiceTransport {
  String? get sessionId;
  String get nonce;

  Future<void> connect({
    required String agentId,
    required String threadId,
    String? incomingCallId,
  });
  Future<void> setMuted(bool muted);
  Future<void> setSpeaker(bool on);

  /// Ends the call (idempotent); resolves once the server session is finalized. Without
  /// [finalize] only this phone's side closes (no token left to tell the server).
  Future<void> close({bool finalize = true});
}

typedef VoiceTransportFactory = VoiceTransport Function(
  VoiceTransportCallbacks callbacks,
  ApiClient api,
);

/// A client nonce as Expo makes one (`Date.now().toString(36)` + two random parts).
String voiceNonce([math.Random? random]) {
  final r = random ?? math.Random.secure();
  String part() => r.nextInt(1 << 32).toRadixString(36);
  return '${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}-${part()}-${part()}';
}

/// The kind of one data-channel message: `session.started`, `session.closed`, `error`,
/// `speaking` (audio or transcript delta), or null for anything else. Throws on bad JSON.
String? dataChannelEventKind(String text) {
  final event = asJson(jsonDecode(text.isEmpty ? '{}' : text));
  final type = asString(event['type']);
  return switch (type) {
    'session.started' || 'session.closed' || 'error' => type,
    'session.output_audio.delta' ||
    'session.output_transcript.delta' => 'speaking',
    _ => null,
  };
}

/// Input and output audio levels (0..1) from a stats report, as Expo's `sample()`.
({double input, double output}) audioLevels(Iterable<StatsReport> reports) {
  var input = 0.0, output = 0.0;
  for (final report in reports) {
    final v = report.values;
    if (v['kind'] != 'audio' && v['mediaType'] != 'audio') continue;
    final raw = v['audioLevel'];
    final level = raw is num ? raw.toDouble().clamp(0.0, 1.0) : 0.0;
    if (report.type == 'media-source' || report.type == 'outbound-rtp') {
      input = math.max(input, level);
    }
    if (report.type == 'inbound-rtp') output = math.max(output, level);
  }
  return (input: input, output: output);
}

/// The native side of a call (flutter_webrtc), behind a class for tests.
class VoiceMedia {
  const VoiceMedia();

  Future<MediaStream> microphone(Map<String, dynamic> constraints) =>
      navigator.mediaDevices.getUserMedia(constraints);

  Future<RTCPeerConnection> peer() => createPeerConnection(<String, dynamic>{});

  /// The phone-wide microphone mute (`AudioManager.setMicrophoneMute` on Android).
  Future<void> setMicrophoneMute(bool mute, MediaStreamTrack track) =>
      Helper.setMicrophoneMute(mute, track);

  Future<void> setSpeakerphoneOn(bool on) => Helper.setSpeakerphoneOn(on);
}

class WebRtcVoiceTransport implements VoiceTransport {
  WebRtcVoiceTransport(
    this._callbacks,
    this._api, {
    this.media = const VoiceMedia(),
    this.iceTimeout = const Duration(seconds: 10),
    this.closedTimeout = const Duration(milliseconds: 2500),
  });

  final VoiceTransportCallbacks _callbacks;
  final ApiClient _api;
  final VoiceMedia media;

  /// How long ICE gathering may take before the call fails.
  final Duration iceTimeout;

  /// How long the end waits for the server's `session.closed`.
  final Duration closedTimeout;

  @override
  final String nonce = voiceNonce();
  @override
  String? sessionId;

  RTCPeerConnection? _peer;
  MediaStream? _microphone;
  RTCDataChannel? _channel;
  Timer? _sampler;
  bool _sampling = false;
  bool _disposed = false;
  bool _finalized = false;
  bool _muted = false;
  DateTime _outputAt = DateTime.fromMillisecondsSinceEpoch(0);
  Completer<void>? _ice;
  final Completer<void> _ended = Completer<void>();
  Future<void>? _closing;

  @override
  Future<void> connect({
    required String agentId,
    required String threadId,
    String? incomingCallId,
  }) async {
    try {
      final microphone = await media.microphone({
        'audio': {
          'echoCancellation': true,
          'noiseSuppression': true,
          'autoGainControl': true,
        },
        'video': false,
      });
      if (_disposed) {
        for (final t in microphone.getTracks()) {
          await t.stop();
        }
        await microphone.dispose();
        return;
      }
      _microphone = microphone;
      final peer = await media.peer();
      if (_disposed) {
        // Ended while the peer was being made: close() never saw it.
        try {
          await peer.close();
          await peer.dispose();
        } catch (_) {}
        return;
      }
      _peer = peer;
      peer.onConnectionState = (state) {
        if (_disposed) return;
        if (state == RTCPeerConnectionState.RTCPeerConnectionStateConnected) {
          _callbacks.onConnected();
        }
        if (state ==
                RTCPeerConnectionState.RTCPeerConnectionStateDisconnected ||
            state == RTCPeerConnectionState.RTCPeerConnectionStateFailed ||
            state == RTCPeerConnectionState.RTCPeerConnectionStateClosed) {
          _callbacks.onError('voice_connection_failed');
          unawaited(close());
        }
      };
      // In-call audio, on the speaker (InCallManager.start + setForceSpeakerphoneOn).
      await setSpeaker(true);
      await setMuted(_muted);
      for (final track in microphone.getAudioTracks()) {
        await peer.addTrack(track, microphone);
      }
      final channel = await peer.createDataChannel(
        'oai-events',
        RTCDataChannelInit(),
      );
      _channel = channel;
      channel.onMessage = (message) => _onChannel(message.text);
      channel.onDataChannelState = (state) {
        if (state == RTCDataChannelState.RTCDataChannelClosed && !_disposed) {
          unawaited(close());
        }
      };
      final offer = await peer.createOffer(<String, dynamic>{});
      if (_disposed) return;
      await peer.setLocalDescription(offer);
      if (_disposed) return;
      await _waitIce(peer);
      if (_disposed) return;
      final sdp = (await peer.getLocalDescription())?.sdp;
      if (sdp == null || sdp.isEmpty) {
        throw ApiError(status: 502, code: 'voice_response_invalid');
      }
      final result = asJson(
        await _api.post('/voice/sessions', {
          'agent_id': agentId,
          'thread_id': threadId,
          'mode': 'gpt_live',
          'client_nonce': nonce,
          'sdp': sdp,
          'incoming_call_id': ?incomingCallId,
        }),
      );
      final id = asString(result['session_id']);
      final answer = asString(result['sdp']);
      if (id == null || answer == null) {
        throw ApiError(status: 502, code: 'voice_response_invalid');
      }
      sessionId = id;
      if (_disposed) {
        await _api.delete('/voice/sessions/${Uri.encodeComponent(id)}');
        return;
      }
      await peer.setRemoteDescription(RTCSessionDescription(answer, 'answer'));
      if (_disposed) return;
      _sampler = Timer.periodic(const Duration(milliseconds: 150), (_) {
        if (_sampling || _disposed) return;
        _sampling = true;
        unawaited(_sample().whenComplete(() => _sampling = false));
      });
    } on SessionRequestCancelled {
      await close();
    } catch (error) {
      if (_disposed) return;
      _callbacks.onError(switch (error) {
        ApiError(:final code) => code,
        _ => 'voice_connection_failed',
      });
      await close();
    }
  }

  void _onChannel(String text) {
    String? kind;
    try {
      kind = dataChannelEventKind(text);
    } catch (_) {
      if (!_disposed) _callbacks.onError('voice_response_invalid');
      return;
    }
    if (kind == 'session.closed') {
      _finalized = true;
      if (!_ended.isCompleted) _ended.complete();
      unawaited(close());
    }
    if (_disposed) return;
    switch (kind) {
      case 'session.started':
        _callbacks.onConnected();
      case 'error':
        _callbacks.onError('voice_connection_failed');
      case 'speaking':
        _outputAt = DateTime.now();
    }
  }

  Future<void> _waitIce(RTCPeerConnection peer) async {
    if (peer.iceGatheringState ==
        RTCIceGatheringState.RTCIceGatheringStateComplete) {
      return;
    }
    final done = _ice = Completer<void>();
    peer.onIceGatheringState = (state) {
      if (state == RTCIceGatheringState.RTCIceGatheringStateComplete &&
          !done.isCompleted) {
        done.complete();
      }
    };
    try {
      await done.future.timeout(iceTimeout);
    } on TimeoutException {
      throw ApiError(status: 504, code: 'voice_connection_failed');
    } finally {
      _ice = null;
    }
  }

  Future<void> _sample() async {
    var levels = (input: 0.0, output: 0.0);
    try {
      levels = audioLevels(await _peer!.getStats());
    } catch (_) {
      // Meters are optional; the call transport stays authoritative.
    }
    if (_disposed) return;
    if (levels.output > 0.03) _outputAt = DateTime.now();
    final speaking =
        DateTime.now().difference(_outputAt) <
        const Duration(milliseconds: 650);
    _callbacks.onActivity(
      VoiceActivity(
        speaking: speaking,
        level: speaking ? levels.output : (_muted ? 0 : levels.input),
      ),
    );
  }

  @override
  Future<void> setMuted(bool muted) async {
    _muted = muted;
    final microphone = _microphone;
    if (microphone == null) return;
    for (final track in microphone.getAudioTracks()) {
      track.enabled = !muted;
    }
    final track = microphone.getAudioTracks().firstOrNull;
    if (track == null) return;
    try {
      await media.setMicrophoneMute(muted, track);
    } catch (_) {}
  }

  @override
  Future<void> setSpeaker(bool on) async {
    try {
      await media.setSpeakerphoneOn(on);
    } catch (_) {}
  }

  @override
  Future<void> close({bool finalize = true}) =>
      _closing ??= _close(finalize: finalize);

  Future<void> _close({required bool finalize}) async {
    _disposed = true;
    _sampler?.cancel();
    final ice = _ice;
    if (ice != null && !ice.isCompleted) ice.complete();
    // Each step is tried on its own: native cleanup can fail after an audio interruption,
    // and the rest must still be released and the server session finalized.
    Future<void> safely(FutureOr<void> Function() action) async {
      try {
        await action();
      } catch (_) {}
    }

    // Silence the agent at once while the server finalizes the session.
    final peer = _peer;
    if (peer != null) {
      await safely(() async {
        for (final receiver in await peer.getReceivers()) {
          receiver.track?.enabled = false;
        }
      });
    }
    final microphone = _microphone;
    if (microphone != null) {
      // The mute is phone-wide: left on, voice notes and other apps would record silence.
      final track = microphone.getAudioTracks().firstOrNull;
      if (_muted && track != null) {
        await safely(() => media.setMicrophoneMute(false, track));
      }
      for (final track in microphone.getTracks()) {
        await safely(track.stop);
      }
    }
    try {
      final channel = _channel;
      if (finalize &&
          !_finalized &&
          channel != null &&
          channel.state == RTCDataChannelState.RTCDataChannelOpen) {
        var sent = false;
        await safely(() async {
          await channel.send(
            RTCDataChannelMessage(jsonEncode({'type': 'session.close'})),
          );
          sent = true;
        });
        if (sent) {
          await _ended.future.timeout(closedTimeout).catchError((Object _) {});
        }
      }
      final id = sessionId;
      if (finalize) {
        await safely(() async {
          if (id != null) {
            await _api.delete('/voice/sessions/${Uri.encodeComponent(id)}');
          } else {
            await _api.post('/voice/cancel-initialization', {
              'client_nonce': nonce,
            });
          }
        });
      }
    } finally {
      await safely(() => _channel?.close());
      // Back to the earpiece while the call's audio session is still ours (disposing the peer
      // then restores the phone's own route).
      await safely(() => media.setSpeakerphoneOn(false));
      await safely(() => peer?.close());
      await safely(() => microphone?.dispose());
      // Only a disposed peer releases the native observer and, with the last one, the in-call
      // audio mode and focus (flutter_webrtc `peerConnectionDispose` → `AudioSwitchManager.stop`).
      await safely(() => peer?.dispose());
      _callbacks.onClosed();
    }
  }
}
