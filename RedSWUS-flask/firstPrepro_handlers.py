# firstPrepro_handlers.py
import os
import cv2
from flask import request, jsonify
from models import db, FirstPreprocessingResult, YoloResult

# 1차 전처리 함수
def preprocess_image(image):
    # 1단계: Gray Scale 변화, CLAHE, 조명 보정
    gray_1 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe_1 = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    clahe_img_1 = clahe_1.apply(gray_1)
    gaussian_blur_1 = cv2.GaussianBlur(clahe_img_1, (0, 0), sigmaX=30, sigmaY=30)
    light_corrected_1 = cv2.addWeighted(clahe_img_1, 1.5, gaussian_blur_1, -0.5, 0)

    # 2단계: 가우시안 블러 적용
    blurred_1 = cv2.GaussianBlur(light_corrected_1, (5, 5), 0)

    # 3단계: Gray Scale 변화, CLAHE, 조명 보정, 가우시안 블러
    gray_2 = cv2.cvtColor(cv2.merge([blurred_1] * 3), cv2.COLOR_BGR2GRAY)
    clahe_2 = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    clahe_img_2 = clahe_2.apply(gray_2)
    gaussian_blur_2 = cv2.GaussianBlur(clahe_img_2, (3, 3), 0)
    sharpened = cv2.addWeighted(clahe_img_2, 1.5, gaussian_blur_2, -0.5, 0)

    return sharpened

# FirstPrepro 핸들러 클래스
class FirstPreproApp:
    def __init__(self, output_folder):
        self.output_folder = output_folder
        os.makedirs(self.output_folder, exist_ok=True)

    def process_first_prepro(self, yolo_result_code):
        # YOLO 결과 코드로 이미지 찾기
        yolo_result = YoloResult.query.filter_by(yolo_result_code=yolo_result_code).first()
        if not yolo_result:
            return {"status": "error", "message": f"YOLO result with ID {yolo_result_code} not found."}, 404

        # YOLO 결과 이미지 경로 확인
        image_path = yolo_result.yolo_result_path
        if not os.path.exists(image_path):
            return {"status": "error", "message": f"File not found at {image_path}."}, 404

        # 이미지 열기 및 전처리 수행
        image = cv2.imread(image_path)
        processed_image = preprocess_image(image)

        # 결과 저장 경로 설정
        output_path = os.path.join(self.output_folder, f"first_prepro_{yolo_result_code}.png")
        cv2.imwrite(output_path, processed_image)

        # 데이터베이스에 1차 전처리 결과 저장
        first_prepro_result = FirstPreprocessingResult(
            video_code=yolo_result.video_code,
            yolo_result_code=yolo_result_code,
            first_result_path=output_path
        )
        db.session.add(first_prepro_result)
        db.session.commit()

        return {
            "status": "success",
            "message": "First preprocessing completed successfully.",
            "first_result_path": output_path
        }, 200

# FirstPreproApp 인스턴스 생성
first_prepro_app = FirstPreproApp(output_folder="first_preprocessed")

# 핸들러 함수
def handle_firstPrepro():
    yolo_result_code = request.form.get('yolo_result_code')
    if not yolo_result_code:
        return jsonify({"status": "error", "message": "yolo_result_code is required."}), 400

    return jsonify(first_prepro_app.process_first_prepro(yolo_result_code))