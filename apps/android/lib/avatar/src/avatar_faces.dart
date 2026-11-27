// Face catalogue of the avatar studio: the sixteen ids of AVATAR_FACES
// (trading-avatar-motion.js:62-81) with the English labels found there and the Arabic
// labels of apps/mobile/lib/i18n.ts:17-32.
import 'package:flutter/widgets.dart';

import 'motion.dart' show resolveAvatarFace;

/// One selectable face. [id] is what `Agent.avatar` stores.
@immutable
class AvatarFace {
  const AvatarFace(this.id, {required this.en, required this.ar});

  final String id;
  final String en;
  final String ar;

  /// The label for [locale] (Arabic for `ar`, English otherwise).
  String label(Locale? locale) => locale?.languageCode == 'ar' ? ar : en;
}

/// All faces in studio order; `orb` (the four signal bars) first.
const List<AvatarFace> avatarFaces = [
  AvatarFace('orb', en: 'Signals', ar: 'الإشارات'),
  AvatarFace('face-smile', en: 'Smile', ar: 'مبتسم'),
  AvatarFace('face-thoughtful', en: 'Thoughtful', ar: 'متأمل'),
  AvatarFace('face-happy', en: 'Happy', ar: 'سعيد'),
  AvatarFace('face-wink', en: 'Wink', ar: 'غمزة'),
  AvatarFace('face-sleepy', en: 'Sleepy', ar: 'نعسان'),
  AvatarFace('face-surprised', en: 'Surprised', ar: 'متفاجئ'),
  AvatarFace('face-angry', en: 'Angry', ar: 'غاضب'),
  AvatarFace('face-playful', en: 'Playful', ar: 'مرح'),
  AvatarFace('face-excited', en: 'Excited', ar: 'متحمس'),
  AvatarFace('face-skeptical', en: 'Skeptical', ar: 'متسائل'),
  AvatarFace('face-dreamy', en: 'Dreamy', ar: 'حالم'),
  AvatarFace('face-focused', en: 'Focused', ar: 'مركز'),
  AvatarFace('face-worried', en: 'Worried', ar: 'قلق'),
  AvatarFace('face-laugh', en: 'Laugh', ar: 'ضاحك'),
  AvatarFace('face-determined', en: 'Determined', ar: 'حازم'),
];

/// The catalogue entry for a stored face id (unknown → `orb`).
AvatarFace avatarFaceFor(String? id) {
  final resolved = resolveAvatarFace(id);
  return avatarFaces.firstWhere((face) => face.id == resolved);
}

/// Arabic when the nearest [Localizations] locale is Arabic.
bool avatarIsArabic(BuildContext context) =>
    Localizations.maybeLocaleOf(context)?.languageCode == 'ar';
