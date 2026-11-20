import { ICON_PATHS, type IconName } from "./paths";

export type IconProps = Omit<React.ComponentProps<"svg">, "name"> & { name: IconName };

/** Drawn for Arabic (back points right, the row chevron left): English mirrors them. */
const MIRRORED: ReadonlySet<IconName> = new Set(["back", "chev"]);

/** The reference's `I(name)`: a 24-unit stroke icon in `currentColor`; its box is sized by CSS. */
function Icon({ name, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      data-mirror={MIRRORED.has(name) ? "" : undefined}
      {...props}
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

export { Icon };
