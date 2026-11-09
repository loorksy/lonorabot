import { AgentAvatar } from "./agent-avatar";

/** A group's avatar is its members: three faces at most, the lead first, clustered inside the
 * slot it is given (the reference's `groupAvatar`, drawn with Lonora's avatar). */
export function GroupAvatar({
  members,
}: {
  members: { id: string; name: string; color: string }[];
}) {
  const shown = members.slice(0, 3);
  return (
    <span className={`lonora-group-avatar n${shown.length}`} aria-hidden="true">
      {shown.map((member, index) => (
        <span key={member.id} className={`lonora-group-member m${index + 1}`}>
          <AgentAvatar identity={member.id} name={member.name} color={member.color} />
        </span>
      ))}
    </span>
  );
}
