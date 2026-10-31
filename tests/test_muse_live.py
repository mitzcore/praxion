"""Live Meta API tests. Spend real credits; skipped when no key is available.

Run: uv run pytest -q -m live
"""
from __future__ import annotations

import pytest

from backend.agent.contracts import ExperimentProposal
from backend.agent.muse_client import MuseClient, load_api_key
from backend.agent.prompts import discovery_messages

pytestmark = pytest.mark.live

MINIMAL_VIEW = {
    "plant": {"description": "A water reservoir. Input u in [0,1] is pump duty and raises the level; "
                             "the reservoir drains on its own. Output y in [0,1] is a noisy level reading.",
              "u_range": [0.0, 1.0], "y_range": [0.0, 1.0]},
    "objective": {"target": 0.6, "band": [0.55, 0.65]},
    "constraints": {"soft_high_limit": 0.85, "hard_cutoff": 0.90, "max_single_experiment_s": 20.0,
                    "experiments_remaining": 12, "candidates_remaining": 5},
    "current_observation": {"t": 0.0, "y": 0.30},
    "experiments": [],
    "ledger": [],
    "candidates": [],
}


@pytest.mark.skipif(load_api_key() is None, reason="no MODEL_API_KEY / ~/meta.key")
@pytest.mark.parametrize("model", ["muse-spark-1.3", "muse-wonder-1.0"])
def test_first_proposal_is_schema_valid_and_bounded(model: str) -> None:
    client = MuseClient(model=model, fallback_model=model, max_attempts=2)
    proposal, rec = client.structured("exploring", discovery_messages(MINIMAL_VIEW), ExperimentProposal)
    assert rec.ok and rec.prompt_tokens > 0 and rec.cost_usd > 0
    assert 0.0 <= proposal.command_u <= 1.0
    assert 0.0 < proposal.duration_s <= 20.0
    assert proposal.hypotheses, "ledger must not be empty"
    # With zero experiments, readiness must be false under prompt v1.0.
    assert proposal.ready_to_generate is False, proposal.readiness_justification
    print(f"\n[{model}] {rec.latency_s:.1f}s reasoning={rec.reasoning_tokens} cost=${rec.cost_usd:.4f} "
          f"u={proposal.command_u} dur={proposal.duration_s}\n  note: {proposal.operator_note}")
