/// Port of the text of packages/core/src/owner-actions.ts: owner action cards (one spec for
/// Web and Mobile), the Mandate lines and the cards' error texts. A card renders only the
/// server's facts (OwnerAction JSON) in the owner's language; tickers, numbers and times are
/// isolated. Nothing here decides anything: the tap goes to the owner-session route.
library;

import '../bidi.dart' show dotSeparator;
import '../fill.dart';
import 'chatgpt_plan.dart';
import 'core_tables.g.dart';
import 'text.dart';
import 'trading_readiness.dart';
import 'values.dart';

/// The refusal that means the card changed on another screen: read it again
/// (owner-actions.ts:997-999 `OWNER_ACTION_CHANGED`).
const String ownerActionChanged = 'owner_action_card_changed';

/// The card labels in [locale]'s language (owner-actions.ts:392-394).
OwnerActionText ownerActionText(String locale) =>
    ownerActionLabels[language(locale)]!;

/// What a button sends: confirm (with an outcome for a resolve card, or the Mandate card's
/// mode) or cancel (owner-actions.ts:396-405).
class OwnerActionButton {
  const OwnerActionButton({
    required this.key,
    required this.label,
    required this.decision,
    required this.primary,
    this.outcome,
    this.tradingMode,
  });

  /// confirm, cancel, an attested outcome or a trading mode.
  final String key;
  final String label;

  /// confirm or cancel.
  final String decision;

  /// executed, not_executed or unknown (a resolve card).
  final String? outcome;

  /// The Mandate card: the mode this button shows; the tap applies exactly this mode.
  final String? tradingMode;
  final bool primary;

  Map<String, Object?> toJson() => {
    'key': key,
    'label': label,
    'decision': decision,
    'outcome': ?outcome,
    'trading_mode': ?tradingMode,
    'primary': primary,
  };
}

/// One field of a Secret card's form; `password` masks it (owner-actions.ts:419-425).
class SecretFormField {
  const SecretFormField({
    required this.key,
    required this.label,
    required this.type,
    required this.required,
  });

  final String key;
  final String label;

  /// password, text or url.
  final String type;
  final bool required;

  Map<String, Object?> toJson() => {
    'key': key,
    'label': label,
    'type': type,
    'required': required,
  };
}

/// A Secret card's form while it waits (owner-actions.ts:426-427).
class SecretForm {
  const SecretForm({required this.fields, required this.submit});

  final List<SecretFormField> fields;
  final String submit;

  Map<String, Object?> toJson() => {
    'fields': [for (final field in fields) field.toJson()],
    'submit': submit,
  };
}

/// A ChatGPT plan card's sign-in while it waits (chatgpt-plan.ts:82-89).
class ChatGptSignInForm {
  const ChatGptSignInForm({
    required this.continueLabel,
    required this.address,
    required this.submit,
    required this.otherAccount,
  });

  final String continueLabel;
  final String address;
  final String submit;
  final String otherAccount;

  Map<String, Object?> toJson() => {
    'continue': continueLabel,
    'address': address,
    'submit': submit,
    'otherAccount': otherAccount,
  };
}

/// The whole card for one locale (owner-actions.ts:428-445). No remaining card offers
/// options, so [options] is always empty; it is kept for the spec's shape.
class OwnerActionSpec {
  const OwnerActionSpec({
    required this.title,
    required this.lines,
    required this.hint,
    required this.buttons,
    required this.secret,
    required this.signIn,
    required this.passkey,
    required this.outcome,
    this.options = const [],
  });

  final String title;

  /// Server facts, one per line, each read in its own direction.
  final List<String> lines;
  final String? hint;
  final List<Map<String, Object?>> options;

  /// Shown while pending; empty once the card is settled.
  final List<OwnerActionButton> buttons;
  final SecretForm? secret;
  final ChatGptSignInForm? signIn;
  final bool passkey;

  /// The settled line ("This card expired. Nothing changed."), null while it waits.
  final String? outcome;

  Map<String, Object?> toJson() => {
    'title': title,
    'lines': lines,
    'hint': hint,
    'options': options,
    'buttons': [for (final button in buttons) button.toJson()],
    'secret': secret?.toJson(),
    'signIn': signIn?.toJson(),
    'passkey': passkey,
    'outcome': outcome,
  };
}

