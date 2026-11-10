// Per owner decision Q10 the notification permission flow stays hidden until a push channel exists
// (Wave 3). This is its place: nothing asks for the permission, nothing in the UI offers it. When the
// channel lands, `notificationPermissionFlow` returns the sheet to show and the shell mounts it here.
export const notificationPermissionFlow: null = null;
