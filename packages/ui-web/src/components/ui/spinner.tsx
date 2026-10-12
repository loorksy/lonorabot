import { t } from "@lingui/core/macro";
// Modified for Lonora from Rakazo lonora-rakazo-reference; Apache-2.0.
import { cn } from "@lonora/ui-web/lib/utils";
import { Loader2Icon } from "lucide-react";

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <Loader2Icon
      data-slot="spinner"
      role="status"
      aria-label={t`Loading`}
      className={cn("size-4 animate-spin", className)}
      {...props}
    />
  );
}

export { Spinner };
