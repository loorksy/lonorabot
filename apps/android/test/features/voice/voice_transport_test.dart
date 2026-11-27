// The WebRTC transport with a fake native side: the offer it posts, the data-channel events,
// and the end of a call (session.close → session.closed → DELETE, or cancel-initialization
// before a session exists; the phone-wide mute cleared; the peer closed AND disposed, which
// is what ends flutter_webrtc's in-call audio session).
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:lonora/features/voice/voice_transport.dart';

import 'voice_fakes.dart';

class _Track extends Fake implements MediaStreamTrack {
  _Track(this.log);
  final List<String> log;
  @override
  bool enabled = true;
  @override
  String? get kind => 'audio';
  @override
  Future<void> stop() async => log.add('track.stop');
}

class _Stream extends Fake implements MediaStream {
  _Stream(this.log) : track = _Track(log);
  final List<String> log;
  final _Track track;
  @override
  List<MediaStreamTrack> getTracks() => [track];
  @override
  List<MediaStreamTrack> getAudioTracks() => [track];
  @override
  Future<void> dispose() async => log.add('stream.dispose');
}

class _Sender extends Fake implements RTCRtpSender {}

class _Channel extends Fake implements RTCDataChannel {
  _Channel(this.log);
  final List<String> log;
  void Function(String text)? onSend;
  @override
  Function(RTCDataChannelState state)? onDataChannelState;
  @override
  Function(RTCDataChannelMessage data)? onMessage;
  @override
  RTCDataChannelState? state = RTCDataChannelState.RTCDataChannelOpen;

  @override
  Future<void> send(RTCDataChannelMessage message) async {
    log.add('channel.send ${message.text}');
    onSend?.call(message.text);
  }

  @override
  Future<void> close() async {
    state = RTCDataChannelState.RTCDataChannelClosed;
    log.add('channel.close');
  }

  void receive(String text) => onMessage?.call(RTCDataChannelMessage(text));
}

class _Peer extends Fake implements RTCPeerConnection {
  _Peer(this.log) : channel = _Channel(log);
  final List<String> log;
  final _Channel channel;
  String? remote;
  String? label;
  final tracks = <MediaStreamTrack>[];

  @override
  Function(RTCPeerConnectionState state)? onConnectionState;
  @override
  Function(RTCIceGatheringState state)? onIceGatheringState;
  @override
  RTCIceGatheringState? iceGatheringState =
      RTCIceGatheringState.RTCIceGatheringStateComplete;

  @override
  Future<RTCRtpSender> addTrack(
    MediaStreamTrack track, [
    MediaStream? stream,
  ]) async {
    tracks.add(track);
    return _Sender();
  }

  @override
  Future<RTCDataChannel> createDataChannel(
    String label,
    RTCDataChannelInit dataChannelDict,
  ) async {
    this.label = label;
    return channel;
  }

  @override
  Future<RTCSessionDescription> createOffer([
    Map<String, dynamic>? constraints,
  ]) async => RTCSessionDescription('offer-sdp', 'offer');

  @override
  Future<void> setLocalDescription(RTCSessionDescription description) async {}

  @override
  Future<RTCSessionDescription?> getLocalDescription() async =>
      RTCSessionDescription('offer-sdp-with-candidates', 'offer');

  @override
  Future<void> setRemoteDescription(RTCSessionDescription description) async =>
      remote = description.sdp;

  @override
  Future<List<RTCRtpReceiver>> getReceivers() async => const [];

  @override
  Future<List<StatsReport>> getStats([MediaStreamTrack? track]) async =>
      const [];

  @override
  Future<void> close() async => log.add('peer.close');

  @override
  Future<void> dispose() async => log.add('peer.dispose');
}

class _Media extends VoiceMedia {
  _Media(this.log) : stream = _Stream(log), peerConnection = _Peer(log);
  final List<String> log;
  final _Stream stream;
  final _Peer peerConnection;

  @override
  Future<MediaStream> microphone(Map<String, dynamic> constraints) async =>
      stream;
  @override
  Future<RTCPeerConnection> peer() async => peerConnection;
  @override
  Future<void> setMicrophoneMute(bool mute, MediaStreamTrack track) async =>
      log.add('mute $mute');
  @override
  Future<void> setSpeakerphoneOn(bool on) async =>
      log.add('speaker ${on ? 'on' : 'off'}');
}

