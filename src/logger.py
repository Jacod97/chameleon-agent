import mlflow

class MLflowTracker:
    """학습 지표를 MLflow 로 기록"""
    def __init__(self, experiment_name: str = "chameleon-rl", run_name: str = None):
        mlflow.set_experiment(experiment_name)
        self._run = mlflow.start_run(run_name=run_name)

    def log_params(self, params: dict):
        # 하이퍼파라미터 등 1회성 기록
        mlflow.log_params(params)

    def log_metrics(self, metrics: dict, step: int):
        mlflow.log_metrics(metrics, step=step)

    def log_artifact(self, path: str):
        # 저장된 모델(.pt/.onnx) 등 파일 업로드
        mlflow.log_artifact(path)

    def close(self):
        mlflow.end_run()
