"""
센서 데이터 검사용 스크립트 (학습 X, 관측만 덤프).

용도: PointNet(BufferSensor)에 실제로 어떤 값이 찍히는지 + 벡터 관측 7-dim을
사람이 읽기 쉽게 출력. 머리 yaw 를 천천히 돌리며(scan) 시야에 모기가 들어오면
그 6-dim 값을 디코딩해 보여준다.

실행:
    1) python scripts/inspect_obs.py   (포트 5004 listening)
    2) Unity 에디터에서 Play
    3) 터미널에서 모기 감지 시 데이터가 찍힘. Ctrl+C 로 종료.

옵션:
    --steps N      최대 스텝 수 (기본 1000)
    --scan S       매 스텝 머리 yaw 행동값 [-1,1] (기본 0.5, 0=고정)
    --raw          정규화 해제 안 하고 원시값 그대로도 함께 출력
    --port P       Unity 통신 포트 (기본 5004)
"""
import argparse
import numpy as np

from mlagents_envs.environment import UnityEnvironment
from mlagents_envs.base_env import ActionTuple

# MosquitoSensor.cs 와 동일 (위치 정규화 기준)
MAX_DETECT_RANGE = 3.0
# ChameleonAgent.cs 의 벡터 관측 정규화 기준
POS_NORM = 3.5
PITCH_NORM = 60.0
YAW_NORM = 180.0


def split_obs(obs_list):
    """decision_steps.obs → (vec [B,vec], pt [B,N,6] or None). 벡터 rank-2, 모기 rank-3."""
    vec = next(o for o in obs_list if o.ndim == 2)
    pt_cands = [o for o in obs_list if o.ndim == 3]
    return vec, (pt_cands[0] if pt_cands else None)


def print_vector_obs(vec_row):
    """7-dim 벡터 관측을 라벨과 함께 출력 (정규화값 → 실제값 역산)."""
    if len(vec_row) < 7:
        print(f"  [vec] (예상 7-dim 아님, len={len(vec_row)}) raw={np.round(vec_row,3)}")
        return
    px, pz, vx, vz, pitch, yaw, remain = vec_row[:7]
    print("  [벡터 관측 7-dim]")
    print(f"    위치(절대)   x={px*POS_NORM:+.2f}m  z={pz*POS_NORM:+.2f}m      (정규화 {px:+.3f}, {pz:+.3f})")
    print(f"    속도(절대)   vx={vx:+.3f}     vz={vz:+.3f}")
    print(f"    머리 각도    pitch={pitch*PITCH_NORM:+.1f}°  yaw={yaw*YAW_NORM:+.1f}°  (정규화 {pitch:+.3f}, {yaw:+.3f})")
    print(f"    남은 모기 수 ≈ {remain*10:.0f}   (정규화 {remain:+.3f})")


def print_point_cloud(pt_rows, show_raw):
    """BufferSensor [N,6] 에서 패딩(전부 0) 제외하고 모기별 6-dim 디코딩 출력."""
    nonzero = pt_rows[np.abs(pt_rows).sum(axis=-1) > 0]
    n = len(nonzero)
    print(f"  [PointNet/BufferSensor] 슬롯 {pt_rows.shape[0]}개 중 감지된 모기 = {n}마리")
    if n == 0:
        print("    (시야 내 모기 없음 — 전부 0 패딩)")
        return
    for i, r in enumerate(nonzero):
        rx, ry, rz, vlx, vly, vlz = r[:6]
        dist = np.sqrt((rx*MAX_DETECT_RANGE)**2 + (ry*MAX_DETECT_RANGE)**2 + (rz*MAX_DETECT_RANGE)**2)
        print(f"    모기 #{i}: 머리기준 상대위치 "
              f"x={rx*MAX_DETECT_RANGE:+.2f} y={ry*MAX_DETECT_RANGE:+.2f} z={rz*MAX_DETECT_RANGE:+.2f} m "
              f"(거리 {dist:.2f}m) | 상대속도 ({vlx:+.2f},{vly:+.2f},{vlz:+.2f})")
        if show_raw:
            print(f"             raw 6-dim = {np.round(r[:6], 4).tolist()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=1000)
    ap.add_argument("--scan", type=float, default=0.5, help="매 스텝 머리 yaw 행동값 [-1,1]")
    ap.add_argument("--raw", action="store_true")
    ap.add_argument("--port", type=int, default=5004)
    args = ap.parse_args()

    print(f"[inspect] Unity 연결 대기 (port {args.port}). Unity 에디터에서 Play 하세요...")
    env = UnityEnvironment(file_name=None, base_port=args.port, timeout_wait=120)
    env.reset()
    behavior_name = list(env.behavior_specs.keys())[0]
    spec = env.behavior_specs[behavior_name]

    print(f"\n[behavior] {behavior_name}")
    for i, os_ in enumerate(spec.observation_specs):
        print(f"  obs[{i}] name={os_.name!r}  shape={tuple(os_.shape)}")
    print(f"  continuous_size={spec.action_spec.continuous_size}  "
          f"discrete_branches={tuple(spec.action_spec.discrete_branches)}\n")

    cont_dim = spec.action_spec.continuous_size
    n_disc = len(spec.action_spec.discrete_branches)

    detected_steps = 0
    for step in range(args.steps):
        dec, term = env.get_steps(behavior_name)
        if len(dec) == 0:
            env.step()
            continue

        vec, pt = split_obs(dec.obs)

        # 모기 감지된 스텝만 자세히 출력 (노이즈 방지). 50스텝마다 벡터도 1회.
        has_mosquito = pt is not None and (np.abs(pt[0]).sum(axis=-1) > 0).any()
        if has_mosquito or step % 50 == 0:
            print(f"================ step {step} ================")
            print_vector_obs(vec[0])
            if pt is not None:
                print_point_cloud(pt[0], args.raw)
            else:
                print("  [PointNet] BufferSensor 관측 없음 (spec 확인 필요)")
            if has_mosquito:
                detected_steps += 1

        # 머리 yaw 만 돌려 scan (index 2), 나머지 0, 공격 0
        cont = np.zeros((len(dec), cont_dim), dtype=np.float32)
        if cont_dim > 2:
            cont[:, 2] = args.scan
        disc = np.zeros((len(dec), n_disc), dtype=np.int32)
        env.set_actions(behavior_name, ActionTuple(continuous=cont, discrete=disc))
        env.step()

    print(f"\n[inspect] 종료. 모기 감지된 출력 스텝 수 = {detected_steps}")
    env.close()


if __name__ == "__main__":
    main()
