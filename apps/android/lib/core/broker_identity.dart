// Shared by the market, the charts and an agent's market scope.
import '../l10n/l10n.dart';
import 'json.dart';

/// A connection's label without its broker login or ids (apps/mobile/lib/broker-identity.ts).
String brokerAccountLabel(L10n l10n, Json connection, int index) {
  final identity = asJson(asJson(connection['state'])['broker_identity']);
  final uuid = RegExp(
    r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
    caseSensitive: false,
  );
  if (identity.isNotEmpty &&
      asInt(identity['connection_version']) == asInt(connection['version'])) {
    final parts = [
      for (final key in ['broker', 'login', 'server'])
        if (asString(identity[key]) case final v?
            when v.trim().isNotEmpty &&
                v != connection['id'] &&
                v != asJson(connection['payload'])['account_id'] &&
                !uuid.hasMatch(v))
          v,
    ];
    if (parts.isNotEmpty) return parts.join(' · ');
  }
  final simulation = asJson(connection['payload'])['provider'] == 'simulation';
  return '${l10n.t(simulation ? 'simulation' : 'unverifiedBrokerAccount')} · ${index + 1}';
}
