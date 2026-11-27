// The model picker sheet of the models page: Lonora's listed models for one route, as a
// single-choice list, built from the sheet and choice tiles.
import 'package:flutter/widgets.dart';

import '../../../design/design.dart';
import '../../../l10n/l10n.dart';
import '../settings_common.dart';
import 'models_data.dart';

/// What the picker answered: a model, or «none» (the route is cleared).
typedef PickedModel = ({ModelSelection? selection});

/// Shows [options] with [current] checked; completes with the choice, or null when dismissed.
/// [allowNone] offers «Choose a model» first, which clears the route.
Future<PickedModel?> showModelPicker(
  BuildContext context, {
  required String title,
  required List<ModelDescriptor> options,
  required ModelSelection? current,
  bool allowNone = true,
}) => showLnSheet<PickedModel>(
  context,
  title: title,
  builder: (sheet) => ConstrainedBox(
    constraints: BoxConstraints(
      maxHeight: MediaQuery.sizeOf(sheet).height * 0.6,
    ),
    child: SingleChildScrollView(
      child: LnSection(
        padding: EdgeInsets.zero,
        children: [
          if (allowNone)
            ChoiceTile(
              title: context.t('md_chooseModel'),
              selected: current == null,
              onSelect: () => Navigator.of(sheet).pop((selection: null)),
            ),
          if (current != null && !options.any((m) => m.selection == current))
            ChoiceTile(
              title: ltr('${current.provider} · ${current.model}'),
              selected: true,
              onSelect: () {},
            ),
          for (final m in options)
            ChoiceTile(
              title: isolate(m.label),
              subtitle: m.verified ? null : context.t('md_unverified'),
              selected: m.selection == current,
              onSelect: () => Navigator.of(sheet).pop((selection: m.selection)),
            ),
        ],
      ),
    ),
  ),
);