void main() {
  late List<String> log;
  late FakeApi api;
  late _Media media;
  late int connected;
  late int closed;
  late List<String> errors;

  WebRtcVoiceTransport transport({Duration ice = const Duration(seconds: 10)}) {
    log = [];
    connected = 0;
    closed = 0;
    errors = [];
    api = FakeApi()
      ..on(
        'POST /voice/sessions',
        (_) => {'session_id': 's1', 'sdp': 'answer-sdp'},
      );
    media = _Media(log);
    return WebRtcVoiceTransport(
      VoiceTransportCallbacks(
        onConnected: () => connected++,
        onError: errors.add,
        onActivity: (_) {},
        onClosed: () => closed++,
      ),
      api,
      media: media,
      iceTimeout: ice,
      closedTimeout: const Duration(milliseconds: 20),
    );
  }

  List<String> network() => [
    for (final c in api.calls) '${c.method} ${c.path}',
  ];

  test(
    'connect posts the complete offer and answers with the server SDP',
    () async {
      final t = transport();
      await t.connect(
        agentId: 'a-sara',
        threadId: 't-sara',
        incomingCallId: 'ic-1',
      );
      final post = api.calls.single;
      expect(post.path, '/voice/sessions');
      expect(post.body, {
        'agent_id': 'a-sara',
        'thread_id': 't-sara',
        'mode': 'gpt_live',
        'client_nonce': t.nonce,
        'sdp': 'offer-sdp-with-candidates',
        'incoming_call_id': 'ic-1',
      });
      expect(t.sessionId, 's1');
      expect(media.peerConnection.remote, 'answer-sdp');
      expect(media.peerConnection.label, 'oai-events');
      expect(media.peerConnection.tracks, [media.stream.track]);
      // In-call audio starts on the speaker.
      expect(log, contains('speaker on'));
      await t.close();
    },
  );

  test('data-channel events drive the call', () async {
    final t = transport();
    await t.connect(agentId: 'a-sara', threadId: 't-sara');
    final channel = media.peerConnection.channel;
    channel.receive('{"type":"session.started"}');
    expect(connected, 1);
    channel.receive('{"type":"session.output_audio.delta"}');
    channel.receive('{"type":"something.else"}');
    expect(errors, isEmpty);
    channel.receive('{"type":"error"}');
    expect(errors, ['voice_connection_failed']);
    channel.receive('not json');
    expect(errors, ['voice_connection_failed', 'voice_response_invalid']);
    await t.close();
  });

  test('ending a muted call: session.close, the server confirms, DELETE; the mute is '
      'cleared and the peer disposed', () async {
    final t = transport();
    await t.connect(agentId: 'a-sara', threadId: 't-sara');
    await t.setMuted(true);
    expect(media.stream.track.enabled, isFalse);
    final channel = media.peerConnection.channel;
    channel.onSend = (text) {
      if (text.contains('session.close')) {
        channel.receive('{"type":"session.closed"}');
      }
    };
    log.clear();
    await t.close();
    expect(log, [
      'mute false',
      'track.stop',
      'channel.send {"type":"session.close"}',
      'channel.close',
      'speaker off',
      'peer.close',
      'stream.dispose',
      'peer.dispose',
    ]);
    expect(network(), ['POST /voice/sessions', 'DELETE /voice/sessions/s1']);
    expect(closed, 1);
    // Idempotent.
    await t.close();
    expect(closed, 1);
    expect(log.where((e) => e == 'peer.dispose'), hasLength(1));
  });

  test('an unmuted call does not touch the phone-wide mute', () async {
    final t = transport();
    await t.connect(agentId: 'a-sara', threadId: 't-sara');
    log.clear();
    await t.close();
    expect(log.where((e) => e.startsWith('mute')), isEmpty);
    expect(log, contains('peer.dispose'));
  });

  test(
    'no answer to session.close: the DELETE still follows after the wait',
    () async {
      final t = transport();
      await t.connect(agentId: 'a-sara', threadId: 't-sara');
      await t.close();
      expect(network().last, 'DELETE /voice/sessions/s1');
      expect(closed, 1);
    },
  );

  test(
    'ended before a session exists: cancel-initialization with the nonce',
    () async {
      final t = transport();
      media.peerConnection.iceGatheringState =
          RTCIceGatheringState.RTCIceGatheringStateGathering;
      final connecting = t.connect(agentId: 'a-sara', threadId: 't-sara');
      await Future<void>.delayed(Duration.zero);
      await t.close();
      await connecting;
      expect(network(), ['POST /voice/cancel-initialization']);
      expect(api.calls.single.body, {'client_nonce': t.nonce});
      expect(errors, isEmpty);
      expect(log, containsAllInOrder(['peer.close', 'peer.dispose']));
    },
  );

  test(
    'ICE gathering that never completes fails the call and cancels it',
    () async {
      final t = transport(ice: const Duration(milliseconds: 10));
      media.peerConnection.iceGatheringState =
          RTCIceGatheringState.RTCIceGatheringStateGathering;
      await t.connect(agentId: 'a-sara', threadId: 't-sara');
      expect(errors, ['voice_connection_failed']);
      expect(network(), ['POST /voice/cancel-initialization']);
      expect(closed, 1);
      expect(log, contains('peer.dispose'));
    },
  );

  test('without finalize nothing reaches the server', () async {
    final t = transport();
    await t.connect(agentId: 'a-sara', threadId: 't-sara');
    log.clear();
    await t.close(finalize: false);
    expect(network(), ['POST /voice/sessions']);
    expect(log, isNot(contains(startsWith('channel.send'))));
    expect(log, containsAllInOrder(['peer.close', 'peer.dispose']));
    expect(closed, 1);
  });

  test('a peer that fails is voice_connection_failed', () async {
    final t = transport();
    await t.connect(agentId: 'a-sara', threadId: 't-sara');
    media.peerConnection.onConnectionState!(
      RTCPeerConnectionState.RTCPeerConnectionStateFailed,
    );
    expect(errors, ['voice_connection_failed']);
    await t.close();
    expect(closed, 1);
  });

  group('pure pieces', () {
    test('dataChannelEventKind', () {
      expect(
        dataChannelEventKind('{"type":"session.started"}'),
        'session.started',
      );
      expect(
        dataChannelEventKind('{"type":"session.closed"}'),
        'session.closed',
      );
      expect(dataChannelEventKind('{"type":"error"}'), 'error');
      expect(
        dataChannelEventKind('{"type":"session.output_audio.delta"}'),
        'speaking',
      );
      expect(
        dataChannelEventKind('{"type":"session.output_transcript.delta"}'),
        'speaking',
      );
      expect(dataChannelEventKind('{"type":"input.something"}'), isNull);
      expect(dataChannelEventKind(''), isNull);
      expect(() => dataChannelEventKind('{nope'), throwsFormatException);
    });

    test('audioLevels reads the input and output meters', () {
      final levels = audioLevels([
        StatsReport('1', 'media-source', 0, {
          'kind': 'audio',
          'audioLevel': 0.2,
        }),
        StatsReport('2', 'outbound-rtp', 0, {
          'mediaType': 'audio',
          'audioLevel': 0.4,
        }),
        StatsReport('3', 'inbound-rtp', 0, {'kind': 'audio', 'audioLevel': 3}),
        StatsReport('4', 'inbound-rtp', 0, {
          'kind': 'video',
          'audioLevel': 0.9,
        }),
        StatsReport('5', 'inbound-rtp', 0, {'kind': 'audio'}),
      ]);
      expect(levels.input, 0.4);
      expect(levels.output, 1.0);
      expect(audioLevels(const []), (input: 0.0, output: 0.0));
    });

    test('voiceNonce: time and two random parts in base 36', () {
      final nonce = voiceNonce();
      expect(nonce, matches(RegExp(r'^[0-9a-z]+-[0-9a-z]+-[0-9a-z]+$')));
      expect(voiceNonce(), isNot(nonce));
    });
  });
}
