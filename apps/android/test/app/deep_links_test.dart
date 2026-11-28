// The Lonora Cloud "Open in the app" link, lonora://connect?server=https://<handle>.lonora.io,
// kept stable: with or without a setup token it maps to the connect confirmation for that server
// only; a remote plain-http server, credentials or a missing server open the screen's "not
// valid" state instead. (The flow behind it: test/features/auth/auth_screens_test.dart.)
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/app/deep_links.dart';
import 'package:lonora/app/routes.dart';

String? map(String link) => DeepLinks.locationFor(Uri.parse(link));

void main() {
  const cloud = '/connect?server=https%3A%2F%2Fhandle.lonora.io';
  const token = 'abcdefghijklmnopqrstuvwxyz0123';

  test('a server alone: the confirmation for that server, no token', () {
    expect(map('lonora://connect?server=https://handle.lonora.io'), cloud);
    // The address as typed elsewhere: case, trailing slash and /api do not change it.
    expect(map('lonora://connect?server=https://Handle.Lonora.io/'), cloud);
    expect(map('lonora://connect?server=https://handle.lonora.io/api'), cloud);
    // An escaped server reads the same.
    expect(
      map('lonora://connect?server=https%3A%2F%2Fhandle.lonora.io'),
      cloud,
    );
    // An empty or malformed token is dropped, never passed on.
    expect(
      map('lonora://connect?server=https://handle.lonora.io&token='),
      cloud,
    );
    expect(
      map('lonora://connect?server=https://handle.lonora.io&token=a%20b'),
      cloud,
    );
  });

  test('a server and a setup token keep the token for that server', () {
    expect(
      map('lonora://connect?server=https://handle.lonora.io&token=$token'),
      '$cloud&token=$token',
    );
  });

  test('refused: remote http, credentials, no server', () {
    for (final link in [
      'lonora://connect?server=http://handle.lonora.io',
      'lonora://connect?server=https://u:p@handle.lonora.io',
      'lonora://connect?server=',
      'lonora://connect',
    ]) {
      expect(map(link), Routes.connect, reason: link);
    }
    // Plain http stays possible for a server at home.
    expect(
      map('lonora://connect?server=http://192.168.1.5:8840&token=$token'),
      '/connect?server=http%3A%2F%2F192.168.1.5%3A8840&token=$token',
    );
  });

  test('other schemes never connect', () {
    expect(
      map('https://handle.lonora.io/connect?server=https://evil.example'),
      isNull,
    );
  });
}
