// «وكيل جديد» in a stacked sheet: the «Create» pill, the avatar studio as the sheet's second page
// (faces, the colour popover), `POST /agents` for a flexible agent and its conversation, the
// discard question, layout in both directions; goldens of the form, the studio and the popover.
//
// Regenerate goldens with: flutter test --update-goldens test/features/agent_profile
import 'dart:ui' show CheckedState;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:lonora/avatar/avatar.dart';
import 'package:lonora/core/api/api_error.dart';
import 'package:lonora/design/design.dart';
import 'package:lonora/features/agents/create_agent_sheet.dart';
import 'package:lonora/features/agents/settings/avatar_editor.dart';
import 'package:lonora/features/groups/form_sheet.dart';

import 'wpe_harness.dart';

/// A page with one button that opens the sheet.
class _Home extends StatelessWidget {
  const _Home();

  @override
  Widget build(BuildContext context) => Center(
    child: TextButton(
      onPressed: () => showCreateAgentSheet(context),
      child: const Text('open'),
    ),
  );
}

Future<void> _open(
  WidgetTester tester, {
  String locale = 'en',
  Brightness brightness = Brightness.light,
}) async {
  await pumpScreen(
    tester,
    const _Home(),
    locale: locale,
    brightness: brightness,
  );
  await tapAndSettle(tester, find.text('open'));
}

/// Drags the sheet down by most of the screen from its header (or [from]), as a closing swipe
/// does.
Future<void> _dragDown(WidgetTester tester, {Finder? from}) async {
  await tester.timedDrag(
    from ?? find.byType(LnSheetHeader),
    const Offset(0, 600),
    const Duration(milliseconds: 300),
  );
  await tester.pumpAndSettle();
}

HeaderPillButton _pill(WidgetTester tester) =>
    tester.widget<HeaderPillButton>(find.byType(HeaderPillButton));

Finder _nameField() => find.descendant(
  of: find.byType(StadiumField),
  matching: find.byType(TextField),
);

const _created = {
  'id': 'a-new',
  'name': 'Scout',
  'avatar': 'face-wink',
  'color': '#3B82F6',
  'role': 'general',
  'scope_mode': 'flexible',
};

