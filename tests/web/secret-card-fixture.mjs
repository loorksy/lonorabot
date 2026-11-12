import { execFileSync } from "node:child_process";

// An agent's Secret card, raised through the same proposal path its tool uses.
export function seedSecretCard(data) {
  const script = `
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import uuid4
from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_db.agents import create_agent
from lonora_db.owner_actions import propose
from lonora_db.threads import conversation_thread
async def main():
    data=json.load(sys.stdin)
    f=await Fixture().open()
    try:
        async with f.runtime.db.sessions() as session, session.begin():
            agent=await create_agent(session,f.owner,AgentCreate(name=data['agent'],scope_mode='flexible'))
            thread=await conversation_thread(session,f.owner,agent.id)
            proposal=OwnerActionProposal(kind='secret',label=data['label'],secret_fields=data['fields'])
            card,_=await propose(session,f.owner,proposal,card_id=str(uuid4()),agent_id=agent.id,thread_id=thread.id,run_id=None)
            print(json.dumps({'agent':agent.id,'thread':thread.id,'card':card.id}))
    finally:
        await f.close(cleanup=False)
asyncio.run(main())
`;
  return JSON.parse(
    execFileSync(".venv/bin/python", ["-c", script], {
      input: JSON.stringify(data),
      encoding: "utf8",
    }),
  );
}
