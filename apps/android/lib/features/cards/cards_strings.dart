import '../../l10n/l10n.dart';

final Expando<bool> _registered = Expando('cards-strings');

/// Android-only labels of the conversation cards (everything else is Lonora's own text:
/// the app catalog and the @lonora/core ports). Registered on the cards' first build; the
/// lead may call `registerCardsStrings(L10n.instance)` at startup instead.
void registerCardsStrings(L10n l10n) {
  if (_registered[l10n] == true) return;
  _registered[l10n] = true;
  l10n.register(cardsStrings);
}

const Map<String, List<String>> cardsStrings = {
  // The consumed approval stadium (a disabled past-tense button) after an approval.
  'cards_approved': ['تمت الموافقة', 'Approved'],
};
