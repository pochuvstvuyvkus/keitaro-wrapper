"""The GitHub Pages demo (app/static/demo.js) must count shares like the real backend."""

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.shares import ShareError, ShareSlot, rebalance

DEMO_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "demo.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_node(script: str, payload) -> object:
    code = f"const demo = require({json.dumps(str(DEMO_JS))});\n{script}"
    out = subprocess.run(
        [NODE, "-e", code], input=json.dumps(payload), capture_output=True, text=True, check=True
    )
    return json.loads(out.stdout)


def test_rebalance_matches_python_on_random_cases():
    rnd = random.Random(42)
    cases = []
    for _ in range(600):
        n = rnd.randint(1, 10)
        cases.append(
            [
                {
                    "share": rnd.randint(0, 40),
                    "active": rnd.random() > 0.2,
                    "pinned": rnd.random() < 0.25,
                }
                for _ in range(n)
            ]
        )
    js = run_node(
        """
        const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
        const out = cases.map((c) => { try { return demo.rebalance(c); } catch { return "error"; } });
        process.stdout.write(JSON.stringify(out));
        """,
        cases,
    )
    for case, got in zip(cases, js, strict=True):
        try:
            expected = rebalance([ShareSlot(**slot) for slot in case])
        except ShareError:
            expected = "error"
        assert got == expected, case


def test_demo_replays_reference_video():
    steps = run_node(
        """
        (async () => {
          const backend = demo.createBackend({ storage: null, countries: async () => [] });
          const call = (m, p, b) => backend.handle(m, p, b);
          const shares = (s) => Object.fromEntries(s.offers.filter((o) => o.state === "active").map((o) => [o.offer_id, o.share]));
          const base = "/api/streams/10012";
          const out = [];
          let c = await call("GET", "/api/campaigns/1001");
          out.push(shares(c.streams[0]));
          out.push(shares(await call("POST", base + "/offers", { offer_id: 104 })));
          await call("POST", base + "/push");
          out.push(shares(await call("POST", base + "/offers/102/remove")));
          await call("POST", base + "/push");
          out.push(shares(await call("POST", base + "/offers/102/restore")));
          await call("POST", base + "/push");
          backend.setKt(10012, [[104, 25], [102, 25]]);
          c = await call("POST", "/api/campaigns/1001/sync");
          out.push(c.streams[0].total);
          await call("POST", base + "/offers/102/pin", { pinned: true });
          const s = await call("POST", base + "/offers/101/restore");
          out.push(shares(s));
          out.push(s.offers.map((o) => o.offer_id));
          process.stdout.write(JSON.stringify(out));
        })();
        """,
        None,
    )
    assert steps == [
        {"101": 33, "102": 33, "103": 34},
        {"101": 25, "102": 25, "103": 25, "104": 25},
        {"101": 33, "103": 33, "104": 34},
        {"101": 25, "103": 25, "104": 25, "102": 25},
        50,
        {"104": 37, "102": 25, "101": 38},
        [101, 104, 102, 103],
    ]
