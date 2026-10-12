import { GroupAvatar as Avatar } from "@lonora/ui-web";
export function GroupAvatar({ name }: { name: string }) {
  return <Avatar members={[{ id: name, name, color: "#7c83fd" }]} />;
}
