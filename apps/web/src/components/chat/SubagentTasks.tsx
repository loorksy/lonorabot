import { Trans } from "@lingui/react/macro";
import type { Run } from "../../lib/api";
import { WorkingIndicator } from "./WorkingIndicator";
export function SubagentTasks({runs}:{runs:Run[]}){const children=runs.filter(r=>r.parent_run_id);return children.length?<details><summary><Trans>Temporary delegated tasks</Trans> ({children.length})</summary>{children.map(r=><div className="row" key={r.id}><code>{r.id.slice(0,8)}</code><WorkingIndicator run={r}/></div>)}</details>:null;}
