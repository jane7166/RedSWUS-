import os
import cv2
import torch
import numpy as np
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
from models import db, FirstPreprocessingResult
from detectron2.engine import DefaultPredictor
from detectron2.config import get_cfg
from model_detection import setup_cfg, get_parser, VisualizationDemo, save_result_to_txt


class DetectronHandler:
    def __init__(self):
        # Detectron2 설정 및 모델 초기화
        self.cfg = get_cfg()
        self.cfg.merge_from_file("./config.yaml")
        self.cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.5
        self.cfg.MODEL.WEIGHTS = "./pt/model_0000599.pth"
        self.cfg.MODEL.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        self.predictor = DefaultPredictor(self.cfg)

    def handle_std_predict(self, first_result_code):
        """
        STD 예측을 처리하는 메서드.
        """
        first_result = FirstPreprocessingResult.query.filter_by(first_result_code=first_result_code).first()
        if not first_result:
            return {"error": "First preprocessing result not found."}, 404

        file_path = first_result.first_result_path
        if not os.path.exists(file_path):
            return {"error": "File not found at the specified path."}, 404

        try:
            img = cv2.imread(file_path)
            if img is None:
                return {"error": "Failed to load the image for prediction."}, 400

            outputs = self.predictor(img)
            instances = outputs["instances"].to("cpu")
            boxes = instances.pred_boxes.tensor.numpy()
            classes = instances.pred_classes.numpy()
            scores = instances.scores.numpy()

            std_result_code = hash(file_path)  # 임시로 결과 코드 생성
            return {
                "std_result_code": std_result_code,
                "boxes": boxes.tolist(),
                "classes": classes.tolist(),
                "scores": scores.tolist()
            }, 200

        except Exception as e:
            return {"error": f"Prediction failed: {str(e)}"}, 500


# DetectronHandler 인스턴스 생성
detectron_handler = DetectronHandler()


def run_all_handlers(first_result_code):
    """
    STD 예측 및 후속 처리를 실행하는 함수.
    """
    # STD Predict 실행
    std_response = detectron_handler.handle_std_predict(first_result_code)
    if std_response[1] != 200:
        return std_response

    # STD Predict 결과 처리
    std_result_code = std_response[0].get("std_result_code")

    return {
        "status": "success",
        "std_result_code": std_result_code,
        "std_response": std_response[0],
    }, 200

__all__ = ["run_all_handlers"]
