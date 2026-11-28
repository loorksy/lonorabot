import '../../app/routes.dart';

/// «التعطل والاستعادة», narrowed to [account] when given (apps/web shell/routes.ts
/// `/app/recovery?account=`).
String recoveryLocation({String? account}) => account == null || account.isEmpty
    ? Routes.recovery
    : Uri(
        path: Routes.recovery,
        queryParameters: {'account': account},
      ).toString();
