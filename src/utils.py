import torch
import torch.nn as nn


def maybe_resume(model: nn.Module, resume_path: str | None, device: torch.device) -> bool:
    """체크포인트(.pt)에서 모델 가중치 로드. resume_path 가 비어 있으면 아무것도 안 함"""
    if not resume_path:
        return False
    state = torch.load(resume_path, map_location=device, weights_only=True)
    model.load_state_dict(state["model"])
    print(f"[resume] loaded weights ← {resume_path}")
    return True


def collate_point_cloud(point_clouds: torch.Tensor, device: torch.device):
    """PointNet Padding 함수"""
    max_num = max(pc.shape[0] for pc in point_clouds) if point_clouds else 0

    if max_num == 0:
        return torch.zeros(len(point_clouds), 0, point_clouds[0].shape[-1], device=device)
    
    feature_dim = point_clouds[0].shape[-1]
    output = torch.zeros(len(point_clouds), max_num, feature_dim, device=device)

    for i, pc in enumerate(point_clouds):
        if pc.shape[0] > 0:
            output[i, :pc.shape[0]] = pc.to(device)
    
    return output