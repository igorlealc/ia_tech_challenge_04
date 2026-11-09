import cv2
import mediapipe as mp
from types import SimpleNamespace

def inicializar_mediapipe() -> SimpleNamespace:
    media_pipe = SimpleNamespace(
        mp_pose = mp.solutions.pose,
        pose = mp.solutions.pose.Pose(min_detection_confidence=0.9, min_tracking_confidence=0.9),
        mp_drawing = mp.solutions.drawing_utils
    )    
    return media_pipe

def capturar_video(video_path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception("Erro ao abrir o vídeo.")        
    return cap

def criar_video_writer(codec, video_props, output_path) -> cv2.VideoWriter:
    fourcc = cv2.VideoWriter_fourcc(*codec)
    out = cv2.VideoWriter(output_path, fourcc, video_props.fps, (video_props.width, video_props.height))
    return out