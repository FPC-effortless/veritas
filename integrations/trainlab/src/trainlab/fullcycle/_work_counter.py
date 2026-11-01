"""Global supported-operator FLOPs without retaining module-attribution hooks."""

from torch.utils.flop_counter import FlopCounterMode
from torch.utils.module_tracker import ModuleTracker


class _GlobalScope(ModuleTracker):
    """Keep the documented Global scope; register no module/autograd hooks."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class GlobalFlopCounter(FlopCounterMode):
    """Retain PyTorch's operator registry and Global total, without attribution."""

    def __init__(self):
        super().__init__(display=False)
        # TrainLab consumes only Global totals. Hierarchy attribution otherwise
        # retains backward-hook handles throughout a long checkpointed stage.
        self.mod_tracker = _GlobalScope()
