# Copyright 2022 The Nerfstudio Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Evaluation utils
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import torch
import yaml
from rich.console import Console

from nerfstudio.configs import base_config as cfg
from nerfstudio.pipelines.base_pipeline import Pipeline

console = Console(width=120)


def eval_load_checkpoint(config: cfg.TrainerConfig, pipeline: Pipeline) -> Path:
    ## TODO: ideally eventually want to get this to be the same as whatever is used to load train checkpoint too
    """Helper function to load checkpointed pipeline

    Args:
        config (DictConfig): Configuration of pipeline to load
        pipeline (Pipeline): Pipeline instance of which to load weights
    """
    assert config.load_dir is not None
    if config.load_step is None:
        console.print("Loading latest checkpoint from load_dir")
        # NOTE: this is specific to the checkpoint name format
        if not os.path.exists(config.load_dir):
            console.rule("Error", style="red")
            console.print(f"No checkpoint directory found at {config.load_dir}, ", justify="center")
            console.print(
                "Please make sure the checkpoint exists, they should be generated periodically during training",
                justify="center",
            )
            sys.exit(1)
        load_step = sorted(int(x[x.find("-") + 1 : x.find(".")]) for x in os.listdir(config.load_dir))[-1]
    else:
        load_step = config.load_step
    load_path = config.load_dir / f"step-{load_step:09d}.ckpt"
    assert load_path.exists(), f"Checkpoint {load_path} does not exist"
    loaded_state = torch.load(load_path, map_location="cpu")
    pipeline.load_pipeline(loaded_state["pipeline"])
    console.print(f":white_check_mark: Done loading checkpoint from {load_path}")
    return load_path


def eval_setup(
    config_path: Path, double_nerfacto_nerf_samples: bool = False, eval_num_rays_per_chunk: Optional[int] = None
) -> Tuple[cfg.Config, Pipeline, Path]:
    """Shared setup for loading a saved pipeline for evaluation.

    Args:
        config_path: Path to config YAML file.

    Returns:
        Loaded config, pipeline module, and corresponding checkpoint.
    """
    # load save config
    config = yaml.load(config_path.read_text(), Loader=yaml.Loader)
    assert isinstance(config, cfg.Config)

    if eval_num_rays_per_chunk:
        config.pipeline.model.eval_num_rays_per_chunk = eval_num_rays_per_chunk

    if config.method_name == "nerfacto" and double_nerfacto_nerf_samples:
        config.pipeline.model.num_nerf_samples_per_ray *= 2
        console.print(
            "[bold yellow]Warning: doubling the number of nerfacto nerf samples to "
            f"{config.pipeline.model.num_nerf_samples_per_ray} for improved quality."
        )
        console.print("[bold yellow]This logic is a hack and will be removed in the future.")

    # load checkpoints from wherever they were saved
    # TODO: expose the ability to choose an arbitrary checkpoint
    config.trainer.load_dir = config.get_checkpoint_dir()
    config.pipeline.datamanager.eval_image_indices = None

    # setup pipeline (which includes the DataManager)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline = config.pipeline.setup(device=device, test_mode=True)
    assert isinstance(pipeline, Pipeline)
    pipeline.eval()

    # load checkpointed information
    checkpoint_path = eval_load_checkpoint(config.trainer, pipeline)

    return config, pipeline, checkpoint_path