// Modified for Lonora from Rakazo lonora-rakazo-reference; Apache-2.0.
import { cn } from "@lonora/ui-web/lib/utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-muted", className)}
      {...props}
    />
  );
}

export { Skeleton };
