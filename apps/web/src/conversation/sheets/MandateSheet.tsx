import { t } from "@lingui/core/macro";
import type { PermissionState } from "@lonora/contracts";
import { useCallback } from "react";
import { AgentPermissions } from "../../components/permissions/AgentPermissions";
import type { Agent } from "../../lib/api";
import { useSheets } from "../../shell/sheets/SheetHost";

/* «التفويض» (reference OA_R.grant_authority): opened from the ladder's «تنفيذ مفوَّض» and from
   «تفاصيل التفويض». The draft, the passkey signature and the activation go through the server's
   account-authority routes only; nothing becomes active without the owner's signature. */
export function useMandateSheet() {
  const sheets = useSheets();
  return useCallback(
    (agent: Agent, _permission: PermissionState | null, details = false) => {
      const title = details ? t`Mandate details` : t`Delegated execution`;
      sheets.open({
        id: "mandate",
        bar: true,
        title,
        label: title,
        body: (
          <div className="legacy-surface">
            <AgentPermissions key={agent.id} agent={agent} threadId="" surface="settings" />
          </div>
        ),
      });
    },
    [sheets],
  );
}
