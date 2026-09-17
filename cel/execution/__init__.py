"""Multi-leg initiate / hedge / timeout. Named 'execution' so it does not shadow Python's exec."""

from cel.execution.algo import AlgoConfig, run_algo

__all__ = ["AlgoConfig", "run_algo"]