String? _accountLabel(Object? account, OwnerActionText text) {
  if (account is! Map) return null;
  final label = str(account['label']);
  if (truthy(label)) return isolate(label!);
  return account['provider'] == 'simulation'
      ? text.simulation
      : text.brokerAccount;
}

String _actionLabel(String? action, String lang) {
  if (action == null || action.isEmpty) return '';
  return tradeActionLabels[lang]![action] ?? isolate(action);
}

/// A broker card's purpose (raised only by the broker tools); null for every other card
/// (owner-actions.ts:461-468).
String? brokerPurpose(Map<String, Object?> card) {
  final secret = obj(card['facts'])['secret'];
  if (secret is! Map) return null;
  return secret['destination'] == 'broker' && !truthy(secret['connect'])
      ? str(secret['purpose']) ?? 'connect'
      : null;
}

/// A saved broker card whose provisioning failed (owner-actions.ts:470-480).
bool brokerCardFailed(Map<String, Object?> card) =>
    card['status'] == 'confirmed' &&
    brokerPurpose(card) != null &&
    obj(card['result'])['provisioning'] == 'failed';

/// The status beside a folded card's kind (owner-actions.ts:482-495).
String ownerActionStatus(Map<String, Object?> card, String locale) {
  final text = ownerActionText(locale);
  return switch (card['status']) {
        'pending' => text.statusPending,
        'confirmed' => text.statusConfirmed,
        'cancelled' => text.statusCancelled,
        'expired' => text.statusExpired,
        'superseded' => text.statusSuperseded,
        _ => null,
      } ??
      '';
}

String? _settledLine(
  Map<String, Object?> card,
  OwnerActionText text,
  String lang,
) {
  final status = card['status'];
  final result = obj(card['result']);
  if (status == 'pending') return null;
  if (status == 'cancelled') {
    return card['kind'] == 'supervision_paused'
        ? text.keptPaused
        : text.cancelled;
  }
  if (status == 'confirmed') {
    switch (card['kind']) {
      case 'trading_mode':
        // Still the agent's switch: its lines show the mode now.
        return null;
      case 'supervision_paused':
        return text.resumedWork;
      case 'secret':
        final purpose = brokerPurpose(card);
        if (purpose != null) {
          final provisioning = result['provisioning'];
          return provisioning == 'failed'
              ? text.brokerFailed
              : provisioning == 'connected'
              ? purpose == 'connect'
                    ? text.brokerConnected
                    : text.brokerChanged
              : provisioning == 'linked'
              ? text.brokerLinked
              : purpose == 'connect'
              ? text.brokerSaved
              : text.brokerSending;
        }
        if (isChatGptCard(card)) {
          final plan = chatgptText(lang);
          final account = str(result['account']);
          return truthy(account)
              ? fill(plan.connected, null, {'account': isolate(account!)})
              : plan.connectedNoAccount;
        }
        return truthy(obj(obj(card['facts'])['secret'])['connect'])
            ? text.connected
            : text.secretSaved;
      case 'settle_operation':
        return result['outcome'] == 'executed'
            ? text.recordedExecuted
            : result['outcome'] == 'not_executed'
            ? text.recordedNotExecuted
            : text.recordedUnknown;
    }
  }
  return switch (card['status_reason']) {
    'operation_already_settled' => text.alreadySettled,
    'done_by_another_card' => text.doneElsewhere,
    'same_choice_on_another_card' => text.sameOnAnotherCard,
    'grant_already_active' => text.alreadySigned,
    'agent_already_removed' => text.agentRemoved,
    'broker_connection_changed' => text.connectionChanged,
    'supervision_pause_ended' => text.alreadyEnded,
    'watch_expired' => text.watchExpired,
    'credential_already_configured' => text.alreadyConnected,
    'secret_name_in_use' => text.secretNameInUse,
    'expired' => text.expired,
    _ => status == 'expired' ? text.expired : text.noLongerApplies,
  };
}

