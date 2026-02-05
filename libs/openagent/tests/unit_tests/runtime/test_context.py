"""Tests for context module: types, CompactionController, CompactionPhase."""

# ruff: noqa: PLR2004

import pytest

from openagent.runtime.context import (
    DEFAULT_COMPACTION_THRESHOLD,
    Append,
    CompactionController,
    CompactionPhase,
    Inject,
    Overwrite,
)

# Test prompt (canonical source is compaction/request.md in the library)
TEST_PROMPT = "Summarize what you have done."

# --- Type tests ---


class TestCompactionPhase:
    """Tests for CompactionPhase enum."""

    def test_phases_exist(self) -> None:
        assert hasattr(CompactionPhase, "NONE")
        assert hasattr(CompactionPhase, "REQUESTING")
        assert hasattr(CompactionPhase, "APPLYING")

    def test_phases_are_distinct(self) -> None:
        phases = [CompactionPhase.NONE, CompactionPhase.REQUESTING, CompactionPhase.APPLYING]
        assert len(set(phases)) == 3

    def test_phase_string_values(self) -> None:
        assert CompactionPhase.NONE.value == "none"
        assert CompactionPhase.REQUESTING.value == "requesting"
        assert CompactionPhase.APPLYING.value == "applying"

    def test_phase_is_str_enum(self) -> None:
        assert isinstance(CompactionPhase.NONE, str)
        assert CompactionPhase.NONE == "none"  # type: ignore[comparison-overlap]

    def test_phase_from_string(self) -> None:
        assert CompactionPhase("none") == CompactionPhase.NONE
        assert CompactionPhase("requesting") == CompactionPhase.REQUESTING
        assert CompactionPhase("applying") == CompactionPhase.APPLYING


class TestOverwrite:
    """Tests for Overwrite dataclass."""

    def test_creation(self) -> None:
        ow = Overwrite()
        assert isinstance(ow, Overwrite)

    def test_frozen(self) -> None:
        ow = Overwrite()
        with pytest.raises(AttributeError):
            ow.x = 1  # type: ignore[attr-defined]

    def test_equality(self) -> None:
        assert Overwrite() == Overwrite()


class TestAppend:
    """Tests for Append dataclass."""

    def test_creation_default_role(self) -> None:
        a = Append(content="hello")
        assert a.content == "hello"
        assert a.role == "user"

    def test_creation_custom_role(self) -> None:
        a = Append(content="hello", role="assistant")
        assert a.role == "assistant"

    def test_frozen(self) -> None:
        a = Append(content="hello")
        with pytest.raises(AttributeError):
            a.content = "world"  # type: ignore[misc]

    def test_equality(self) -> None:
        assert Append(content="hello") == Append(content="hello")
        assert Append(content="hello") != Append(content="world")


class TestInject:
    """Tests for Inject dataclass."""

    def test_creation_default_position(self) -> None:
        i = Inject(content="reminder")
        assert i.content == "reminder"
        assert i.position == "prepend"

    def test_creation_append_position(self) -> None:
        i = Inject(content="reminder", position="append")
        assert i.position == "append"

    def test_frozen(self) -> None:
        i = Inject(content="reminder")
        with pytest.raises(AttributeError):
            i.content = "new"  # type: ignore[misc]

    def test_equality(self) -> None:
        assert Inject(content="a") == Inject(content="a")
        assert Inject(content="a", position="prepend") != Inject(content="a", position="append")


# --- CompactionController tests ---


class TestCompactionControllerInit:
    """Tests for CompactionController initialization."""

    def test_default_threshold(self) -> None:
        ctrl = CompactionController(TEST_PROMPT)
        assert ctrl.threshold == DEFAULT_COMPACTION_THRESHOLD

    def test_custom_threshold(self) -> None:
        ctrl = CompactionController(TEST_PROMPT, threshold=50_000)
        assert ctrl.threshold == 50_000

    def test_prompt_stored(self) -> None:
        ctrl = CompactionController(TEST_PROMPT)
        assert ctrl.compaction_prompt == TEST_PROMPT


