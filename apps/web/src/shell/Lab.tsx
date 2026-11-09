import { useState } from "react";
import { usePermissionSheet } from "./PermissionSheet";
import { useShortcutsSheet } from "./ShortcutsSheet";
import { useToast } from "./Toast";

/* «مختبر الحالات»: development builds only (DEV_ROUTES). Opens every interface state so the
   chrome can be seen without waiting for the real condition. Never part of a production build. */
export function Lab({
  onMaintenance,
  onUpdateBar,
}: {
  onMaintenance: () => void;
  onUpdateBar: () => void;
}) {
  const toast = useToast();
  const permission = usePermissionSheet();
  const shortcuts = useShortcutsSheet();
  const [crash, setCrash] = useState(false);
  if (crash) throw new Error("lab crash");
  const rows: [string, () => void][] = [
    ["toast · success", () => toast("تم الحفظ", { type: "success" })],
    ["toast · error", () => toast("تعذّر الحفظ", { type: "error" })],
    ["toast · warn", () => toast("راجع الحقل المحدد قبل الحفظ", { type: "warn" })],
    ["toast · info", () => toast("هذه الصفحة متاحة في نسخة التطوير فقط", { type: "info" })],
    [
      "toast · action",
      () =>
        toast("أُرشفت المحادثة", {
          type: "success",
          action: { label: "تراجع", run: () => toast("تم التراجع") },
        }),
    ],
    ["update bar", onUpdateBar],
    ["maintenance", onMaintenance],
    ["permission · mic", () => permission("mic")],
    ["permission · camera", () => permission("camera")],
    ["shortcuts", shortcuts],
    ["render error", () => setCrash(true)],
  ];
  return (
    <div className="group">
      {rows.map(([label, run]) => (
        <button type="button" className="row" key={label} onClick={run} dir="ltr">
          <span className="body">
            <strong>{label}</strong>
          </span>
        </button>
      ))}
    </div>
  );
}