void main() {
  setUpAll(setUpWpeHarness);
  setUp(resetWpe);

  testWidgets('a stacked sheet: ✕, the title and «Create», enabled once the '
      'agent has a name', (tester) async {
    await _open(tester);
    expect(find.byType(CreateAgentForm), findsOneWidget);
    expect(
      ModalRoute.of(tester.element(find.byType(CreateAgentForm))),
      isA<FormSheetRoute<void>>(),
    );
    expect(find.text('New agent'), findsOneWidget);
    expect(_pill(tester).onPressed, isNull);
    await tester.enterText(_nameField(), '   ');
    await tester.pump();
    expect(_pill(tester).onPressed, isNull, reason: 'blank names are refused');
    await tester.enterText(_nameField(), 'Scout');
    await tester.pump();
    expect(_pill(tester).onPressed, isNotNull);
  });

  testWidgets('«Create» posts a flexible agent with its avatar, then opens '
      'its conversation', (tester) async {
    fakeApi
      ..on('POST /agents', (_, _) => _created)
      ..on(
        'POST /agents/a-new/conversation',
        (_, _) => {'id': 't-new', 'agent_id': 'a-new'},
      );
    await _open(tester);
    await tester.enterText(_nameField(), '  Scout ');
    await tester.pump();
    await tapAndSettle(tester, find.byType(HeaderPillButton));
    expect(fakeApi.callsTo('POST', '/agents').single.body, {
      'name': 'Scout',
      'scope_mode': 'flexible',
      'avatar': avatarFaces.first.id,
      'color': defaultAvatarColor,
    });
    expect(find.byType(CreateAgentForm), findsNothing);
    expect(shownRoute(tester), '/chats/thread/t-new');
  });

  testWidgets('a refused creation says why and keeps the form', (tester) async {
    fakeApi.on(
      'POST /agents',
      (_, _) => throw ApiError(status: 500, code: 'request_failed'),
    );
    await _open(tester);
    await tester.enterText(_nameField(), 'Scout');
    await tester.pump();
    await tapAndSettle(tester, find.byType(HeaderPillButton));
    expect(find.text('The request failed. Try again.'), findsOneWidget);
    expect(find.byType(CreateAgentForm), findsOneWidget);
    expect(shownRoute(tester), isNull);
  });

  testWidgets('the edit badge opens the studio as a second page; ✓ keeps the '
      'face and the colour picked in the popover', (tester) async {
    fakeApi
      ..on('POST /agents', (_, _) => _created)
      ..on(
        'POST /agents/a-new/conversation',
        (_, _) => {'id': 't-new', 'agent_id': 'a-new'},
      );
    await _open(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('Edit avatar'));
    expect(find.byType(AvatarStudio), findsOneWidget);
    expect(find.text('Edit avatar'), findsOneWidget);
    // A second page of the same sheet: › back, not a new sheet.
    expect(find.bySemanticsLabel('Back'), findsOneWidget);
    expect(find.byType(CreateAgentForm), findsOneWidget);
    await tapAndSettle(tester, find.bySemanticsLabel('Wink'));
    await tapAndSettle(tester, find.bySemanticsLabel('Choose a color'));
    expect(find.bySemanticsLabel(RegExp('^Color #')), findsNWidgets(11));
    await tapAndSettle(tester, find.bySemanticsLabel('Color #3B82F6'));
    expect(find.bySemanticsLabel(RegExp('^Color #')), findsNothing);
    await tapAndSettle(tester, find.bySemanticsLabel('Save'));
    expect(find.byType(AvatarStudio), findsNothing);
    await tester.enterText(_nameField(), 'Scout');
    await tester.pump();
    await tapAndSettle(tester, find.byType(HeaderPillButton));
    final body = fakeApi.callsTo('POST', '/agents').single.body! as Map;
    expect(body['avatar'], 'face-wink');
    expect(body['color'], '#3B82F6');
  });

  testWidgets('› back leaves the studio without its changes; Android back '
      'does too', (tester) async {
    await _open(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('Edit avatar'));
    await tapAndSettle(tester, find.bySemanticsLabel('Wink'));
    await tapAndSettle(tester, find.bySemanticsLabel('Back'));
    expect(find.byType(AvatarStudio), findsNothing);
    await tapAndSettle(tester, find.bySemanticsLabel('Edit avatar'));
    // The studio opens on the form's face again.
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Wink'))
          .getSemanticsData()
          .flagsCollection
          .isChecked,
      CheckedState.isFalse,
    );
    await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(find.byType(AvatarStudio), findsNothing);
    expect(find.byType(CreateAgentForm), findsOneWidget);
  });

  testWidgets('a downward drag closes the clean sheet', (tester) async {
    await _open(tester);
    await _dragDown(tester);
    expect(find.byType(CreateAgentForm), findsNothing);
  });

  testWidgets('with a name the drag no longer closes it and ✕ asks', (
    tester,
  ) async {
    await _open(tester);
    await tester.enterText(_nameField(), 'Scout');
    await tester.pump();
    FocusManager.instance.primaryFocus?.unfocus();
    await tester.pumpAndSettle();
    await _dragDown(tester);
    expect(find.byType(CreateAgentForm), findsOneWidget);
    expect(find.text('Scout'), findsOneWidget);
    expect(find.text('Discard the changes?'), findsNothing);
    await tapAndSettle(tester, find.bySemanticsLabel('Close'));
    expect(find.text('Discard the changes?'), findsOneWidget);
    await tapAndSettle(tester, find.text('Keep editing'));
    expect(find.byType(CreateAgentForm), findsOneWidget);
    await tapAndSettle(tester, find.bySemanticsLabel('Close'));
    await tapAndSettle(tester, find.text('Discard'));
    expect(find.byType(CreateAgentForm), findsNothing);
  });

  testWidgets('the drag does not close the sheet over the studio page', (
    tester,
  ) async {
    await _open(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('Edit avatar'));
    await tapAndSettle(tester, find.bySemanticsLabel('Wink'));
    await _dragDown(tester, from: find.text('Edit avatar'));
    expect(find.byType(AvatarStudio), findsOneWidget);
    // ✓ keeps the draft, and the form is back with the drag still off (the face changed).
    await tapAndSettle(tester, find.bySemanticsLabel('Save'));
    expect(find.byType(AvatarStudio), findsNothing);
    await _dragDown(tester);
    expect(find.byType(CreateAgentForm), findsOneWidget);
  });

  testWidgets('layout: a 112 dp avatar over a 54 dp stadium field; the edit '
      'badge sits on its bottom-end edge (left in Arabic)', (tester) async {
    final handle = tester.ensureSemantics();
    await _open(tester, locale: 'ar');
    final avatar = tester.getRect(
      find.descendant(
        of: find.byType(CreateAgentForm),
        matching: find.byType(LonoraAvatar),
      ),
    );
    expect(avatar.size, const Size.square(CreateAgentLayout.avatar));
    final screen = tester.getSize(find.byType(MaterialApp));
    expect(avatar.center.dx, screen.width / 2);
    final field = tester.getRect(find.byType(StadiumField));
    expect(field.height, 54);
    expect(field.left, 16);
    expect(field.right, screen.width - 16);
    expect(field.top - avatar.bottom, CreateAgentLayout.avatarToField);
    final badge = tester.getRect(find.bySemanticsLabel('تعديل الأفاتار'));
    expect(badge.size, const Size.square(LnSize.minTouch));
    expect(badge.center.dx, lessThan(avatar.center.dx));
    expect(badge.center.dy, greaterThan(avatar.center.dy));
    expect(
      tester.widget<TextField>(_nameField()).decoration!.hintText,
      'اسم الوكيل',
    );
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    handle.dispose();
  });

  testWidgets('the studio: a five-column face grid, the selected face on its '
      'tile; the colour popover holds the eleven shells', (tester) async {
    final handle = tester.ensureSemantics();
    await _open(tester);
    await tapAndSettle(tester, find.bySemanticsLabel('Edit avatar'));
    final faces = find.descendant(
      of: find.byType(AvatarStudio),
      matching: find.byWidgetPredicate(
        (w) => w is LonoraAvatar && w.size == AvatarStudio.faceSize,
      ),
    );
    expect(faces, findsNWidgets(avatarFaces.length));
    final first = tester.getRect(faces.at(0));
    final second = tester.getRect(faces.at(1));
    final sixth = tester.getRect(faces.at(5));
    final screen = tester.getSize(find.byType(MaterialApp));
    expect(
      second.center.dx - first.center.dx,
      moreOrLessEquals((screen.width - 32) / 5),
    );
    expect(sixth.center.dy - first.center.dy, AvatarStudio.faceRowPitch);
    expect(
      tester
          .getSemantics(find.bySemanticsLabel('Signals'))
          .getSemanticsData()
          .flagsCollection
          .isChecked,
      CheckedState.isTrue,
    );
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
    await tapAndSettle(tester, find.bySemanticsLabel('Choose a color'));
    // The ring (the popover names itself the same).
    final ring = tester.getRect(find.bySemanticsLabel('Choose a color').first);
    final swatches = find.bySemanticsLabel(RegExp('^Color #'));
    expect(swatches, findsNWidgets(avatarPalette.length));
    // Under the ring, centred on it.
    final card = tester
        .getRect(swatches.first)
        .expandToInclude(tester.getRect(swatches.last));
    expect(card.top, greaterThan(ring.bottom));
    expect(
      tester.getRect(swatches.at(2)).right,
      moreOrLessEquals(ring.center.dx, epsilon: 25),
    );
    await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
    handle.dispose();
  });

  for (final v in [goldenVariants[1], goldenVariants[2]]) {
    testWidgets('golden create agent ${v.name}', (tester) async {
      await withRealShadows(() async {
        await _open(tester, locale: v.locale, brightness: v.brightness);
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/create_agent_${v.name}.png'),
        );
      });
    });

    testWidgets('golden avatar studio ${v.name}', (tester) async {
      await withRealShadows(() async {
        await _open(tester, locale: v.locale, brightness: v.brightness);
        await tapAndSettle(
          tester,
          find.bySemanticsLabel(
            v.locale == 'ar' ? 'تعديل الأفاتار' : 'Edit avatar',
          ),
        );
        await expectLater(
          find.byType(MaterialApp),
          matchesGoldenFile('goldens/avatar_studio_${v.name}.png'),
        );
      });
    });
  }

  testWidgets('golden avatar colours dark_ar', (tester) async {
    await withRealShadows(() async {
      await _open(tester, locale: 'ar', brightness: Brightness.dark);
      await tapAndSettle(tester, find.bySemanticsLabel('تعديل الأفاتار'));
      await tapAndSettle(tester, find.bySemanticsLabel('اختيار اللون'));
      await expectLater(
        find.byType(MaterialApp),
        matchesGoldenFile('goldens/avatar_colors_dark_ar.png'),
      );
    });
  });
}
