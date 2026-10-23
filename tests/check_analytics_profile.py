"""Actual reviewed dependency image, resource boundary and analytical output.

Requires an explicit full local image ID; never pulls or mutates broker state.
"""

import asyncio
import json
import sys
from pathlib import Path

from lonora_agent.workspace import AnalyticalContainer

SOURCE = """
import importlib.metadata as metadata
import json
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from PIL import Image
from pathlib import Path
values = pd.Series([1.,2.,3.,4.,5.])
assert values.rolling(3).mean().dropna().tolist() == [2.,3.,4.]
assert np.isclose(stats.linregress(np.arange(5),values).slope,1)
fig, ax = plt.subplots(figsize=(3,2))
ax.plot(values.to_numpy())
fig.savefig('analysis.png')
plt.close(fig)
with Image.open('analysis.png') as image:
    assert image.size == (300,200)
result = {'mean':float(values.mean()),'versions':{
    name:metadata.version(name) for name in
    ('numpy','pandas','scipy','matplotlib','Pillow')
}}
Path('result.json').write_text(json.dumps(result))
print('analytical profile complete')
"""


async def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Pass the administrator-reviewed full local analytics image ID")
    backend = AnalyticalContainer(sys.argv[1])
    result = await backend.execute(
        "python -I analysis.py", {"analysis.py": SOURCE.encode()}, deadline_seconds=45
    )
    assert result.exit_code == 0, result.stderr
    assert result.image == sys.argv[1]
    actual = json.loads(result.files["result.json"])
    assert actual["mean"] == 3
    requirements = (
        await asyncio.to_thread(Path("infra/analysis/analytics.requirements.lock").read_text)
    ).splitlines()
    locked = {
        line.split("==")[0].casefold(): line.split("==")[1].split()[0]
        for line in requirements
        if "==" in line
    }
    assert all(locked[name.casefold()] == version for name, version in actual["versions"].items())
    assert result.files["analysis.png"].startswith(b"\x89PNG\r\n\x1a\n")
    failure = await backend.execute(
        "python -I -c 'import lonora_broker_credentials'", deadline_seconds=10
    )
    assert failure.exit_code != 0 and "ModuleNotFoundError" in failure.stderr
    no_install = await backend.execute(
        "python -m pip install --no-index lonora_nonexistent_dependency", deadline_seconds=10
    )
    assert no_install.exit_code != 0
    print(
        "PASS: actual locked analytical imports, numerical/rolling/statistical output, "
        "rendered raster, immutable image provenance and unsupported-dependency failures"
    )


if __name__ == "__main__":
    asyncio.run(main())
