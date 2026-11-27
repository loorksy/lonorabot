// «مجموعة جديدة» as a page (/groups/new, for deep links and «مجموعة من المحددين» links): the same
// form as the create-group sheet ([NewGroupForm]) on the sheet's page fill, under the status bar.
import 'package:flutter/widgets.dart';

import '../../design/design.dart';
import 'create_group_sheet.dart';

class NewGroupScreen extends StatelessWidget {
  const NewGroupScreen({super.key, required this.memberIds});
  final List<String> memberIds;

  @override
  Widget build(BuildContext context) => ColoredBox(
    color: context.ln.colors.sheetPage,
    child: SafeArea(bottom: false, child: NewGroupForm(memberIds: memberIds)),
  );
}
