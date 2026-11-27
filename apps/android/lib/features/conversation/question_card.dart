// The agent's question (`Run.input_requests[]`), drawn in place of the message that holds it,
// as apps/mobile/components/conversation-question.tsx: the question, one button per choice and
// the request's state. A choice is sent as an owner message with `input_answer`
// (`content == choice.label`, `reply_to` = the question's message), never queued offline.
// Composed from the action card: body text + stacked block buttons.
import 'package:flutter/widgets.dart';
import 'package:forui/forui.dart' show FIcons;

import '../../core/models/models.dart';
import '../../design/design.dart';
import '../../l10n/l10n.dart';

class QuestionCard extends StatelessWidget {
  const QuestionCard({
    super.key,
    required this.request,
    required this.onAnswer,
    this.answering,
  });

  final InputRequest request;

  /// The owner picked [choice]; the caller sends the answer.
  final ValueChanged<InputChoice> onAnswer;

  /// The choice whose answer is on its way (buttons wait meanwhile).
  final String? answering;

  @override
  Widget build(BuildContext context) {
    final ln = context.ln;
    final c = ln.colors;
    final l10n = context.l10n;
    final open = request.pending && answering == null;
    final status = l10n.t(
      request.pending
          ? 'questionPending'
          : request.status == 'answered'
          ? 'questionAnswered'
          : 'questionClosed',
    );
    return ActionCard(
      semanticLabel: request.question,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(request.question),
          const SizedBox(height: 6),
          Semantics(
            liveRegion: true,
            child: Text(
              status,
              style: ln.text.footnote.copyWith(color: c.fgMuted),
            ),
          ),
        ],
      ),
      actions: [
        for (final choice in request.choices)
          BlockButton(
            label: choice.label,
            icon: request.selectedChoiceId == choice.id ? FIcons.check : null,
            loading: answering == choice.id,
            variant: open
                ? BlockButtonVariant.secondary
                : BlockButtonVariant.done,
            onPressed: open ? () => onAnswer(choice) : null,
          ),
      ],
    );
  }
}