class TestPreModelUpdate:
    """Tests for CompactionController.pre_model_update()."""

    def test_none_phase_returns_no_update(self) -> None:
        ctrl = CompactionController(TEST_PROMPT)
        update, phase = ctrl.pre_model_update(CompactionPhase.NONE)
        assert update is None
        assert phase == CompactionPhase.NONE

    def test_requesting_phase_returns_append(self) -> None:
        ctrl = CompactionController(TEST_PROMPT)
        update, phase = ctrl.pre_model_update(CompactionPhase.REQUESTING)
        assert isinstance(update, Append)
        assert update.content == TEST_PROMPT
        assert update.role == "user"
        assert phase == CompactionPhase.REQUESTING

    def test_requesting_phase_uses_custom_prompt(self) -> None:
        ctrl = CompactionController("Custom prompt.")
        update, _ = ctrl.pre_model_update(CompactionPhase.REQUESTING)
        assert isinstance(update, Append)
        assert update.content == "Custom prompt."

    def test_applying_phase_returns_overwrite(self) -> None:
        ctrl = CompactionController(TEST_PROMPT)
        update, phase = ctrl.pre_model_update(CompactionPhase.APPLYING)
        assert isinstance(update, Overwrite)
        assert phase == CompactionPhase.NONE


class TestPostModelTransition:
    """Tests for CompactionController.post_model_transition()."""

    def test_none_below_threshold_no_rerun(self) -> None:
        ctrl = CompactionController(TEST_PROMPT, threshold=100)
        should_rerun, phase = ctrl.post_model_transition(50, CompactionPhase.NONE)
        assert should_rerun is False
        assert phase == CompactionPhase.NONE

    def test_none_at_threshold_triggers_requesting(self) -> None:
        ctrl = CompactionController(TEST_PROMPT, threshold=100)
        should_rerun, phase = ctrl.post_model_transition(100, CompactionPhase.NONE)
        assert should_rerun is True
        assert phase == CompactionPhase.REQUESTING

    def test_none_above_threshold_triggers_requesting(self) -> None:
        ctrl = CompactionController(TEST_PROMPT, threshold=100)
        should_rerun, phase = ctrl.post_model_transition(200, CompactionPhase.NONE)
        assert should_rerun is True
        assert phase == CompactionPhase.REQUESTING

    def test_requesting_transitions_to_applying(self) -> None:
        ctrl = CompactionController(TEST_PROMPT, threshold=100)
        should_rerun, phase = ctrl.post_model_transition(0, CompactionPhase.REQUESTING)
        assert should_rerun is True
        assert phase == CompactionPhase.APPLYING

    def test_requesting_ignores_token_count(self) -> None:
        ctrl = CompactionController(TEST_PROMPT, threshold=100)
        # Token count doesn't matter in REQUESTING phase
        should_rerun1, phase1 = ctrl.post_model_transition(0, CompactionPhase.REQUESTING)
        should_rerun2, phase2 = ctrl.post_model_transition(999, CompactionPhase.REQUESTING)
        assert should_rerun1 == should_rerun2 is True
        assert phase1 == phase2 == CompactionPhase.APPLYING

    def test_applying_no_rerun(self) -> None:
        ctrl = CompactionController(TEST_PROMPT, threshold=100)
        should_rerun, phase = ctrl.post_model_transition(0, CompactionPhase.APPLYING)
        assert should_rerun is False
        assert phase == CompactionPhase.APPLYING


class TestFullCompactionProtocol:
    """Test the full 3-phase compaction protocol end-to-end."""

    def test_full_cycle(self) -> None:
        """Walk through NONE -> REQUESTING -> APPLYING -> NONE."""
        ctrl = CompactionController(TEST_PROMPT, threshold=100)
        phase = CompactionPhase.NONE

        # Step 1: after_model detects threshold exceeded
        should_rerun, phase = ctrl.post_model_transition(200, phase)
        assert should_rerun is True
        assert phase == CompactionPhase.REQUESTING

        # Step 2: before_model appends compaction prompt
        update, phase = ctrl.pre_model_update(phase)
        assert isinstance(update, Append)
        assert phase == CompactionPhase.REQUESTING

        # Step 3: after_model transitions to APPLYING
        should_rerun, phase = ctrl.post_model_transition(200, phase)
        assert should_rerun is True
        assert phase == CompactionPhase.APPLYING

        # Step 4: before_model signals overwrite
        update, phase = ctrl.pre_model_update(phase)
        assert isinstance(update, Overwrite)
        assert phase == CompactionPhase.NONE

        # Step 5: back to normal
        should_rerun, phase = ctrl.post_model_transition(50, phase)
        assert should_rerun is False
        assert phase == CompactionPhase.NONE
