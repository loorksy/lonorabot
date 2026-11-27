/// Reading direction and bidi isolation, as the Expo app and Web do it.
library;

import 'package:flutter/widgets.dart' show TextDirection;

import 'core/text.dart';

// packages/core/src/plain-line.ts:8-15: right-to-left letters (Hebrew, Arabic, Syriac, Thaana,
// N'Ko and their presentation forms) without the Arabic-Indic digits and the Arabic number
// signs and punctuation, which take the surrounding direction; Latin, Greek and Cyrillic.
final RegExp _rtl = RegExp(
  r'[\u0590-\u05ff\u0610-\u061a\u0620-\u065f\u066e-\u06d3\u06d5-\u06ef\u06fa-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]',
);
final RegExp _ltr = RegExp(
  r'[A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u024f\u0370-\u03ff\u0400-\u04ff]',
);
// Embedded direction controls would end an isolate early and reorder the rest of the line.
final RegExp _controls = RegExp(r'[\u202a-\u202e\u2066-\u2069]');

/// Whether [text] reads right to left: it has an Arabic (or other RTL) letter
/// (packages/core/src/plain-line.ts:25-33).
bool isRtlText(String text) => _rtl.hasMatch(text);

/// rtl when the text has a right-to-left letter, ltr when its letters are all Latin, Greek or
/// Cyrillic, null when it has none (numbers, symbols: it takes its surroundings)
/// (packages/core/src/plain-line.ts:25-33 `textDirection`).
TextDirection? readingDirection(String text) {
  if (_rtl.hasMatch(text)) return TextDirection.rtl;
  return _ltr.hasMatch(text) ? TextDirection.ltr : null;
}

/// The direction text written by an agent or person reads in, else [fallback] (the
/// interface's direction) (apps/mobile/lib/text-direction.ts:5-12).
TextDirection textDirectionFor(String text, TextDirection fallback) =>
    readingDirection(text) ?? fallback;

/// Keeps a ticker, number, name or time in its own direction inside the surrounding text:
/// FSI … PDI (U+2068/U+2069), the value's own direction controls dropped first
/// (packages/core/src/trading-readiness.ts:17-22).
String isolate(String value) =>
    '\u2068${value.replaceAll(_controls, '')}\u2069';

/// Forces a URL, email, server address, code, command line or token to read left to right
/// inside Arabic text: LRI … PDI (U+2066/U+2069), as apps/mobile/app/(settings)/running.tsx:34-35
/// isolates a command line. Embedded controls are dropped, as [isolate] does.
String ltr(String value) => '\u2066${value.replaceAll(_controls, '')}\u2069';

/// The list separator of the owner's language: the Arabic comma only in Arabic
/// (packages/core/src/trading-readiness.ts:24-27).
String listSeparator(String locale) => language(locale) == 'ar' ? '، ' : ', ';

/// The « · » between the parts of a metadata line, with a no-break space before the dot so a
/// wrapped line never starts with it (Android; the TS joins with a plain ' · ').
const String dotSeparator = '\u00a0· ';
