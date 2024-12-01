import os
import torch
import cv2
import numpy as np
import glob
import tempfile
import time
from flask import Flask, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from detectron2.engine import DefaultPredictor
from detectron2.config import get_cfg
from model_detection import setup_cfg, get_parser, VisualizationDemo, save_result_to_txt

# Flask 앱 초기화
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///your_database.db'  # DB 설정
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# 데이터베이스 모델 정의
class Video(db.Model):
    __tablename__ = 'video'
    video_code = db.Column(db.Integer, primary_key=True)
    upload_time = db.Column(db.DateTime, nullable=False)
    video_path = db.Column(db.String(255), nullable=False)

class FirstPreprocessingResult(db.Model):
    __tablename__ = '1st_preprocessing_result'
    first_result_code = db.Column(db.Integer, primary_key=True)
    video_code = db.Column(db.Integer, db.ForeignKey('video.video_code'), nullable=False)
    yolo_result_code = db.Column(db.Integer, nullable=False)
    first_result_path = db.Column(db.String(255), nullable=False)
    video = db.relationship('Video', backref=db.backref('first_preprocessing_results', lazy=True))

# Detectron2 설정 및 모델 불러오기
cfg = get_cfg()
cfg.merge_from_file("./config.yaml")  # YAML 파일 경로 설정
cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = 0.5  # 예측 점수 임계값 설정
cfg.MODEL.WEIGHTS = "./model_0000599.pth"  # 모델 가중치 파일 경로 설정
cfg.MODEL.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"  # GPU 사용 가능하면 GPU 사용

predictor = DefaultPredictor(cfg)

@app.route('/get_first_preprocessing', methods=['GET'])
def get_first_preprocessing():
    video_code = request.args.get('video_code')
    if not video_code:
        return jsonify({"error": "video_code parameter is required"}), 400

    first_result = FirstPreprocessingResult.query.filter_by(video_code=video_code).first()
    if not first_result:
        return jsonify({"error": "No preprocessing result found for this video_code"}), 404

    file_path = first_result.first_result_path
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found on server"}), 404

    return send_file(file_path, mimetype='image/jpeg')

@app.route('/detect_visual', methods=['POST'])
def detect_objects_visual():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400

    try:
        # 이미지 읽기
        file = request.files['image']
        np_img = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(np_img, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({"error": "Failed to load image"}), 400

        # Detectron2를 사용한 객체 탐지 수행
        outputs = predictor(img)
        instances = outputs["instances"].to("cpu")
        boxes = instances.pred_boxes.tensor.numpy()
        classes = instances.pred_classes.numpy()
        scores = instances.scores.numpy()

        for box, cls, score in zip(boxes, classes, scores):
            x1, y1, x2, y2 = box
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            label = f"Class: {cls}, Score: {score:.2f}"
            cv2.putText(img, label, (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_filename = temp_file.name
        cv2.imwrite(temp_filename, img)

        return send_file(temp_filename, mimetype='image/jpeg')

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/batch_process', methods=['POST'])
def batch_process():
    try:
        input_dir = request.json.get('input_dir')
        output_dir = request.json.get('output_dir')

        if not os.path.exists(input_dir):
            return jsonify({"error": "Input directory does not exist"}), 400

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        args = get_parser().parse_args([])
        args.input = input_dir + '/*.jpg'
        args.output = output_dir
        cfg = setup_cfg(args)
        detection_demo = VisualizationDemo(cfg)

        start_time_all = time.time()
        img_count = 0

        for img_path in glob.glob(args.input):
            print(f"Processing {img_path}...")
            img_name = os.path.basename(img_path)
            img_save_path = os.path.join(args.output, img_name)
            img = cv2.imread(img_path)

            if img is None:
                print(f"Failed to load {img_path}")
                continue

            start_time = time.time()

            prediction, vis_output, polygons = detection_demo.run_on_image(img)
            txt_save_path = os.path.join(args.output, f"res_img_{img_name.split('.')[0]}.txt")
            save_result_to_txt(txt_save_path, prediction, polygons)
            vis_output.save(img_save_path)

            print(f"Time: {time.time() - start_time:.2f} s / img")
            img_count += 1

        avg_time = (time.time() - start_time_all) / img_count if img_count > 0 else 0
        print(f"Average Time: {avg_time:.2f} s / img")

        return jsonify({"message": "Batch processing completed", "average_time": avg_time}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)