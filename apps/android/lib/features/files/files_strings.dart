import '../../l10n/l10n.dart';

/// Android-only labels of the files screens. Where the Web already words the same thing (apps/web
/// shell/domain/FilesPages.tsx and its ar catalog), its wording is reused; Lonora's existing keys
/// (artifacts, artifactSearch, emptyArtifacts, download, share, preview, unsupportedPreview,
/// nativeHtmlPreview, previewTruncated, noImage, fileMissing…) are used directly.
void registerFilesStrings([L10n? l10n]) {
  final target = l10n ?? L10n.instance;
  if (target.has('fl_images')) return;
  target.register(_filesStrings);
}

const Map<String, List<String>> _filesStrings = {
  'fl_images': ['الصور', 'Images'],
  'fl_documents': ['المستندات', 'Documents'],
  'fl_text': ['النصوص', 'Text'],
  'fl_data': ['البيانات', 'Data'],
  'fl_other': ['أخرى', 'Other'],
  'fl_thisChat': ['هذه المحادثة', 'This conversation'],
  'fl_openWith': ['فتح في تطبيق آخر', 'Open in another app'],
  'fl_noOpener': ['لا يوجد تطبيق يفتح هذا الملف', 'No app can open this file'],
  'fl_saved': ['حُفظ الملف', 'File saved'],
  'fl_add': ['إضافة ملف', 'Add a file'],
  'fl_upload': ['رفع ملف', 'Upload a file'],
  'fl_uploaded': ['رُفع الملف', 'File uploaded'],
  'fl_newText': ['ملف نصي جديد', 'New text file'],
  'fl_editText': ['تحرير الملف', 'Edit file'],
  'fl_saveFile': ['حفظ الملف', 'Save file'],
  'fl_fileName': ['اسم الملف', 'File name'],
  'fl_content': ['المحتوى', 'Content'],
  'fl_defaultName': ['ملاحظة.txt', 'note.txt'],
  'fl_tooLarge': [
    'اختر ملفًا أصغر من 600 كيلوبايت.',
    'Choose a file smaller than 600 KB.',
  ],
  'fl_deleteQ': ['هل تريد حذف هذا الملف؟', 'Delete this file?'],
  'fl_confirmDelete': ['تأكيد الحذف', 'Confirm deletion'],
  'fl_deleted': ['حُذف الملف', 'File deleted'],
  'fl_gone': ['لم يعد الملف موجودًا.', 'The file no longer exists.'],
  'fl_grid': ['عرض شبكي', 'Grid view'],
  'fl_list': ['عرض القائمة', 'List view'],
  'fl_firstRows': ['أول {0} صفًا', 'First {0} rows'],
  'fl_saveImage': ['حفظ الصورة', 'Save image'],
};
