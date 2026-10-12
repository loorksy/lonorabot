import { AgentAvatar } from "./agent-avatar";
export function GroupAvatar({
  members,
}: {
  members: { id: string; name: string; color: string }[];
}) {
  return (
    <span className="inline-flex -space-x-2">
      {members.slice(0, 3).map((member) => (
        <AgentAvatar key={member.id} name={member.name} color={member.color} />
      ))}
    </span>
  );
}
