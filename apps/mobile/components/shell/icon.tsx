import Svg, { Path } from "react-native-svg";
import { ICON_PATHS, type IconName } from "./icon-paths";

export type { IconName } from "./icon-paths";

/** The reference's `I(name)`: a 24-unit stroke icon (1.7 wide, round caps). */
export function Icon({ name, size = 22, color }: { name: IconName; size?: number; color: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" accessible={false}>
      <Path
        d={ICON_PATHS[name]}
        stroke={color}
        strokeWidth={1.7}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );
}
