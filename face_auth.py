import cv2
import numpy as np
import base64
import os

class FaceAuth:
    def __init__(self):
        models_dir = os.path.join(os.path.dirname(__file__), 'models')
        
        # Paths to the new ONNX models
        det_model_path = os.path.join(models_dir, 'face_detection_yunet.onnx')
        rec_model_path = os.path.join(models_dir, 'face_recognition_sface.onnx')
        
        # Fallback to Haar Cascade if needed, but we'll prioritize the DNN models
        self.face_cascade = cv2.CascadeClassifier(os.path.join(models_dir, 'haarcascade_frontalface_default.xml'))

        # Initialize the DNN models
        try:
            self.detector = cv2.FaceDetectorYN.create(det_model_path, "", (0, 0))
            self.recognizer = cv2.FaceRecognizerSF.create(rec_model_path, "")
            self.dnn_ready = True
        except Exception as e:
            print(f"Error loading DNN models: {e}")
            self.dnn_ready = False

        # In-memory storage for face features of people who have already voted
        # In a real app, this should be a persistent database
        self.voted_features = []
        
        # Similarity threshold for SFace (Cosine distance)
        # Typically > 0.363 is a match
        self.threshold = 0.363

    def decode_image(self, base64_image):
        try:
            encoded_data = base64_image.split(',')[1]
            nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except:
            return None

    def verify_frame(self, base64_image):
        """
        Detects face and checks if the person has already voted.
        Returns: (success, message, feature_vector)
        """
        frame = self.decode_image(base64_image)
        if frame is None:
            return False, "Invalid image frame.", None

        if not self.dnn_ready:
            # Fallback to simple detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)
            if len(faces) > 0:
                return True, "Face detected (Identity check disabled - models missing).", None
            return False, "No face detected.", None

        # DNN Detection
        h, w, _ = frame.shape
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)

        if faces is None or len(faces) == 0:
            return False, "No face detected. Please position yourself clearly.", None

        # Extract features for the first face detected
        face_aligned = self.recognizer.alignCrop(frame, faces[0])
        current_feature = self.recognizer.feature(face_aligned)

        # Check against already voted faces
        for voted_feature in self.voted_features:
            score = self.recognizer.match(current_feature, voted_feature, cv2.FaceRecognizerSF_FR_COSINE)
            if score >= self.threshold:
                return False, "BIOMETRIC DENIED: This face has already been used to cast a vote. Each person can only vote once.", None

        return True, "Identity Verified Successfully!", current_feature

    def register_voted_face(self, feature_vector):
        """
        Stores the feature vector to prevent this person from voting again.
        """
        if feature_vector is not None:
            # Check if already in list to avoid duplicates
            exists = False
            for f in self.voted_features:
                score = self.recognizer.match(feature_vector, f, cv2.FaceRecognizerSF_FR_COSINE)
                if score >= self.threshold:
                    exists = True
                    break
            
            if not exists:
                self.voted_features.append(feature_vector)
                return True
        return False

    def verify_liveness(self, base64_image, expected_direction):
        """
        Verifies if the person is moving their head in the expected direction.
        Directions: 'left', 'right', 'center'
        """
        frame = self.decode_image(base64_image)
        if frame is None or not self.dnn_ready:
            return False, "Unable to perform liveness check."

        h, w, _ = frame.shape
        self.detector.setInputSize((w, h))
        _, faces = self.detector.detect(frame)

        if faces is None or len(faces) == 0:
            return False, "No face detected during liveness check."

        # Get landmarks for the first face
        face = faces[0]
        # Landmarks: 4,5 (R eye), 6,7 (L eye), 8,9 (Nose)
        r_eye_x = face[4]
        l_eye_x = face[6]
        nose_x = face[8]

        # Calculate horizontal position of nose between eyes (0 to 1)
        # Note: In the image, 'Left' eye is usually on the right side of the frame depending on mirroring
        # Let's assume standard camera mirroring
        try:
            eye_dist = abs(r_eye_x - l_eye_x)
            if eye_dist == 0: return False, "Invalid face geometry."
            
            # Ratio of nose position relative to eyes (0.5 is center)
            ratio = (nose_x - min(r_eye_x, l_eye_x)) / eye_dist
            print(f"Liveness Debug - Nose Position Ratio: {ratio:.2f}")

            if expected_direction == 'tilt':
                # If tilted, the nose moves away from the center (0.5)
                # We'll be very lenient: if it's less than 0.42 or more than 0.58, it's a tilt.
                if ratio < 0.42 or ratio > 0.58:
                    return True, "Liveness verified"
                return False, "Please tilt your head more clearly to the side"
            else:
                # For center check
                if 0.4 <= ratio <= 0.6:
                    return True, "Face Centered"
                return False, "Please look straight at the camera"
                    
        except Exception as e:
            return False, f"Liveness error: {str(e)}"

    def reset_auth(self):
        """
        Clears the list of people who have already voted.
        """
        self.voted_features = []
        return True

# Singleton instance
face_authenticator = FaceAuth()