/// «التفويض: يستأذن» / "Trading mode: Ask"; null when the agent has no mode
/// (owner-actions.ts:574-580).
String? mandateLine(String? mode, String locale) {
  final text = ownerActionText(locale);
  if (mode == 'full') return '${text.mandateTitle}: ${text.modeFull}';
  if (mode == 'ask') return '${text.mandateTitle}: ${text.modeAsk}';
  return null;
}

/// The line under the mode: an unconfirmed operation, otherwise the mode's first clause
/// (owner-actions.ts:582-598).
String? tradingSubLine(int? unresolved, String? mode, String locale) {
  final text = ownerActionText(locale);
  final count = unresolved ?? 0;
  if (count == 1) return text.unresolvedOne;
  if (count > 1) {
    return fill(text.unresolvedMany, null, {
      'n': language(locale) == 'ar' ? isolate('$count') : '$count',
    });
  }
  if (mode == 'ask') return text.modeAskClause;
  if (mode == 'full') return text.modeFullClause;
  return null;
}

/// The one line after a Mandate tap; the withdrawn count is the server's, and only for Full
/// (owner-actions.ts:600-619).
String modeChangeLine(String name, String mode, num withdrawn, String locale) {
  final text = ownerActionText(locale);
  final head = '$name: ${mode == 'full' ? text.modeFull : text.modeAsk}';
  if (mode != 'full' || withdrawn != withdrawn.truncate() || withdrawn < 1) {
    return head;
  }
  final n = jsString(withdrawn);
  final tail = withdrawn == 1
      ? text.withdrawnOne
      : withdrawn == 2
      ? text.withdrawnTwo
      : fill(text.withdrawnMany, null, {
          'n': language(locale) == 'ar' ? isolate(n) : n,
        });
  return '$head$dotSeparator$tail';
}

String _nameList(List<String> names, String lang) =>
    names.map(isolate).join(listSeparator(lang));

List<String> _pauseLines(Map<String, Object?> card, OwnerActionText text) {
  final pause = obj(card['facts'])['supervision'];
  if (pause is! Map) return [];
  final supervisor = str(pause['supervisor_name']);
  final by = truthy(supervisor) ? isolate(supervisor!) : text.anAgent;
  final lines = [
    '${text.pausedBy}: $by${truthy(pause['from_owner_message']) ? '$dotSeparator${text.fromYourMessage}' : ''}',
  ];
  final names = strings(pause['supervised_names']);
  if (names.isNotEmpty && names.first.isNotEmpty) {
    lines.add('${text.agent}: ${isolate(names.first)}');
  }
  final target = str(pause['target']);
  if (truthy(target)) {
    final targetLabel = str(pause['target_label']);
    final label = truthy(targetLabel)
        ? '$dotSeparator${isolate(targetLabel!)}'
        : '';
    final key = ownerActionTargetLabel[target];
    lines.add('${text.pausedWhat}: ${key == null ? '' : text[key]}$label');
  }
  return lines;
}

String _connectTitle(Object? target, Object? service, OwnerActionText text) {
  if (service == 'x') return text.connectX;
  return switch (target) {
        'mcp_server' => text.connectMcp,
        'news_feed' => text.connectFeed,
        'brave_search' => text.connectBrave,
        'economic_calendar' => text.connectCalendar,
        'broker' => text.connectBroker,
        'model_provider' => text.connectModel,
        _ => null,
      } ??
      '';
}

SecretForm _secretForm(Map<String, Object?> secret, OwnerActionText text) {
  final roles = {
    'token': text.fieldToken,
    'api_key': text.fieldApiKey,
    'server_url': text.fieldServerUrl,
    'feed_url': text.fieldFeedUrl,
  };
  return SecretForm(
    fields: [
      for (final raw in list(secret['fields']))
        () {
          final field = obj(raw);
          final key = jsString(field['key']);
          final role = str(field['role']);
          return SecretFormField(
            key: key,
            label:
                str(field['label']) ?? (truthy(role) ? roles[role] ?? '' : key),
            type: truthy(field['secret'])
                ? 'password'
                : role == 'feed_url' || role == 'server_url'
                ? 'url'
                : 'text',
            required: field['required'] is bool
                ? field['required'] as bool
                : true,
          );
        }(),
    ],
    submit: truthy(secret['connect']) ? text.connect : text.secretSave,
  );
}

