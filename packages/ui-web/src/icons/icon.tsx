import { ICON_PATHS, type IconName } from "./paths";

export type IconProps = Omit<React.ComponentProps<"svg">, "name"> & { name: IconName };

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
      {...props}
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

export { Icon };
