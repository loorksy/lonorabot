import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/deep_links.dart';
import 'package:lonora/core/api/api_client.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/core/json.dart';
import 'package:lonora/core/models/models.dart';
import 'package:lonora/state/app_state.dart';

void main() {
  group('normalizeServerUrl (apps/mobile/lib/api.ts rules)', () {
    test('strips trailing /api and slashes', () {
      expect(
        normalizeServerUrl('https://lonora.example.com/api/'),
        'https://lonora.example.com',
      );
      expect(
        normalizeServerUrl('https://lonora.example.com/'),
        'https://lonora.example.com',
      );
      expect(
        normalizeServerUrl('  https://x.example/sub/api  '),
        'https://x.example/sub',
      );
    });
    test('adds https when the scheme is missing', () {
      expect(
        normalizeServerUrl('lonora.example.com'),
        'https://lonora.example.com',
      );
    });
    test('rejects credentials, query, fragment and other schemes', () {
      expect(normalizeServerUrl('https://u:p@x.example'), isNull);
      expect(normalizeServerUrl('https://x.example/?a=1'), isNull);
      expect(normalizeServerUrl('https://x.example/#t'), isNull);
      expect(normalizeServerUrl('ftp://x.example'), isNull);
      expect(normalizeServerUrl(''), isNull);
    });
    test('local hosts', () {
      for (final h in [
        'localhost',
        'box.local',
        '10.0.0.2',
        '192.168.1.10',
        '172.20.1.1',
        '127.0.0.1',
      ]) {
        expect(isLocalHost(h), isTrue, reason: h);
      }
      for (final h in ['example.com', '172.32.0.1', '8.8.8.8']) {
        expect(isLocalHost(h), isFalse, reason: h);
      }
    });
  });

  group('ApiError', () {
    test('parses the Lonora envelope', () {
      final e = ApiError.fromResponse(409, {
        'code': 'agent_paused',
        'request_id': 'abc',
      });
      expect(e.code, 'agent_paused');
      expect(e.requestId, 'abc');
      expect(e.serverAnswered, isTrue);
    });
    test('bare proxy 502/504 means the API never saw it', () {
      expect(ApiError.fromResponse(502, null).serverAnswered, isFalse);
      expect(ApiError.fromResponse(504, '<html>').serverAnswered, isFalse);
      expect(ApiError.network().serverAnswered, isFalse);
    });
    test('maintenance 503 is an answer', () {
      final e = ApiError.fromResponse(503, {'error': 'maintenance'});
      expect(e.code, 'maintenance');
      expect(e.serverAnswered, isTrue);
    });
    test('retry-after from body or header', () {
      expect(
        ApiError.fromResponse(409, {
          'code': 'run_retry_too_early',
          'retry_after_seconds': 30,
        }).retryAfter,
        const Duration(seconds: 30),
      );
      expect(
        ApiError.fromResponse(429, {
          'code': 'rate_limited',
        }, retryAfterHeader: '60').retryAfter,
        const Duration(seconds: 60),
      );
    });
  });

  group('deep links', () {
    test('connect links require https for remote hosts', () {
      expect(
        DeepLinks.locationFor(
          Uri.parse(
            'lonora://connect?server=https://a.example&token=abcdefghijklmnopqrstuvwxyz',
          ),
        ),
        '/connect?server=https%3A%2F%2Fa.example&token=abcdefghijklmnopqrstuvwxyz',
      );
      expect(
        DeepLinks.locationFor(
          Uri.parse('lonora://connect?server=http://a.example'),
        ),
        '/connect',
      );
      expect(
        DeepLinks.locationFor(
          Uri.parse('lonora://connect?server=http://192.168.1.5:8000'),
        ),
        '/connect?server=http%3A%2F%2F192.168.1.5%3A8000',
      );
    });
    test('invalid setup tokens are dropped', () {
      expect(
        DeepLinks.locationFor(
          Uri.parse('lonora://connect?server=https://a.example&token=short'),
        ),
        '/connect?server=https%3A%2F%2Fa.example',
      );
    });
    test('threads and agents', () {
      expect(
        DeepLinks.locationFor(Uri.parse('lonora://thread/t1?around=42')),
        '/chats/thread/t1?around=42',
      );
      expect(
        DeepLinks.locationFor(Uri.parse('lonora://thread/t1')),
        '/chats/thread/t1',
      );
      expect(
        DeepLinks.locationFor(Uri.parse('lonora://agent/a1')),
        '/agent/a1',
      );
      expect(
        DeepLinks.locationFor(Uri.parse('https://evil.example/thread/t1')),
        isNull,
      );
    });
  });

  group('server rule: https, plain http only for local hosts', () {
    Matcher refused() => throwsA(
      isA<ApiError>().having((e) => e.code, 'code', 'auth_httpsRequired'),
    );

    test('serverAllowed', () {
      expect(serverAllowed('https://lonora.example.com'), isTrue);
      expect(serverAllowed('http://192.168.1.5:8840'), isTrue);
      expect(serverAllowed('http://localhost:8840'), isTrue);
      expect(serverAllowed('http://lonora.example.com'), isFalse);
      expect(serverAllowed('ws://lonora.example.com'), isFalse);
    });

    test('every session request to a remote http server is refused', () {
      final api = ApiClient(userAgent: 'test')
        ..configure(server: 'http://lonora.example.com', token: 'tok');
      // get/post/upload/bytes/downloadTo all build their URL here.
      expect(() => api.resolve('/agents'), refused());
      api.configure(server: 'http://192.168.1.5:8840', token: 'tok');
      expect(
        api.resolve('/agents').toString(),
        'http://192.168.1.5:8840/api/agents',
      );
      api.configure(server: 'https://lonora.example.com', token: 'tok');
      expect(
        api.resolve('/agents').toString(),
        'https://lonora.example.com/api/agents',
      );
    });

    testWidgets('requests and probes are refused before they leave', (
      tester,
    ) async {
      final api = ApiClient(userAgent: 'test')
        ..configure(server: 'http://lonora.example.com', token: 'tok');
      await expectLater(api.post('/auth/logout'), refused());
      await expectLater(
        api.probe(
          'http://lonora.example.com',
          '/onboarding',
          method: 'POST',
          body: {'password': 'never sent'},
        ),
        refused(),
      );
    });
  });

  group('outbox entries', () {
    test('only plain text waits for the network', () {
      OutgoingMessage o(Json body) => OutgoingMessage(
        nonce: 'n',
        threadId: 't',
        body: body,
        delivery: Delivery.sending,
        createdAt: DateTime(2026),
      );
      expect(o({'content': 'hi'}).isPlain, isTrue);
      expect(o({'content': 'x', 'edited_from': 'm'}).isPlain, isFalse);
      expect(o({'content': 'x', 'input_answer': {}}).isPlain, isFalse);
      expect(o({'ui_submit': {}}).isPlain, isFalse);
      expect(o({'voice': {}}).isPlain, isFalse);
    });
    test('a send in flight when the app died is restored as queued', () {
      final restored = OutgoingMessage.fromJson({
        'nonce': 'n',
        'thread_id': 't',
        'body': {'content': 'hi', 'client_nonce': 'n'},
        'delivery': 'sending',
        'created_at': '2026-11-27T00:00:00Z',
      });
      expect(restored!.delivery, Delivery.queued);
    });
  });

  group('models parse real server samples', () {
    final samples = Directory(
      '/tmp/claude-0/-home-user-lonorabot/c777793c-4d08-5fcf-a248-25819dbbff0b/scratchpad/lonora-runtime/samples',
    );
    final available = samples.existsSync();

    test('agents, messages, run', () {
      final agents = asJsonList(
        jsonDecode(File('${samples.path}/agents-list.json').readAsStringSync()),
      ).map(Agent.fromJson).toList();
      expect(agents, isNotEmpty);
      expect(agents.first.id, isNotEmpty);
      final messages = asJsonList(
        jsonDecode(
          File('${samples.path}/thread-messages.json').readAsStringSync(),
        ),
      ).map(Message.fromJson).toList();
      expect(messages.first.fromOwner, isTrue);
      expect(messages.last.fromAgent, isTrue);
      expect(messages.first.seq < messages.last.seq, isTrue);
      final run = Run.fromJson(
        asJson(jsonDecode(File('${samples.path}/run.json').readAsStringSync())),
      );
      expect(run.id, isNotEmpty);
    }, skip: available ? false : 'local runtime samples not present');
  });
}