List<String> _savedLabels(
  Map<String, Object?> secret,
  List<SecretFormField> fields,
  List<String> names,
) {
  final raw = list(secret['fields']).map(obj).toList();
  final labels = <String>[];
  for (var index = 0; index < names.length; index++) {
    SecretFormField? field;
    if (secret['connect'] == 'model_provider') {
      final at = raw.indexWhere((item) => item['role'] == 'api_key');
      field = at >= 0 && at < fields.length ? fields[at] : null;
    } else if (truthy(secret['connect'])) {
      field = index < fields.length ? fields[index] : null;
    } else {
      for (final item in fields) {
        if (item.key == names[index]) {
          field = item;
          break;
        }
      }
    }
    if (field != null) labels.add(field.label);
  }
  return labels;
}

/// Whether the card still offers its buttons: a pending card, or a Mandate card the owner
/// already tapped, which stays the agent's switch while the agent exists
/// (owner-actions.ts:988-995).
bool ownerActionLive(Map<String, Object?> card) =>
    card['status'] == 'pending' ||
    (card['kind'] == 'trading_mode' &&
        card['status'] == 'confirmed' &&
        truthy(obj(card['facts'])['trading_mode']));

/// The whole card for one locale: title, fact lines, hint, buttons and settled line. [card]
/// is the OwnerAction JSON (owner-actions.ts:741-986).
OwnerActionSpec ownerActionCard(
  Map<String, Object?> card,
  String locale,
  DateTime now,
) {
  final lang = language(locale);
  final text = ownerActionLabels[lang]!;
  final facts = obj(card['facts']);
  final account = truthy(facts['several_accounts'])
      ? _accountLabel(facts['account'], text)
      : null;
  final lines = <String>[];
  var title = '';
  String? hint;
  var buttons = <OwnerActionButton>[];
  SecretForm? form;
  ChatGptSignInForm? signIn;
  List<OwnerActionButton> pair(String confirm, String cancel) => [
    OwnerActionButton(
      key: 'confirm',
      label: confirm,
      decision: 'confirm',
      primary: true,
    ),
    OwnerActionButton(
      key: 'cancel',
      label: cancel,
      decision: 'cancel',
      primary: false,
    ),
  ];
  switch (card['kind']) {
    case 'trading_mode':
      title = text.mandateTitle;
      final mode = str(facts['trading_mode']);
      final agent = facts['agent'];
      if (agent is! Map || !truthy(agent['exists']) || !truthy(mode)) {
        lines.add(text.mandateGone);
        break;
      }
      final agentName = str(agent['name']);
      final name = truthy(agentName)
          ? '${isolate(agentName!)}$dotSeparator'
          : '';
      lines.add(
        '$name${text.mandateNow}: ${mode == 'full' ? text.modeFull : text.modeAsk}',
      );
      lines.add(mode == 'full' ? text.modeFullLine : text.modeAskLine);
      if (truthy(facts['active_grant'])) lines.add(text.mandateGrantStays);
      // The grants it held before the trading mode, named once by the migration.
      final previous = list(facts['previous_grants']).map(obj).toList();
      if (previous.isNotEmpty) {
        final grants = [
          for (final grant in previous)
            [
              truthy(grant['full_delegation'])
                  ? text.mandatePreviousFull
                  : grant['symbol_scope'] == 'account'
                  ? text.mandatePreviousAllPairs
                  : strings(grant['symbols'])
                        .map(isolate)
                        .join(listSeparator(lang)),
              truthy(facts['several_accounts'])
                  ? _accountLabel(grant['account'], text)
                  : null,
            ].where(truthy).join(dotSeparator),
        ];
        // Several grants: the plural line, and a semicolon between grants, since a comma
        // already separates the markets inside one.
        lines.add(
          grants.length > 1
              ? fill(text.mandatePreviousGrants, null, {
                  'grants': grants.join(lang == 'ar' ? '؛ ' : '; '),
                })
              : fill(text.mandatePreviousGrant, null, {'grant': grants.first}),
        );
      }
      // One button for the other mode; the tap applies the mode this button shows.
      final other = mode == 'full' ? 'ask' : 'full';
      hint = other == 'full' ? text.mandateToFull : text.mandateToAsk;
      buttons = [
        OwnerActionButton(
          key: other,
          label: other == 'full' ? text.modeFull : text.modeAsk,
          decision: 'confirm',
          tradingMode: other,
          primary: true,
        ),
      ];
    case 'settle_operation':
      title = text.settleKind;
      lines.add(text.resolveTitle);
      final operation = facts['operation'];
      if (operation is Map) {
        final volume = str(operation['volume']);
        final symbol = str(operation['symbol']);
        final what = [
          _actionLabel(str(operation['action']), lang),
          if (truthy(volume)) isolate(volume!),
          if (truthy(symbol)) isolate(symbol!),
        ].join(' ');
        final submitted = operation['submitted_at'];
        final when = truthy(submitted)
            ? '$dotSeparator${text.at} ${readinessTime(submitted!, locale, now)}'
            : '';
        final byAgent = str(operation['by_agent_name']);
        final who = truthy(operation['by_owner'])
            ? text.byYou
            : '${text.by} ${truthy(byAgent) ? isolate(byAgent!) : text.anAgent}';
        lines.add('$what$when$dotSeparator$who');
        if (account != null && account.isNotEmpty) {
          lines.add('${text.account}: $account');
        }
      }
      hint = '${text.resolveHint} ${text.resolveRecord}';
      buttons = [
        OwnerActionButton(
          key: 'executed',
          label: text.executed,
          decision: 'confirm',
          outcome: 'executed',
          primary: false,
        ),
        OwnerActionButton(
          key: 'not_executed',
          label: text.notExecuted,
          decision: 'confirm',
          outcome: 'not_executed',
          primary: false,
        ),
        OwnerActionButton(
          key: 'unknown',
          label: text.unknown,
          decision: 'confirm',
          outcome: 'unknown',
          primary: false,
        ),
      ];
      if (obj(card['result'])['outcome'] == 'unknown') {
        // Answered Unknown: still uncertain and held; Executed or Not executed remain.
        lines.add(text.recordedUnknown);
        buttons = buttons
            .where((button) => button.outcome != 'unknown')
            .toList();
      }
    case 'supervision_paused':
      title = text.pauseTitle;
      lines.addAll(_pauseLines(card, text));
      final supervision = facts['supervision'];
      if (supervision is! Map || !truthy(supervision['active'])) {
        // Resumed elsewhere (Lonora, the owner): the card can only be dismissed.
        hint = text.pauseEnded;
        buttons = [
          OwnerActionButton(
            key: 'cancel',
            label: text.keep,
            decision: 'cancel',
            primary: false,
          ),
        ];
        break;
      }
      // The owner's pause from a control is lifted only by the owner's control or this card;
      // one the owner asked for in chat also by an agent acting on the owner's message.
      hint = !truthy(supervision['owner_holds'])
          ? text.pauseHint
          : truthy(supervision['from_owner_message'])
          ? text.pauseOwnerAsked
          : text.pauseOwnerHolds;
      buttons = pair(text.resumeWork, text.keepPaused);
    case 'secret':
      final secret = facts['secret'] is Map ? obj(facts['secret']) : null;
      title = secret != null && truthy(secret['connect'])
          ? _connectTitle(secret['connect'], secret['service'], text)
          : text.secretTitle;
      final agentName = str(secret?['agent_name']);
      final askedBy = truthy(agentName)
          ? fill(text.secretAskedBy, null, {'agent': isolate(agentName!)})
          : null;
      if (secret != null &&
          secret['destination'] == 'broker' &&
          secret['account'] is Map) {
        // Raised only by the broker tools: every word is ours, the account is server fact.
        final brokerAccount = obj(secret['account']);
        title = secret['purpose'] == 'rotate_password'
            ? text.brokerRotateTitle
            : secret['purpose'] == 'replace_token'
            ? text.brokerTokenTitle
            : text.brokerConnectTitle;
        lines.add(
          fill(text.brokerAccountLine, null, {
            'login': isolate(jsString(brokerAccount['login'])),
            'server': isolate(jsString(brokerAccount['server'])),
            'platform': jsString(brokerAccount['platform']).toUpperCase(),
          }),
        );
        final serverFrom = str(secret['server_from']);
        if (truthy(serverFrom)) {
          lines.add(
            fill(text.brokerMoveLine, null, {
              'from': isolate(serverFrom!),
              'server': isolate(jsString(brokerAccount['server'])),
            }),
          );
        }
        if (askedBy != null) lines.add(askedBy);
        hint = text.secretBroker;
        form = SecretForm(
          fields: [
            for (final raw in list(secret['fields']))
              SecretFormField(
                key: jsString(obj(raw)['key']),
                label: obj(raw)['key'] != 'METAAPI_TOKEN'
                    ? text.brokerPassword
                    : secret['purpose'] == 'replace_token'
                    ? text.brokerTokenNew
                    : text.brokerToken,
                type: 'password',
                required: true,
              ),
          ],
          submit: text.secretSave,
        );
      } else if (secret != null && isChatGptCard(card)) {
        // The Secret card with a sign-in in place of the key field: the paste step is said
        // before it happens, since OpenAI's callback page does not open on a server.
        final plan = chatgptText(lang);
        title = plan.title;
        lines.addAll([plan.plan, plan.stepSignIn, plan.stepPaste]);
        if (askedBy != null) lines.add(askedBy);
        hint = plan.hint;
        signIn = ChatGptSignInForm(
          continueLabel: plan.continue_,
          address: plan.address,
          submit: plan.connect,
          otherAccount: plan.otherAccount,
        );
      } else if (secret != null) {
        // The label, field labels and details are the agent's words; every other word is ours.
        final label = str(secret['label']);
        if (truthy(label)) lines.add(isolate(label!));
        final detailName = str(obj(secret['details'])['name']);
        if (truthy(detailName) && secret['connect'] != 'brave_search') {
          lines.add('${text.fieldName}: ${isolate(detailName!)}');
        }
        if (askedBy != null) lines.add(askedBy);
        form = _secretForm(secret, text);
        // What each value is saved as, and the saved values it would replace: never silently,
        // and by the field's label, never by the workspace name it is stored under (17).
        final saves = _savedLabels(
          secret,
          form.fields,
          strings(secret['saves_as']),
        );
        if (saves.isNotEmpty) {
          lines.add(
            fill(text.secretSavesAs, null, {'fields': _nameList(saves, lang)}),
          );
        }
        final replaces = _savedLabels(
          secret,
          form.fields,
          strings(secret['replaces']),
        );
        if (replaces.isNotEmpty) {
          lines.add(
            fill(text.secretReplaces, null, {
              'fields': _nameList(replaces, lang),
            }),
          );
        }
        final fields = list(secret['fields']).map(obj);
        hint = secret['connect'] == 'model_provider'
            ? fields.any((field) => field['role'] == 'server_url')
                  ? '${text.modelHint} ${text.modelEndpointHint}'
                  : text.modelHint
            : secret['destination'] == 'broker'
            ? text.secretBroker
            : !truthy(secret['connect'])
            ? text.secretWorkspace
            : secret['service'] == 'x'
            ? '${text.connectHint} ${text.connectXHint}'
            : text.connectHint;
      }
      // Save is the form's own submit: the values go to the card's route, never here.
      buttons = [
        OwnerActionButton(
          key: 'cancel',
          label: text.notNow,
          decision: 'cancel',
          primary: false,
        ),
      ];
  }
  final pending = ownerActionLive(card);
  return OwnerActionSpec(
    title: title,
    lines: lines,
    hint: pending ? hint : null,
    buttons: pending ? buttons : const [],
    secret: pending ? form : null,
    signIn: pending ? signIn : null,
    passkey: pending && card['requires_passkey'] == true,
    outcome: _settledLine(card, text, lang),
  );
}

/// Owner text for a card decision's refusal, else a ChatGPT sign-in refusal's; null if
/// neither (owner-actions.ts:1153-1157).
String? ownerActionError(String? code, String locale) {
  final entry = code == null || code.isEmpty ? null : ownerActionErrors[code];
  return entry != null ? entry.pick(locale) : chatgptError(code, locale);
}
