import cv2
from tqdm import tqdm
from types import SimpleNamespace
import argparse
import sys
import math
import helpers.log as log
import helpers.media_pipe as p_mp
import json
import helpers.json as json_pd

def calcular_angulos_obrigatorio(maior: float, menor: float, quantidade: int) -> []:
    maior = float(maior)
    menor = float(menor)
    quantidade = int(quantidade)

    if quantidade <= 0:
        raise ValueError("quantidade deve ser maior que zero")
    if maior < menor:
        raise ValueError("maior deve ser maior ou igual a menor")

    fator = (maior - menor) / quantidade

    return [maior - i * fator for i in range(quantidade)] + [menor]


def avaliar_movimento(args):

    mediapipe = p_mp.inicializar_mediapipe()

    angulo_que_definine_inicio_exercicio = float(args.angulo_inicial)
    angulo_que_define_maximo_correto = float(args.angulo_final)
    alterecao_minima_angulo = float(args.alterecao_minima_angulo)
    angulos_obrigatorios = calcular_angulos_obrigatorio(angulo_que_define_maximo_correto, angulo_que_definine_inicio_exercicio, args.quantidade_angulos)
   

    cap: cv2.VideoCapture | None = None
    try:
        cap = p_mp.capturar_video(args.video)
    except Exception as e:
        log.log_error(e)
        return

    propriedades_video = SimpleNamespace(
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        fps=int(cap.get(cv2.CAP_PROP_FPS)),
        total_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    )

    avaliacoes = []
   
    frame_count = 0
    count = 0
    avaliacao_atual = None
    ultimo_angulo_avaliado = None
    for _ in tqdm(range(propriedades_video.total_frames), desc="Processando vídeo"):
        ret, frame = cap.read()

        if not ret:
            break

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        results = mediapipe.pose.process(rgb_frame)

        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark 
            ombro_direito = landmarks[mediapipe.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            pulso_direito = landmarks[mediapipe.mp_pose.PoseLandmark.RIGHT_WRIST.value]
            angulo = calcular_angulo(pulso_direito, ombro_direito)
            movimentou = abs(angulo - (ultimo_angulo_avaliado or 0.0)) > alterecao_minima_angulo
            if(not movimentou):
                frame_count += 1
                continue
            
            if(avaliacao_atual):
                criar_novo = avaliar_angulo(angulo, ultimo_angulo_avaliado, angulo_que_definine_inicio_exercicio, args.margem_proximidade_inicio_fim, avaliacao_atual)

            if(avaliacao_atual == None or criar_novo):
                count += 1                
                avaliacao_atual = SimpleNamespace(
                                        frame_inicio = frame_count,
                                        frame_fim = None,
                                        angulos_ida = dict.fromkeys(angulos_obrigatorios, False),
                                        angulos_volta = dict.fromkeys(angulos_obrigatorios[1:], False),
                                        atingiu_angulo_maximo = False,
                                        atingiu_angulo_minimo = False,
                                        existe_movimento = False,
                                        fps = cap.get(cv2.CAP_PROP_FPS),
                                        esta_em_sentido_ida = True,
                                        esta_em_sentido_volta = False,
                                        passou_angulo_maximo = False
                                    ) 
                avaliacoes.append(avaliacao_atual)
                print(f"iniciou: {count}")
            if(avaliacao_atual):
                validar_maximo_minimo(angulo, angulo_que_definine_inicio_exercicio, angulo_que_define_maximo_correto, float(args.margem_proximidade_inicio_fim), avaliacao_atual)
                validar_sentido(angulo, ultimo_angulo_avaliado, avaliacao_atual)
                validar_movimento(angulo, angulos_obrigatorios[-2], float(args.margem_proximidade_angulos), avaliacao_atual)
                if(avaliacao_atual.esta_em_sentido_ida):
                    for angulo_key in avaliacao_atual.angulos_ida:
                        valor_atual = avaliacao_atual.angulos_ida[angulo_key] 
                        avaliacao_atual.angulos_ida[angulo_key] = valor_atual or esta_no_angulo(angulo, angulo_key, args.margem_proximidade_angulos)
                if(avaliacao_atual.esta_em_sentido_volta):
                    for angulo_key in avaliacao_atual.angulos_volta:
                        valor_atual = avaliacao_atual.angulos_volta[angulo_key] 
                        avaliacao_atual.angulos_volta[angulo_key] = valor_atual  or esta_no_angulo(angulo, angulo_key, args.margem_proximidade_angulos)        
                
                avaliacao_atual.frame_fim = frame_count 

            ultimo_angulo_avaliado = angulo

        frame_count += 1

    cap.release()
    resultado = [
        SimpleNamespace(
            frame_inicio=item.frame_inicio,
            frame_fim=item.frame_fim,
            fps = item.fps,
            correto=all(item.angulos_ida.values()) and all(item.angulos_volta.values()) and not item.passou_angulo_maximo
        )
        for item in [item for item in avaliacoes if item.existe_movimento is True]
    ]

    nome_arquivo_json = f"{args.output}/avaliacao.json"
    with open(nome_arquivo_json, "w", encoding="utf-8") as file: json.dump([vars(item) for item in resultado], file, indent=4, ensure_ascii=False)
    cv2.destroyAllWindows()     
    gerar_video_relatorio(args, nome_arquivo_json)

def gerar_video_relatorio(args, path_avaliacao):

    arquivo_saida_video = "resultado.mp4"
    
    mediapipe = p_mp.inicializar_mediapipe()
    
    df = json_pd.retornar_dados(path_avaliacao)
    
    cap: cv2.VideoCapture | None = None
    try:
        cap = p_mp.capturar_video(args.video)
    except Exception as e:
        log.log_error(e)
        return
    
    propriedades_video = SimpleNamespace(
        width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        fps=int(cap.get(cv2.CAP_PROP_FPS)),
        total_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    )
    print(propriedades_video)     
    video_writer = p_mp.criar_video_writer('mp4v', propriedades_video, f"{args.output}/{arquivo_saida_video}")
    frame_count = 0

    for _ in tqdm(range(propriedades_video.total_frames), desc="Processando vídeo"):
        ret, frame = cap.read()           
    
        if not ret:
            print("fim")   
            break
    
        df_no_intervalo_correto = df[(df["frame_inicio"] <= frame_count) & (frame_count <= df["frame_fim"]) & df["correto"]]
        df_no_intervalo_incorreto = df[(df["frame_inicio"] <= frame_count) & (frame_count <= df["frame_fim"])&  (~df["correto"])]
        correto = not df_no_intervalo_correto.empty
        incorreto = not df_no_intervalo_incorreto.empty   
        desenhar_rotulo(frame, correto, incorreto, cv2)

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        results = mediapipe.pose.process(rgb_frame)
    
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark 
            ombro_direito = landmarks[mediapipe.mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
            pulso_direito = landmarks[mediapipe.mp_pose.PoseLandmark.RIGHT_WRIST.value]
            angulo = calcular_angulo(pulso_direito, ombro_direito)
                
            escrever_pontos("Ombro direito", ombro_direito, angulo, frame)
            escrever_pontos("Pulso direito", pulso_direito, angulo, frame)
        video_writer.write(frame)   
            
        frame_count += 1
        cv2.imshow('Video', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break                 
    
                
    
    cap.release()
    video_writer.release()       
    cv2.destroyAllWindows() 

def avaliar_angulo(angulo_atual: float, angulo_anterior: float, angulo_inicial: float, margem: float, avaliacao_atual):
    movimento_ida = angulo_atual > angulo_anterior  
    esta_no_angulo_minimo = esta_no_angulo(angulo_atual, float(angulo_inicial), float(margem))
    
    return movimento_ida and esta_no_angulo_minimo and (angulo_anterior == None or avaliacao_atual.esta_em_sentido_volta)

def validar_sentido(angulo_atual: float, angulo_anterior: float, avaliacao_atual):
    avaliacao_atual.esta_em_sentido_ida = angulo_anterior == None or angulo_atual >= angulo_anterior
    avaliacao_atual.esta_em_sentido_volta = not avaliacao_atual.esta_em_sentido_ida

def validar_movimento(angulo_atual: float, angulo_base: float, margem: float, avaliacao_atual):
    avaliacao_atual.existe_movimento = avaliacao_atual.existe_movimento or (avaliacao_atual.atingiu_angulo_minimo and (avaliacao_atual.esta_em_sentido_ida and esta_no_angulo(angulo_atual, angulo_base, margem)))

def validar_maximo_minimo(angulo_atual: float, angulo_minimo: float, angulo_maximo: float,margem: float, avaliacao_atual):
    avaliacao_atual.atingiu_angulo_maximo = avaliacao_atual.atingiu_angulo_maximo or esta_no_angulo(angulo_atual, angulo_maximo, margem)
    avaliacao_atual.atingiu_angulo_minimo = avaliacao_atual.atingiu_angulo_minimo or esta_no_angulo(angulo_atual, angulo_minimo, margem)
    avaliacao_atual.passou_angulo_maximo = avaliacao_atual.passou_angulo_maximo or angulo_atual > (angulo_maximo + margem)

def esta_no_angulo(angulo_atual: float, angulo_base: float, margem: float) -> bool:
    minimo = float(angulo_base) - float(margem)
    maximo = float(angulo_base) + float(margem)

    log.log_info(f"esta no angulo: minimo:{minimo} maximo: {maximo} atual:{angulo_atual} margem: {margem} ") 

    return angulo_atual >= minimo and angulo_atual <= maximo

def calcular_angulo(landmark_base, landmark_movimento):
    x = landmark_base.x - landmark_movimento.x
    y = landmark_base.y - landmark_movimento.y

    angulo_radianos = math.atan2(x, y)
    angulo_graus = math.degrees(angulo_radianos)
    return abs(angulo_graus)

def escrever_pontos(descricao, landmark, angulo, frame):
    h, w, _ = frame.shape
    x = int(landmark.x * w)
    y = int(landmark.y * h)
    angulo_str = f"{angulo:.1f}*"
    log.log_info(f"{descricao}: {x} {y} {angulo_str}") 
    cv2.circle(frame, (x, y), radius=6, color=(0, 0, 255), thickness=-1)
    cv2.putText(frame, f'{descricao}: {x} {y} {angulo_str}', (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

def desenhar_rotulo(frame, correto, incorreto, cv2):

    if(not correto and not incorreto):
        return

    altura, largura = frame.shape[:2]
    texto = 'certo' if correto else 'errado'
    cor = (0, 255, 0) if correto else (0, 0, 255)
    fonte = cv2.FONT_HERSHEY_SIMPLEX
    escala = max(0.5, altura / 360)
    espessura = max(1, round(escala * 2))
    margem = max(6, round(min(altura, largura) * 0.025))
    (w, h), base = cv2.getTextSize(texto, fonte, escala, espessura)
    if w > largura - 2 * margem:
        escala *= (largura - 2 * margem) / w
        espessura = max(1, round(escala * 2))
        (w, h), base = cv2.getTextSize(texto, fonte, escala, espessura)
    x, y = largura - margem - w, margem + h
  
    padding = max(3, margem // 2)
    cv2.rectangle(frame, (max(0, x - padding), max(0, margem - padding)),
                  (min(largura - 1, x + w + padding), min(altura - 1, y + base + padding)),
                  (0, 0, 0), -1)
    cv2.putText(frame, texto, (x, y), fonte, escala, cor, espessura, cv2.LINE_AA) 
    

def argumentos():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--video", required=True, help="caminho do arquivo do video")    
    parser.add_argument("-o", "--output", required=True, help="pasta de saida dos dados")
    parser.add_argument("-q", "--quantidade_angulos", required=True, help="quantidade de angulos obrigatórios")
    parser.add_argument("-s", "--angulo_inicial", required=True, help="ângulo incial do exercício")
    parser.add_argument("-e", "--angulo_final", required=True, help="ângulo final do exercício")
    parser.add_argument("-m", "--margem_proximidade_inicio_fim", required=True, help="margem de proximidade em graus para considerar angulo atingido para inicio e fim")
    parser.add_argument("-n", "--margem_proximidade_angulos", required=True, help="margem de proximidade em graus para considerar angulo atingido")
    parser.add_argument("-a", "--alterecao_minima_angulo", required=True, help="alteração mínima de angulo para considerar movimento")        
    
    return parser.parse_args()


def main():
    log.log_info("início")
    args = argumentos()
    avaliar_movimento(args)       

if __name__ == '__main__':
    sys.exit(main())        




