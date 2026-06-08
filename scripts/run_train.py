import sys
from pathlib import Path

import hydra
from omegaconf import DictConfig

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from train import train


@hydra.main(version_base=None, config_path="../config", config_name="default")
def main(cfg: DictConfig):
    train(cfg)


if __name__ == "__main__":
    main()
